# Developing

Notes for people changing the sync itself. Customer-facing docs are in [`docs/`](..).

## Repository layout

| Path | What it is |
|---|---|
| `logic-app/azuredeploy.json` | ARM template: storage account, Logic App (Consumption), storage role assignment. **Generated. Don't edit by hand.** |
| `tools/generate_template.py` | Source of `azuredeploy.json`. Edit this, then run `python3 tools/generate_template.py`. |
| `logic-app/createUiDefinition.json` | The Azure Portal form behind the Deploy to Azure button. |
| `logic-app/azuredeploy.parameters.template.json` | Example parameters for `az deployment group create`. |
| `deploy.sh` | Interactive command-line installer: deploy, upload mapping file, run `grant-permissions.sh`. |
| `scripts/grant-permissions.sh` | Grants the managed identity its Microsoft Graph app roles, then enables the Logic App. |
| `scripts/create-role-app.sh` | Creates/updates the Enterprise App used by `entraAppRoles` mapping. |
| `config/role-mapping.json` | Example mapping file for `mapped` mode. |

The Deploy to Azure button points at `main` on GitHub, so template changes go live for new installs as soon as they're merged.

## How a run works

Each run (Recurrence trigger) does the following:

1. **Collect changed user IDs**
   - `Load_user_changes` (Role source department/both): follows `users/delta?$select=department`. It also keeps each user's department from the delta record (`deltaDepartments`), because Graph reads made straight after a change can return the old value.
   - `Load_group_changes` (groups/both): follows `groups/delta?$select=members` and flattens every `members@delta` entry of type user. It does this without loops: stringify each array, strip the brackets, join, then parse.
   - `Load_app_role_assignments` (`entraAppRoles`): reads all assignments on the Enterprise App and compares them with the snapshot in `state/app-role-assignments.json`. If they differ, every directly assigned user and every member of every assigned group, before and after, is added to the list.
2. **Load mapping inputs**
   - `Load_mapping_file`: reads `role-mapping.json`.
   - `Load_existing_PM_roles`: the optional role filter.
3. **`Stop_if_setup_problem`** fails the run with a readable message if any load stage failed or set `runError`. Load stages always run in sequence regardless of each other's outcome, so this check always runs.
4. **`For_each_changed_user`** (5 in parallel):
   1. Read the user from Graph (404 means deleted, so skip).
   2. Work out the desired roles.
   3. Find them in Process Manager via SCIM by `mail` (falling back to `userPrincipalName`).
   4. Compute the final role list for the update mode.
   5. `PUT` only if it differs from the current roles.
   6. In `managed` mode, save the desired roles to `state/users/{id}.json`.
5. **Save progress:** delta links and the assignment snapshot are saved even if some users failed, so one bad user can't block everyone else. `Report_user_failures` then fails the run if any user failed.

All storage access is HTTP with the managed identity (`Storage Blob Data Contributor`). There are no API connections.

### Managed update mode

Removable roles = the roles saved in `state/users/{id}.json` for that user (what the sync gave last time), plus `controlledRoles`, which is every role named in the mapping file or the Enterprise App. Final roles = (current roles − removable) ∪ desired. Comparisons are case-insensitive.

### Why the Logic App is deployed disabled

Azure caches managed-identity tokens (for up to 24 hours). If the first run fetches a Graph token before the app roles are granted, runs can keep getting 403s long after the grant. So the template deploys it `Disabled`, and `grant-permissions.sh` enables it two minutes after granting.

### Logic Apps gotchas hit while building this

- Actions inside an `If` that was skipped return `null` from `outputs()`/`body()`. This is relied on in several places.
- A handled failure (a following action with `runAfter: Failed`) doesn't fail the run. An `If` containing an unhandled failed action is itself `Failed`, which skips everything that runs only after it succeeds.
- `Terminate` isn't allowed inside loops. Errors inside `Until`/`Foreach` set a variable, and a `Terminate` outside the loop reports it.
- `$filter` user queries hit an index that lags behind; `GET /users/{id}` doesn't.

## Testing changes

There are no offline tests. Deploy to a test resource group and exercise it against a test tenant.

```bash
az group create -n rg-scim-test -l eastus
./deploy.sh      # answer with rg-scim-test
```

Useful commands:

```bash
# Trigger a run now instead of waiting
az rest --method post --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/rg-scim-test/providers/Microsoft.Logic/workflows/ProcessManagerSCIMSync/triggers/Recurrence/run?api-version=2019-05-01"

# Latest runs
az rest --method get --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/rg-scim-test/providers/Microsoft.Logic/workflows/ProcessManagerSCIMSync/runs?api-version=2019-05-01&\$top=5" \
  --query "value[].{start:properties.startTime,status:properties.status,error:properties.error.message}" -o table
```

After changing something in Entra ID, wait about a minute before triggering: the delta feeds lag slightly.

Scenarios worth covering for any change to the workflow:

| Setup | Change in Entra ID | Expect |
|---|---|---|
| department / dynamic / managed | Change department | New department role added; previous one removed if the sync gave it |
| groups / dynamic / managed | Add to one group, remove from another | Added group's role appears; removed group's role goes only if the sync gave it |
| both / mapped / managed, `oneGroupRoleOnly: true` | Change department | Department rule applied (case-insensitive); only the first matching group rule applied; rules can match by group Object ID |
| groups / entraAppRoles / managed | Assign a group and a user to app roles, then remove one | Roles appear via group and direct assignment; removed assignment's role goes on the next run |
| entraAppRoles with a wrong app ID | none | Run **fails** with "Could not read the Enterprise App's roles" |
| Fresh install with `deploy.sh` | none | Deploys disabled, grants permissions, enables; first run succeeds |
