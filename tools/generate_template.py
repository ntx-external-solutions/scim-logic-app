"""Generates logic-app/azuredeploy.json.

azuredeploy.json is generated: edit this file, then run from the repository root:

    python3 tools/generate_template.py

See docs/maintainers/DEVELOPING.md.
"""
import json, os, sys

GRAPH = "https://graph.microsoft.com/v1.0"
MSI_GRAPH = {"type": "ManagedServiceIdentity", "audience": "https://graph.microsoft.com"}
MSI_STORAGE = {"type": "ManagedServiceIdentity", "audience": "https://storage.azure.com/"}
BLOB_VERSION = "2021-08-06"
EMPTY = "@json('[]')"


def after(*names, statuses=("Succeeded",)):
    return {n: list(statuses) for n in names}


def graph_get(uri, run_after=None):
    return {"runAfter": run_after or {}, "type": "Http",
            "inputs": {"method": "GET", "uri": uri, "authentication": MSI_GRAPH}}


def blob_get(path, run_after=None):
    return {"runAfter": run_after or {}, "type": "Http",
            "inputs": {"method": "GET", "uri": "@{parameters('blobBaseUrl')}/" + path,
                       "headers": {"x-ms-version": BLOB_VERSION},
                       "authentication": MSI_STORAGE}}


def blob_put(path, body, content_type, run_after=None):
    return {"runAfter": run_after or {}, "type": "Http",
            "inputs": {"method": "PUT", "uri": "@{parameters('blobBaseUrl')}/" + path,
                       "headers": {"x-ms-version": BLOB_VERSION, "x-ms-blob-type": "BlockBlob",
                                   "Content-Type": content_type},
                       "body": body, "authentication": MSI_STORAGE}}


def compose(expr, run_after=None):
    return {"runAfter": run_after or {}, "type": "Compose", "inputs": expr}


def set_var(name, value, run_after=None):
    return {"runAfter": run_after or {}, "type": "SetVariable", "inputs": {"name": name, "value": value}}


def query(frm, where, run_after=None):
    return {"runAfter": run_after or {}, "type": "Query", "inputs": {"from": frm, "where": where}}


def select(frm, sel, run_after=None):
    return {"runAfter": run_after or {}, "type": "Select", "inputs": {"from": frm, "select": sel}}


def cond(expr, actions, else_actions=None, run_after=None):
    """expr is a boolean workflow expression string."""
    return {"runAfter": run_after or {}, "type": "If",
            "expression": {"and": [{"equals": [expr, True]}]},
            "actions": actions, "else": {"actions": else_actions or {}}}


def sets_equal(a, b):
    """Order-insensitive equality of two arrays of scalars (union() de-duplicates)."""
    return (f"and(equals(length(union({a}, {b})), length(union({a}, json('[]')))), "
            f"equals(length(union({a}, json('[]'))), length(union({b}, json('[]')))))")


# ---------------------------------------------------------------- delta stages

def delta_stage(kind, token_blob, first_url, collect_actions, collect_last, error_label):
    """Reads a saved delta link (or starts a new one), then follows Graph delta pages.

    kind: 'users' | 'groups'. collect_actions: actions that merge ids from
    body('Call_{kind}_delta') into changedUserIds; collect_last is the final one.
    """
    K = kind.capitalize()
    url_var, more_var, new_var = f"{kind}Url", f"{kind}HasMore", f"{kind}NewDelta"
    get_token = f"Get_{kind}_delta_token"
    call = f"Call_{kind}_delta"
    loop_actions = {call: graph_get(f"@variables('{url_var}')")}
    loop_actions.update(collect_actions)
    loop_actions[f"Check_{kind}_next_page"] = cond(
        f"@not(equals(body('{call}')?['@odata.nextLink'], null))",
        {f"Set_{kind}_next_page": set_var(url_var, f"@{{body('{call}')?['@odata.nextLink']}}")},
        {
            f"Store_{kind}_delta_link": set_var(new_var, f"@{{body('{call}')?['@odata.deltaLink']}}"),
            f"Finish_{kind}_pages": set_var(more_var, False, after(f"Store_{kind}_delta_link")),
        },
        run_after=after(collect_last))
    loop_actions[f"Record_{kind}_delta_error"] = set_var(
        "runError",
        f"Microsoft Graph refused the request to read {error_label} (HTTP @{{outputs('{call}')?['statusCode']}}). "
        "Check that the Logic App's managed identity has been granted the Microsoft Graph permissions "
        "listed in the setup guide. Permission changes can take up to an hour to take effect.",
        after(call, statuses=("Failed", "TimedOut")))

    return {
        get_token: blob_get(f"state/{token_blob}"),
        f"Set_{kind}_start_url": set_var(
            url_var,
            f"@{{if(equals(outputs('{get_token}')?['statusCode'], 200), trim(string(body('{get_token}'))), "
            f"concat('{first_url}', if(parameters('syncExistingUsersOnFirstRun'), '', '&$deltatoken=latest')))}}",
            after(get_token, statuses=("Succeeded", "Failed"))),
        f"Check_{kind}_token_readable": cond(
            f"@not(or(equals(outputs('{get_token}')?['statusCode'], 200), equals(outputs('{get_token}')?['statusCode'], 404)))",
            {f"Record_{kind}_storage_error": set_var(
                "runError",
                f"Could not read sync progress from the storage account (HTTP @{{outputs('{get_token}')?['statusCode']}}). "
                "If the Logic App was deployed in the last few minutes, its storage access may still be taking effect.")},
            run_after=after(f"Set_{kind}_start_url")),
        f"Follow_{kind}_changes": {
            "runAfter": after(f"Check_{kind}_token_readable"),
            "type": "Until",
            "expression": f"@or(equals(variables('{more_var}'), false), not(equals(variables('runError'), '')))",
            "limit": {"count": 5000, "timeout": "PT1H"},
            "actions": loop_actions,
        },
    }

def json_str(prop):
    """Expression rendering item()[prop] as a JSON literal: an escaped, quoted string, or null."""
    return (f"substring(string(createArray(item()?['{prop}'])), 1, "
            f"sub(length(string(createArray(item()?['{prop}']))), 2))")


users_collect = {
    "Filter_live_users": query("@coalesce(body('Call_users_delta')?['value'], json('[]'))",
                               "@equals(item()?['@removed'], null)", after("Call_users_delta")),
    "Select_changed_user_ids": select("@body('Filter_live_users')", "@item()?['id']", after("Filter_live_users")),
    "Merge_changed_user_ids": compose("@union(variables('changedUserIds'), body('Select_changed_user_ids'))",
                                      after("Select_changed_user_ids")),
    "Save_changed_user_ids": set_var("changedUserIds", "@outputs('Merge_changed_user_ids')",
                                     after("Merge_changed_user_ids")),
    # Keep each user's department from the change feed itself: Graph lookups made
    # straight after a change can still return the old value for a minute or so.
    "Select_department_pairs": select("@body('Filter_live_users')",
                                      f"@concat({json_str('id')}, ':', {json_str('department')})",
                                      after("Save_changed_user_ids")),
    "Merge_delta_departments": compose(
        "@union(variables('deltaDepartments'), json(concat('{', join(body('Select_department_pairs'), ','), '}')))",
        after("Select_department_pairs")),
    "Save_delta_departments": set_var("deltaDepartments", "@outputs('Merge_delta_departments')",
                                      after("Merge_delta_departments")),
}

# Each group in a groups/delta page carries a 'members@delta' array. Flatten all of
# them into one array without a loop: stringify each, strip the brackets, re-join.
groups_collect = {
    "Select_member_lists": select("@coalesce(body('Call_groups_delta')?['value'], json('[]'))",
                                  "@string(coalesce(item()?['members@delta'], json('[]')))", after("Call_groups_delta")),
    "Filter_nonempty_member_lists": query("@body('Select_member_lists')", "@not(equals(item(), '[]'))",
                                          after("Select_member_lists")),
    "Select_member_list_bodies": select("@body('Filter_nonempty_member_lists')",
                                        "@substring(item(), 1, sub(length(item()), 2))", after("Filter_nonempty_member_lists")),
    "Combine_member_changes": compose("@json(concat('[', join(body('Select_member_list_bodies'), ','), ']'))",
                                      after("Select_member_list_bodies")),
    "Filter_user_members": query("@outputs('Combine_member_changes')",
                                 "@equals(item()?['@odata.type'], '#microsoft.graph.user')", after("Combine_member_changes")),
    "Select_member_ids": select("@body('Filter_user_members')", "@item()?['id']", after("Filter_user_members")),
    "Merge_member_ids": compose("@union(variables('changedUserIds'), body('Select_member_ids'))", after("Select_member_ids")),
    "Save_member_ids": set_var("changedUserIds", "@outputs('Merge_member_ids')", after("Merge_member_ids")),
}

load_user_changes = cond(
    "@not(equals(parameters('roleSource'), 'groups'))",
    delta_stage("users", "users-delta.txt", f"{GRAPH}/users/delta?$select=department",
                users_collect, "Save_delta_departments", "user department changes"),
    run_after=after("Initialize_variables"))

load_group_changes = cond(
    "@not(equals(parameters('roleSource'), 'department'))",
    delta_stage("groups", "groups-delta.txt", f"{GRAPH}/groups/delta?$select=members",
                groups_collect, "Save_member_ids", "group membership changes"),
    run_after=after("Load_user_changes", statuses=("Succeeded", "Failed", "Skipped", "TimedOut")))

# ---------------------------------------------------------------- mapping file (option A)

load_mapping_file = cond(
    "@equals(parameters('mappingMode'), 'mapped')",
    {
        "Get_role_mapping_file": blob_get("role-mapping.json"),
        "Save_mapping": set_var("mapping", "@json(string(body('Get_role_mapping_file')))", after("Get_role_mapping_file")),
        "Record_mapping_error": set_var(
            "runError",
            "Could not read role-mapping.json (HTTP @{outputs('Get_role_mapping_file')?['statusCode']}). Mapping mode is "
            "'mapped', so upload your role-mapping.json to the 'config' container of this Logic App's storage account.",
            after("Get_role_mapping_file", statuses=("Failed", "TimedOut"))),
        "Select_department_rule_role_names": select(
            "@coalesce(variables('mapping')?['departmentRoles'], json('[]'))", "@item()?['role']", after("Save_mapping")),
        "Select_group_rule_role_names": select(
            "@coalesce(variables('mapping')?['groupRoles'], json('[]'))", "@item()?['role']", after("Save_mapping")),
        "Save_file_controlled_roles": set_var(
            "controlledRoles",
            "@union(body('Select_department_rule_role_names'), body('Select_group_rule_role_names'), "
            "if(empty(coalesce(variables('mapping')?['defaultRole'], '')), json('[]'), createArray(variables('mapping')?['defaultRole'])))",
            after("Select_department_rule_role_names", "Select_group_rule_role_names")),
    },
    run_after=after("Load_group_changes", statuses=("Succeeded", "Failed", "Skipped", "TimedOut")))

# ---------------------------------------------------------------- Entra app roles (option B)

SP = f"{GRAPH}/servicePrincipals(appId='@{{parameters('entraAppId')}}')"

load_app_roles = cond(
    "@equals(parameters('mappingMode'), 'entraAppRoles')",
    {
        "Get_app_roles": graph_get(f"{SP}?$select=id,appRoles"),
        "Record_app_roles_error": set_var(
            "runError",
            "Could not read the Enterprise App's roles (HTTP @{outputs('Get_app_roles')?['statusCode']}). "
            "Check the Enterprise App ID setting, and that the Logic App's managed identity has the "
            "Application.Read.All Microsoft Graph permission.",
            after("Get_app_roles", statuses=("Failed", "TimedOut"))),
        # Only custom roles map to Process Manager. Built-in gallery roles such as
        # 'User' and 'msiam_access' have no value, so they are skipped.
        "Filter_custom_app_roles": query(
            "@coalesce(body('Get_app_roles')?['appRoles'], json('[]'))",
            "@and(equals(item()?['isEnabled'], true), not(empty(coalesce(item()?['value'], ''))))",
            after("Get_app_roles")),
        "Select_app_role_pairs": select("@body('Filter_custom_app_roles')",
                                        f"@concat('\"', item()?['id'], '\":', {json_str('displayName')})",
                                        after("Filter_custom_app_roles")),
        "Build_role_name_lookup": compose("@json(concat('{', join(body('Select_app_role_pairs'), ','), '}'))",
                                          after("Select_app_role_pairs")),
        "Select_app_role_names": select("@body('Filter_custom_app_roles')", "@item()?['displayName']",
                                        after("Filter_custom_app_roles")),
        "Save_app_controlled_roles": set_var("controlledRoles", "@body('Select_app_role_names')",
                                             after("Select_app_role_names")),
        "Set_assignments_start_url": set_var("assignmentsUrl", f"{SP}/appRoleAssignedTo?$top=999",
                                             after("Build_role_name_lookup")),
        "Follow_assignment_pages": {
            "runAfter": after("Set_assignments_start_url"),
            "type": "Until",
            "expression": "@or(equals(variables('assignmentsHasMore'), false), not(equals(variables('runError'), '')))",
            "limit": {"count": 1000, "timeout": "PT30M"},
            "actions": {
                "Call_assignments": graph_get("@variables('assignmentsUrl')"),
                "Select_assignment_rows": select(
                    "@coalesce(body('Call_assignments')?['value'], json('[]'))",
                    {"principalId": "@item()?['principalId']",
                     "principalType": "@item()?['principalType']",
                     "role": "@outputs('Build_role_name_lookup')?[item()?['appRoleId']]"},
                    after("Call_assignments")),
                "Merge_assignments": compose("@union(variables('assignments'), body('Select_assignment_rows'))",
                                             after("Select_assignment_rows")),
                "Save_assignments": set_var("assignments", "@outputs('Merge_assignments')", after("Merge_assignments")),
                "Check_assignments_next_page": cond(
                    "@not(equals(body('Call_assignments')?['@odata.nextLink'], null))",
                    {"Set_assignments_next_page": set_var("assignmentsUrl",
                                                          "@{body('Call_assignments')?['@odata.nextLink']}")},
                    {"Finish_assignment_pages": set_var("assignmentsHasMore", False)},
                    run_after=after("Save_assignments")),
                "Record_assignments_error": set_var(
                    "runError",
                    "Could not read the Enterprise App's role assignments (HTTP @{outputs('Call_assignments')?['statusCode']}).",
                    after("Call_assignments", statuses=("Failed", "TimedOut"))),
            },
        },
        "Filter_mapped_assignments": query("@variables('assignments')", "@not(equals(item()?['role'], null))",
                                           after("Follow_assignment_pages")),
        "Save_mapped_assignments": set_var("assignments", "@body('Filter_mapped_assignments')",
                                           after("Filter_mapped_assignments")),
        "Get_saved_assignments": blob_get("state/app-role-assignments.json", after("Save_mapped_assignments")),
        "Previous_assignments": compose(
            "@if(equals(outputs('Get_saved_assignments')?['statusCode'], 200), json(string(body('Get_saved_assignments'))), json('[]'))",
            after("Get_saved_assignments", statuses=("Succeeded", "Failed"))),
        # When someone changes a role assignment, re-check every user it could affect:
        # directly assigned users and members of assigned groups, before and after.
        "Check_assignments_changed": cond(
            "@not(and(equals(length(union(outputs('Previous_assignments'), variables('assignments'))), length(variables('assignments'))), "
            "equals(length(outputs('Previous_assignments')), length(variables('assignments')))))",
            {
                "Mark_assignments_changed": set_var("assignmentsChanged", True),
                "Filter_assigned_users": query("@union(outputs('Previous_assignments'), variables('assignments'))",
                                               "@equals(item()?['principalType'], 'User')"),
                "Select_assigned_user_ids": select("@body('Filter_assigned_users')", "@item()?['principalId']",
                                                   after("Filter_assigned_users")),
                "Merge_assigned_user_ids": compose("@union(variables('changedUserIds'), body('Select_assigned_user_ids'))",
                                                   after("Select_assigned_user_ids", "Mark_assignments_changed")),
                "Save_assigned_user_ids": set_var("changedUserIds", "@outputs('Merge_assigned_user_ids')",
                                                  after("Merge_assigned_user_ids")),
                "Filter_assigned_groups": query("@union(outputs('Previous_assignments'), variables('assignments'))",
                                                "@equals(item()?['principalType'], 'Group')"),
                "Select_assigned_group_ids": select("@body('Filter_assigned_groups')", "@item()?['principalId']",
                                                    after("Filter_assigned_groups")),
                "For_each_assigned_group": {
                    "runAfter": after("Select_assigned_group_ids", "Save_assigned_user_ids"),
                    "type": "Foreach",
                    "foreach": "@union(body('Select_assigned_group_ids'), json('[]'))",
                    "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
                    "actions": {
                        "Get_assigned_group_members": graph_get(
                            f"{GRAPH}/groups/@{{items('For_each_assigned_group')}}/members/microsoft.graph.user?$select=id&$top=999"),
                        "Select_assigned_group_member_ids": select(
                            "@coalesce(body('Get_assigned_group_members')?['value'], json('[]'))", "@item()?['id']",
                            after("Get_assigned_group_members")),
                        "Merge_assigned_group_member_ids": compose(
                            "@union(variables('changedUserIds'), body('Select_assigned_group_member_ids'))",
                            after("Select_assigned_group_member_ids")),
                        "Save_assigned_group_member_ids": set_var(
                            "changedUserIds", "@outputs('Merge_assigned_group_member_ids')",
                            after("Merge_assigned_group_member_ids")),
                        # A group that has since been deleted has no members left to update.
                        "Skip_deleted_group": compose("Group not found; skipped.",
                                                      after("Get_assigned_group_members", statuses=("Failed",))),
                    },
                },
            },
            run_after=after("Previous_assignments")),
    },
    run_after=after("Load_mapping_file", statuses=("Succeeded", "Failed", "Skipped", "TimedOut")))

# ---------------------------------------------------------------- PM role filter (unchanged behaviour)

load_pm_roles = cond(
    "@and(equals(parameters('filterToExistingRoles'), true), not(equals(parameters('processManagerSiteUrl'), '')))",
    {
        "Get_PM_oauth_token": {
            "runAfter": {}, "type": "Http",
            "inputs": {"method": "POST", "uri": "@{parameters('processManagerSiteUrl')}/oauth2/token",
                       "headers": {"Content-Type": "application/x-www-form-urlencoded"},
                       "body": "grant_type=password&username=@{encodeUriComponent(parameters('processManagerUsername'))}"
                               "&password=@{encodeUriComponent(parameters('processManagerPassword'))}&duration=3600000"}},
        "Get_PM_roles_html": {
            "runAfter": after("Get_PM_oauth_token"), "type": "Http",
            "inputs": {"method": "GET", "uri": "@{parameters('processManagerSiteUrl')}/Lookup/AssociateRoles.aspx",
                       "headers": {"Authorization": "Bearer @{body('Get_PM_oauth_token')?['access_token']}"}}},
        "Split_PM_roles_html": compose("@skip(split(string(body('Get_PM_roles_html')), 'checkbox-label\" for=\"R'), 1)",
                                       after("Get_PM_roles_html")),
        "Extract_PM_role_names": select(
            "@outputs('Split_PM_roles_html')",
            "@toLower(trim(replace(replace(replace(replace(replace(first(split(substring(item(), add(indexOf(item(), '>'), 1)), '</label>')), '&amp;', '&'), '&#39;', ''''), '&quot;', '\"'), '&nbsp;', ' '), '&#246;', 'ö')))",
            after("Split_PM_roles_html")),
        "Save_valid_roles_lower": set_var("validRolesLower", "@body('Extract_PM_role_names')", after("Extract_PM_role_names")),
        "Record_PM_sign_in_error": set_var(
            "runError",
            "The role filter could not sign in to Process Manager (HTTP @{outputs('Get_PM_oauth_token')?['statusCode']}). "
            "Check the site URL, service-account username and password, and that the account doesn't use multi-factor sign-in.",
            after("Get_PM_oauth_token", statuses=("Failed", "TimedOut"))),
        "Record_PM_roles_error": set_var(
            "runError",
            "The role filter signed in to Process Manager but could not read the list of roles "
            "(HTTP @{outputs('Get_PM_roles_html')?['statusCode']}). Check the service account can view roles.",
            after("Get_PM_roles_html", statuses=("Failed", "TimedOut"))),
    },
    run_after=after("Load_app_role_assignments", statuses=("Succeeded", "Failed", "Skipped", "TimedOut")))

LOAD_STAGES = ["Load_user_changes", "Load_group_changes", "Load_mapping_file", "Load_app_role_assignments",
               "Load_existing_PM_roles"]
stop_if_setup_problem = cond(
    "@or(not(equals(variables('runError'), '')), contains(createArray("
    + ", ".join(f"actions('{a}')?['status']" for a in LOAD_STAGES) + "), 'Failed'))",
    {"Stop_with_setup_problem": {
        "runAfter": {}, "type": "Terminate",
        "inputs": {"runStatus": "Failed",
                   "runError": {"code": "SetupProblem", "message":
                       "@{if(empty(variables('runError')), 'A setup step failed before any users were processed. "
                       "Open this run and look for the step marked as failed.', variables('runError'))}"}}}},
    run_after=after("Load_existing_PM_roles", statuses=("Succeeded", "Failed", "Skipped", "TimedOut")))

# ---------------------------------------------------------------- per-user processing

U = "items('For_each_changed_user')"
PM_ROLES_OK = "or(empty(variables('validRolesLower')), contains(variables('validRolesLower'), toLower(trim(item()))))"
CHANGED = "not(" + sets_equal("body('Select_final_lower')", "body('Select_current_lower')") + ")"
STATE_CHANGED = "not(" + sets_equal("outputs('Desired_roles')", "outputs('Last_synced_roles')") + ")"

pm_user_found_actions = {
    "PM_user": compose("@first(body('Get_SCIM_user')?['Resources'])"),
    "Load_sync_state": cond(
        "@equals(parameters('updateMode'), 'managed')",
        {"Get_user_sync_state": blob_get(f"state/users/@{{{U}}}.json")},
        run_after=after("PM_user")),
    "Last_synced_roles": compose(
        "@if(equals(outputs('Get_user_sync_state')?['statusCode'], 200), json(string(body('Get_user_sync_state'))), json('[]'))",
        after("Load_sync_state", statuses=("Succeeded", "Failed"))),
    "Select_current_role_names": select("@coalesce(outputs('PM_user')?['roles'], json('[]'))",
                                        "@coalesce(item()?['display'], item()?['value'])", after("PM_user")),
    # Roles the sync is allowed to take away in managed mode: whatever it gave this
    # user last time, plus every role named in the mapping file / Enterprise App.
    "Select_removable_lower": select("@union(outputs('Last_synced_roles'), variables('controlledRoles'))",
                                     "@toLower(trim(string(item())))", after("Last_synced_roles")),
    "Filter_kept_roles": query(
        "@body('Select_current_role_names')",
        "@or(equals(parameters('updateMode'), 'preserve'), and(equals(parameters('updateMode'), 'managed'), "
        "not(contains(body('Select_removable_lower'), toLower(trim(string(item())))))))",
        after("Select_removable_lower", "Select_current_role_names")),
    "Select_kept_lower": select("@body('Filter_kept_roles')", "@toLower(trim(string(item())))", after("Filter_kept_roles")),
    "Filter_roles_to_add": query("@outputs('Desired_roles')",
                                 "@not(contains(body('Select_kept_lower'), toLower(trim(item()))))", after("Select_kept_lower")),
    "Final_roles": compose("@union(body('Filter_kept_roles'), body('Filter_roles_to_add'))", after("Filter_roles_to_add")),
    "Select_final_lower": select("@outputs('Final_roles')", "@toLower(trim(string(item())))", after("Final_roles")),
    "Select_current_lower": select("@body('Select_current_role_names')", "@toLower(trim(string(item())))",
                                   after("Select_current_role_names")),
    # Replace mode never strips a user down to zero roles; everything else only
    # writes to Process Manager when the role list actually changes.
    "Check_roles_changed": cond(
        f"@and(not(and(equals(parameters('updateMode'), 'replace'), empty(outputs('Desired_roles')))), {CHANGED})",
        {
            "Select_role_objects": select("@outputs('Final_roles')", {"display": "@item()"}),
            "Update_SCIM_user": {
                "runAfter": after("Select_role_objects"), "type": "Http",
                "inputs": {
                    "method": "PUT",
                    "uri": "@{parameters('scimBaseUrl')}/users/@{outputs('PM_user')?['id']}",
                    "headers": {"Authorization": "Bearer @{parameters('scimApiKey')}", "Content-Type": "application/json"},
                    "body": {
                        "userName": "@{outputs('PM_user')?['userName']}",
                        "name": {"givenName": "@{outputs('PM_user')?['name']?['givenName']}",
                                 "familyName": "@{outputs('PM_user')?['name']?['familyName']}"},
                        "active": "@coalesce(outputs('PM_user')?['active'], true)",
                        "emails": "@outputs('PM_user')?['emails']",
                        "roles": "@body('Select_role_objects')",
                    }}},
        },
        run_after=after("Select_final_lower", "Select_current_lower")),
    "Save_sync_state": cond(
        f"@and(equals(parameters('updateMode'), 'managed'), {STATE_CHANGED})",
        {"Put_user_sync_state": blob_put(f"state/users/@{{{U}}}.json", "@outputs('Desired_roles')", "application/json")},
        run_after=after("Check_roles_changed")),
}

user_found_actions = {
    "Current_user": compose("@body('Get_user')"),
    "Load_user_groups": cond(
        "@not(equals(parameters('roleSource'), 'department'))",
        {"Get_user_groups": graph_get(f"{GRAPH}/users/@{{{U}}}/memberOf/microsoft.graph.group?$select=id,displayName&$top=999")},
        run_after=after("Current_user")),
    "User_groups": compose("@coalesce(body('Get_user_groups')?['value'], json('[]'))", after("Load_user_groups")),
    "Department_name": compose(
        f"@trim(coalesce(if(contains(variables('deltaDepartments'), {U}), variables('deltaDepartments')?[{U}], "
        "outputs('Current_user')?['department']), ''))", after("Current_user")),

    # ---- department role (0 or 1)
    "Match_department_rules": query(
        "@coalesce(variables('mapping')?['departmentRoles'], json('[]'))",
        "@equals(toLower(trim(coalesce(item()?['department'], ''))), toLower(outputs('Department_name')))",
        after("Department_name")),
    "Select_department_rule_roles": select("@body('Match_department_rules')", "@item()?['role']",
                                           after("Match_department_rules")),
    "Department_candidates": compose(
        "@if(or(equals(parameters('roleSource'), 'groups'), empty(outputs('Department_name'))), json('[]'), "
        "if(equals(parameters('mappingMode'), 'mapped'), "
        "union(body('Select_department_rule_roles'), createArray(variables('mapping')?['departmentMapping']?[outputs('Department_name')], "
        "variables('mapping')?['departmentMapping']?['_default'])), createArray(outputs('Department_name'))))",
        after("Select_department_rule_roles")),
    "Filter_department_candidates": query("@outputs('Department_candidates')", "@not(empty(coalesce(item(), '')))",
                                          after("Department_candidates")),

    # ---- group roles
    "Select_group_names": select("@outputs('User_groups')", "@item()?['displayName']", after("User_groups")),
    "Select_group_ids": select("@outputs('User_groups')", "@item()?['id']", after("User_groups")),
    "Select_group_keys_lower": select("@union(body('Select_group_names'), body('Select_group_ids'))",
                                      "@toLower(trim(coalesce(item(), '')))", after("Select_group_names", "Select_group_ids")),
    "Match_group_rules": query(
        "@coalesce(variables('mapping')?['groupRoles'], json('[]'))",
        "@contains(body('Select_group_keys_lower'), toLower(trim(coalesce(item()?['group'], ''))))",
        after("Select_group_keys_lower")),
    "Select_group_rule_roles": select("@body('Match_group_rules')", "@item()?['role']", after("Match_group_rules")),
    "Select_legacy_group_roles": select("@outputs('User_groups')",
                                        "@variables('mapping')?['groupMapping']?[item()?['displayName']]", after("User_groups")),
    "Filter_file_group_roles": query("@union(body('Select_group_rule_roles'), body('Select_legacy_group_roles'))",
                                     "@not(empty(coalesce(item(), '')))",
                                     after("Select_group_rule_roles", "Select_legacy_group_roles")),
    "Match_app_role_assignments": query(
        "@variables('assignments')",
        f"@contains(union(body('Select_group_ids'), createArray({U})), item()?['principalId'])",
        after("Select_group_ids")),
    "Select_app_assignment_roles": select("@body('Match_app_role_assignments')", "@item()?['role']",
                                          after("Match_app_role_assignments")),
    "Group_roles": compose(
        "@if(equals(parameters('roleSource'), 'department'), json('[]'), "
        "if(equals(parameters('mappingMode'), 'mapped'), "
        "if(equals(variables('mapping')?['oneGroupRoleOnly'], true), take(body('Filter_file_group_roles'), 1), body('Filter_file_group_roles')), "
        "if(equals(parameters('mappingMode'), 'entraAppRoles'), body('Select_app_assignment_roles'), body('Select_group_names'))))",
        after("Filter_file_group_roles", "Select_app_assignment_roles", "Select_group_names")),

    # ---- desired roles
    "Filter_desired_roles": query(
        "@union(take(body('Filter_department_candidates'), 1), outputs('Group_roles'))",
        f"@and(not(empty(coalesce(item(), ''))), {PM_ROLES_OK})",
        after("Filter_department_candidates", "Group_roles")),
    "Desired_roles": compose(
        "@if(and(empty(body('Filter_desired_roles')), not(empty(coalesce(variables('mapping')?['defaultRole'], '')))), "
        "createArray(variables('mapping')?['defaultRole']), body('Filter_desired_roles'))",
        after("Filter_desired_roles")),

    "Check_PM_lookup_needed": cond(
        "@or(greater(length(outputs('Desired_roles')), 0), equals(parameters('updateMode'), 'managed'))",
        {
            "Get_SCIM_user": {
                "runAfter": {}, "type": "Http",
                "inputs": {
                    "method": "GET",
                    "uri": "@{parameters('scimBaseUrl')}/users?filter=@{encodeUriComponent(concat('userName eq \"', "
                           "coalesce(outputs('Current_user')?['mail'], outputs('Current_user')?['userPrincipalName']), '\"'))}",
                    "headers": {"Authorization": "Bearer @{parameters('scimApiKey')}", "Content-Type": "application/json"}}},
            "Check_PM_user_found": cond(
                "@greater(length(coalesce(body('Get_SCIM_user')?['Resources'], json('[]'))), 0)",
                pm_user_found_actions, run_after=after("Get_SCIM_user")),
        },
        run_after=after("Desired_roles")),
}

for_each_user = {
    "runAfter": after("Stop_if_setup_problem"),
    "type": "Foreach",
    "foreach": "@variables('changedUserIds')",
    "runtimeConfiguration": {"concurrency": {"repetitions": 5}},
    "actions": {
        "Get_user": graph_get(f"{GRAPH}/users/@{{{U}}}?$select=id,mail,userPrincipalName,department"),
        # 404 means the user was deleted after the change was recorded: nothing to do.
        # Any other error fails this user (json() of plain text throws, carrying the
        # message) so it is reported by Report_user_failures.
        "Check_user_exists": cond(
            "@equals(outputs('Get_user')?['statusCode'], 200)", user_found_actions,
            {"Check_lookup_error": cond(
                "@not(equals(outputs('Get_user')?['statusCode'], 404))",
                {"Fail_user_lookup": compose(
                    "@json(concat('Microsoft Graph returned HTTP ', string(outputs('Get_user')?['statusCode']), "
                    "' when looking up this user.'))")})},
            run_after=after("Get_user", statuses=("Succeeded", "Failed"))),
    },
}

# ---------------------------------------------------------------- save progress

DONE = after("For_each_changed_user", statuses=("Succeeded", "Failed"))
save_actions = {
    "Save_users_delta_token": cond(
        "@and(not(equals(parameters('roleSource'), 'groups')), not(equals(variables('usersNewDelta'), '')))",
        {"Put_users_delta_token": blob_put("state/users-delta.txt", "@variables('usersNewDelta')", "text/plain")},
        run_after=DONE),
    "Save_groups_delta_token": cond(
        "@and(not(equals(parameters('roleSource'), 'department')), not(equals(variables('groupsNewDelta'), '')))",
        {"Put_groups_delta_token": blob_put("state/groups-delta.txt", "@variables('groupsNewDelta')", "text/plain")},
        run_after=DONE),
    "Save_assignments_snapshot": cond(
        "@variables('assignmentsChanged')",
        {"Put_assignments_snapshot": blob_put("state/app-role-assignments.json", "@variables('assignments')",
                                              "application/json")},
        run_after=DONE),
    "Report_user_failures": cond(
        "@equals(actions('For_each_changed_user')?['status'], 'Failed')",
        {"Stop_with_user_failures": {
            "runAfter": {}, "type": "Terminate",
            "inputs": {"runStatus": "Failed", "runError": {
                "code": "SomeUsersFailed",
                "message": "One or more users could not be updated in Process Manager. Open this run and expand "
                           "'For_each_changed_user' to see which ones. Their changes will not be retried automatically."}}}},
        run_after=after("Save_users_delta_token", "Save_groups_delta_token", "Save_assignments_snapshot",
                        statuses=("Succeeded", "Failed", "Skipped"))),
}

# ---------------------------------------------------------------- assemble

variables = [
    ("changedUserIds", "array", []), ("runError", "string", ""), ("deltaDepartments", "object", {}),
    ("usersUrl", "string", ""), ("usersHasMore", "boolean", True), ("usersNewDelta", "string", ""),
    ("groupsUrl", "string", ""), ("groupsHasMore", "boolean", True), ("groupsNewDelta", "string", ""),
    ("mapping", "object", {}), ("controlledRoles", "array", []), ("validRolesLower", "array", []),
    ("assignments", "array", []), ("assignmentsUrl", "string", ""), ("assignmentsHasMore", "boolean", True),
    ("assignmentsChanged", "boolean", False),
]

actions = {
    "Initialize_variables": {"runAfter": {}, "type": "InitializeVariable",
                             "inputs": {"variables": [{"name": n, "type": t, "value": v} for n, t, v in variables]}},
    "Load_user_changes": load_user_changes,
    "Load_group_changes": load_group_changes,
    "Load_mapping_file": load_mapping_file,
    "Load_app_role_assignments": load_app_roles,
    "Load_existing_PM_roles": load_pm_roles,
    "Stop_if_setup_problem": stop_if_setup_problem,
    "For_each_changed_user": for_each_user,
}
actions.update(save_actions)

wf_params = {"$connections": {"defaultValue": {}, "type": "Object"}}
for name, typ in [("scimApiKey", "SecureString"), ("scimBaseUrl", "String"), ("roleSource", "String"),
                  ("mappingMode", "String"), ("entraAppId", "String"), ("updateMode", "String"),
                  ("syncExistingUsersOnFirstRun", "Bool"), ("filterToExistingRoles", "Bool"),
                  ("processManagerSiteUrl", "String"), ("processManagerUsername", "String"),
                  ("processManagerPassword", "SecureString")]:
    wf_params[name] = {"defaultValue": f"[parameters('{name}')]", "type": typ}
wf_params["blobBaseUrl"] = {"defaultValue": "[variables('blobBaseUrl')]", "type": "String"}


def p(typ, desc, default=None, allowed=None, **extra):
    d = {"type": typ}
    if default is not None:
        d["defaultValue"] = default
    if allowed:
        d["allowedValues"] = allowed
    d.update(extra)
    d["metadata"] = {"description": desc}
    return d


template = {
    "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
    "contentVersion": "2.0.0.0",
    "parameters": {
        "logicAppName": p("string", "Name of the Logic App.", "ProcessManagerSCIMSync"),
        "location": p("string", "Azure region for all resources. Defaults to the resource group's region.",
                      "[resourceGroup().location]"),
        "scimApiKey": p("securestring", "Process Manager SCIM API token (Process Manager > My Profile > Access Tokens)."),
        "roleSource": p("string", "What decides a user's Process Manager roles: their Entra ID department, their Entra ID "
                        "group memberships, or both.", "department", ["department", "groups", "both"]),
        "mappingMode": p("string", "How Entra ID values become Process Manager role names. dynamic: use the department/group "
                         "name as-is. mapped: use role-mapping.json in the storage account. entraAppRoles: use the role "
                         "assignments on an Entra ID Enterprise App (groups/both only).",
                         "dynamic", ["dynamic", "mapped", "entraAppRoles"]),
        "entraAppId": p("string", "Application (client) ID of the Enterprise App whose app roles map to Process Manager "
                        "roles. Only used when mappingMode is entraAppRoles.", ""),
        "updateMode": p("string", "managed: add roles from Entra ID and remove only roles this sync gave out (roles added "
                        "by hand in Process Manager are kept). preserve: only ever add roles. replace: make the user's "
                        "roles exactly match Entra ID.", "managed", ["managed", "preserve", "replace"]),
        "pollingIntervalMinutes": p("int", "How often (in minutes) to check Entra ID for changes.", 15,
                                    minValue=1, maxValue=60),
        "syncExistingUsersOnFirstRun": p("bool", "If true, the first run processes every user, not just users who "
                                         "change after installation.", False),
        "roleMappingStorageAccountName": p(
            "string", "Storage account for sync progress and role-mapping.json. Created if it does not exist. "
            "3-24 lowercase letters and numbers, globally unique.",
            "[concat('pmscim', uniqueString(resourceGroup().id))]"),
        "roleMappingContainerName": p("string", "Blob container for sync progress and role-mapping.json.", "config"),
        "scimBaseUrl": p("string", "Process Manager SCIM API base URL. Change only if Nintex support tells you to.",
                         "https://api.promapp.com/api/scim"),
        "filterToExistingRoles": p("bool", "If true, only roles that already exist in Process Manager are assigned, so "
                                   "Entra ID never creates new roles. Requires the three processManager* settings.", False),
        "processManagerSiteUrl": p("string", "Process Manager site URL, e.g. https://demo.promapp.com/{tenantId}. No "
                                   "trailing slash. Only used by filterToExistingRoles.", ""),
        "processManagerUsername": p("string", "Process Manager service-account username (no MFA). Only used by "
                                    "filterToExistingRoles.", ""),
        "processManagerPassword": p("securestring", "Process Manager service-account password. Only used by "
                                    "filterToExistingRoles.", ""),
    },
    "variables": {
        "storageBlobDataContributorRoleId": "ba92f5b4-2d11-453d-a403-e96b0029c9fe",
        "blobBaseUrl": "[concat('https://', parameters('roleMappingStorageAccountName'), '.blob.', "
                       "environment().suffixes.storage, '/', parameters('roleMappingContainerName'))]",
    },
    "resources": [
        {
            "type": "Microsoft.Storage/storageAccounts", "apiVersion": "2023-01-01",
            "name": "[parameters('roleMappingStorageAccountName')]", "location": "[parameters('location')]",
            "sku": {"name": "Standard_LRS"}, "kind": "StorageV2",
            "properties": {"minimumTlsVersion": "TLS1_2", "allowBlobPublicAccess": False,
                           "supportsHttpsTrafficOnly": True},
        },
        {
            "type": "Microsoft.Storage/storageAccounts/blobServices/containers", "apiVersion": "2023-01-01",
            "name": "[concat(parameters('roleMappingStorageAccountName'), '/default/', parameters('roleMappingContainerName'))]",
            "dependsOn": ["[resourceId('Microsoft.Storage/storageAccounts', parameters('roleMappingStorageAccountName'))]"],
            "properties": {"publicAccess": "None"},
        },
        {
            "type": "Microsoft.Logic/workflows", "apiVersion": "2019-05-01",
            "name": "[parameters('logicAppName')]", "location": "[parameters('location')]",
            "identity": {"type": "SystemAssigned"},
            "properties": {
                # Starts switched off: scripts/grant-permissions.sh switches it on once Microsoft
                # Graph access is granted, so it never caches a sign-in token without permissions.
                "state": "Disabled",
                "definition": {
                    "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
                    "contentVersion": "2.0.0.0",
                    "parameters": wf_params,
                    "triggers": {"Recurrence": {"type": "Recurrence", "recurrence": {
                        "frequency": "Minute", "interval": "[parameters('pollingIntervalMinutes')]"}}},
                    "actions": actions,
                    "outputs": {},
                },
                "parameters": {"$connections": {"value": {}}},
            },
        },
        {
            # Nested so the assignment's name can be derived from the managed identity's id.
            # A reinstall creates a new identity; a name based only on the Logic App's name
            # would clash with the previous identity's assignment.
            "type": "Microsoft.Resources/deployments", "apiVersion": "2022-09-01",
            "name": "[concat(parameters('logicAppName'), '-storage-access')]",
            "dependsOn": [
                "[resourceId('Microsoft.Storage/storageAccounts', parameters('roleMappingStorageAccountName'))]",
                "[resourceId('Microsoft.Logic/workflows', parameters('logicAppName'))]",
            ],
            "properties": {
                "mode": "Incremental",
                "expressionEvaluationOptions": {"scope": "inner"},
                "parameters": {
                    "storageAccountName": {"value": "[parameters('roleMappingStorageAccountName')]"},
                    "principalId": {"value": "[reference(resourceId('Microsoft.Logic/workflows', parameters('logicAppName')), "
                                             "'2019-05-01', 'full').identity.principalId]"},
                    "roleId": {"value": "[variables('storageBlobDataContributorRoleId')]"},
                },
                "template": {
                    "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
                    "contentVersion": "1.0.0.0",
                    "parameters": {"storageAccountName": {"type": "string"}, "principalId": {"type": "string"},
                                   "roleId": {"type": "string"}},
                    "resources": [{
                        "type": "Microsoft.Authorization/roleAssignments", "apiVersion": "2022-04-01",
                        "scope": "[format('Microsoft.Storage/storageAccounts/{0}', parameters('storageAccountName'))]",
                        "name": "[guid(resourceId('Microsoft.Storage/storageAccounts', parameters('storageAccountName')), "
                                "parameters('principalId'), parameters('roleId'))]",
                        "properties": {
                            "roleDefinitionId": "[subscriptionResourceId('Microsoft.Authorization/roleDefinitions', parameters('roleId'))]",
                            "principalId": "[parameters('principalId')]",
                            "principalType": "ServicePrincipal",
                        },
                    }],
                },
            },
        },
    ],
    "outputs": {
        "logicAppName": {"type": "string", "value": "[parameters('logicAppName')]"},
        "storageAccountName": {"type": "string", "value": "[parameters('roleMappingStorageAccountName')]"},
        "managedIdentityPrincipalId": {
            "type": "string",
            "value": "[reference(resourceId('Microsoft.Logic/workflows', parameters('logicAppName')), '2019-05-01', 'full').identity.principalId]"},
    },
}

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "logic-app", "azuredeploy.json")
with open(OUT, "w") as f:
    json.dump(template, f, indent=2, ensure_ascii=False)
    f.write("\n")
