# Mapping Modes Guide

This guide explains the two mapping modes available in the Process Manager SCIM Sync Logic App and helps you choose the right one for your organization.

Both **Department Sync** and **Group Sync** workflows support these mapping modes.

> **Important — preventing AD groups from creating new roles in Process Manager**
>
> If your concern is that every AD group a user belongs to gets pushed into Process Manager as a new role (causing role bloat), enable the **Role Filter** feature described in [Filtering to Existing Process Manager Roles](#filtering-to-existing-process-manager-roles). With the filter enabled, only departments/groups whose names already exist as roles in Process Manager are synced. This works in **both** dynamic and mapped mode, and dynamic mode + filter is the recommended combination for this use case.

## Quick Comparison

| Feature | Dynamic Mode | Mapped Mode |
|---------|--------------|-------------|
| **Setup Complexity** | Minimal | Requires configuration file |
| **Maintenance** | None | Update mapping file as needed |
| **Use Case** | 1:1 department-to-role matching | Custom or complex mappings |
| **Configuration File** | Not required | Required (role-mapping.json) |
| **Department Rename** | Update in both Entra ID and Process Manager | Update only in mapping file |
| **Default Fallback** | No fallback | Configurable default role |
| **Recommended For** | Most organizations | Organizations with naming inconsistencies |

## Dynamic Mode (Recommended)

### How It Works

The department or group name from Entra ID is used directly as the role name in Process Manager.

**Department Sync Example:**
```
Entra ID User:
  Department: "Engineering"
       ↓
Logic App:
  Uses "Engineering" directly
       ↓
Process Manager:
  Assigns role: "Engineering"
```

**Group Sync Example:**
```
Entra ID User Groups:
  Member of: "ProcessManager-Admins"
       ↓
Logic App:
  Uses "ProcessManager-Admins" directly
       ↓
Process Manager:
  Assigns role: "ProcessManager-Admins"
```

### Requirements

1. **Exact name matching**: Department names in Entra ID must exactly match role names in Process Manager
2. **Case-sensitive**: "Engineering" ≠ "engineering"
3. **Roles must exist**: All department names must have corresponding roles already created in Process Manager

### Advantages

- **Simple**: No configuration file to manage
- **Direct**: What you see in Entra ID is what gets assigned
- **Fast**: One less API call (no blob storage lookup)
- **Transparent**: Easy to understand and troubleshoot

### Disadvantages

- **Inflexible**: Can't map multiple departments to one role
- **No fallback**: Users without departments get no role assigned
- **Naming constraints**: You're locked into using the same names in both systems

### Best For

- Organizations with consistent naming conventions
- Small to medium deployments where you control both Entra ID and Process Manager
- Teams that prefer simplicity over flexibility

### Example Configuration

In your deployment parameters:
```json
{
  "mappingMode": {
    "value": "dynamic"
  }
}
```

That's it! No additional configuration needed.

## Mapped Mode

### How It Works

The Logic App looks up the department or group in a configuration file (`role-mapping.json`) and uses the mapped value as the role name.

**Department Sync Example:**
```
Entra ID User:
  Department: "Eng"
       ↓
Logic App:
  Looks up in role-mapping.json
  departmentMapping: "Eng" → "Engineering Team"
       ↓
Process Manager:
  Assigns role: "Engineering Team"
```

**Group Sync Example:**
```
Entra ID User Groups:
  Member of: "PM-Editors"
       ↓
Logic App:
  Looks up in role-mapping.json
  groupMapping: "PM-Editors" → "Process Editor"
       ↓
Process Manager:
  Assigns role: "Process Editor"
```

### Requirements

1. **Mapping file**: Must upload `role-mapping.json` to Azure Blob Storage
2. **Maintenance**: Update mapping file when departments or roles change
3. **Default role**: Configure `_default` for unmapped departments

### Advantages

- **Flexible**: Map any department name to any role name
- **Many-to-one**: Multiple departments can map to the same role
- **Fallback**: Default role for unmapped departments
- **Independence**: Change mappings without touching Entra ID or Process Manager
- **Gradual rollout**: Add departments to mapping as you onboard teams

### Disadvantages

- **More complex**: Additional configuration file to manage
- **Extra API call**: Fetches mapping from blob storage on each run
- **Maintenance overhead**: Must update mapping file when departments change
- **Indirection**: Harder to troubleshoot (department → mapping → role)

### Best For

- Organizations with inconsistent naming between systems
- Large deployments with many departments
- Scenarios where department names can't be changed in Entra ID
- Organizations that need multiple departments to share the same role

### Example Configuration

**Deployment parameters:**
```json
{
  "mappingMode": {
    "value": "mapped"
  }
}
```

**role-mapping.json:**
```json
{
  "departmentMapping": {
    "Eng": "Engineering Team",
    "Engineering": "Engineering Team",
    "Dev": "Engineering Team",
    "Sales Dept": "Sales",
    "Sales - West": "Sales",
    "Sales - East": "Sales",
    "HR": "Human Resources",
    "_default": "Standard User"
  },
  "groupMapping": {
    "PM-Admins": "Administrator",
    "PM-Editors": "Process Editor",
    "PM-Viewers": "Process Viewer",
    "Engineering-Team": "Engineering Team",
    "_default": "Standard User"
  }
}
```

In this example:
- **Department Mapping:** "Eng", "Engineering", and "Dev" all map to "Engineering Team"
- **Department Mapping:** Both sales departments map to "Sales"
- **Group Mapping:** "PM-Admins" maps to "Administrator"
- **Group Mapping:** "PM-Editors" maps to "Process Editor"
- Any unmapped department or group gets "Standard User"

## Filtering to Existing Process Manager Roles

By default, the Logic App sends every department and group name (dynamic mode) or every mapped role name (mapped mode) to Process Manager via SCIM. Because the SCIM `PUT` implicitly creates roles that don't exist yet, this can cause unwanted role proliferation — every AD group a user belongs to becomes a new role in Process Manager.

The **role filter** feature solves this by fetching the current list of roles from Process Manager at the start of each run and only syncing departments/groups whose names already exist there. Everything else is silently dropped.

### Recommended: Dynamic Mode + Role Filter

For the "keep Entra ID and Process Manager in sync without creating new roles" use case, the recommended configuration is:

- `mappingMode: dynamic`
- `filterToExistingRoles: true`
- Provide `processManagerSiteUrl`, `processManagerUsername`, `processManagerPassword`

**Flow:**
```
Entra ID user: Department = "IT-Service-Desk", member of 12 AD groups
       ↓
Logic App fetches list of roles from Process Manager:
  ["Account Manager", "CEO", "Finance", "IT-Service-Desk", "Sales", ...]
       ↓
Filter user's department + groups against the list:
  Kept:    "IT-Service-Desk" (matches)
  Dropped: 11 AD groups that don't exist as roles in PM
       ↓
Process Manager: user is assigned "IT-Service-Desk" only
```

The user's other 11 AD groups are never pushed to Process Manager, so no new roles are created.

### How It Works

When `filterToExistingRoles` is `true` AND `processManagerSiteUrl` is non-empty, every run of the Logic App:

1. **Fetches an OAuth token** — `POST {processManagerSiteUrl}/oauth2/token` with `grant_type=password` using the provided username/password. Returns a short-lived bearer token.
2. **Fetches the roles HTML** — `GET {processManagerSiteUrl}/Lookup/AssociateRoles.aspx` with the bearer token. Returns an HTML document containing all existing Process Manager roles.
3. **Parses role names** — extracts each role label, decodes common HTML entities (`&amp; &#39; &quot; &nbsp; &#246;`), trims, and lowercases them. Stored in the `validRolesLower` variable for the run.
4. **Filters during mapping:**
   - **Dynamic mode** — department and each group's displayName are dropped unless their lowercased/trimmed value appears in `validRolesLower`.
   - **Mapped mode** — the *mapped output* (e.g. the value from `departmentMapping["Eng"]`, or the `_default`) is dropped unless it exists in `validRolesLower`. This means mapped mode also won't create new PM roles via the `_default` fallback.
5. **Matching is case-insensitive and whitespace-trimmed.** "IT-Service-Desk", "it-service-desk", and " IT-Service-Desk " all match the same PM role.

### Configuration

**Deployment parameters:**

```json
{
  "mappingMode":           { "value": "dynamic" },
  "filterToExistingRoles": { "value": true },
  "processManagerSiteUrl":  { "value": "https://{tenant}.promapp.com/{tenantId}" },
  "processManagerUsername": { "value": "svc-scim-sync@example.com" },
  "processManagerPassword": { "value": "..." }
}
```

**Notes:**
- `processManagerSiteUrl` has **no trailing slash**. The Logic App appends `/oauth2/token` and `/Lookup/AssociateRoles.aspx`.
- `processManagerUsername` / `processManagerPassword` should belong to a **dedicated service account** in Process Manager, not a real user. The account needs permission to view the roles list.
- `processManagerPassword` is an ARM `securestring` — encrypted in deployment history, but readable by anyone with read access to the Logic App definition at runtime. For production, reference an Azure Key Vault secret in your parameters file instead of inlining the password.
- If `filterToExistingRoles` is `false` (the default) or `processManagerSiteUrl` is empty, the fetch is skipped and behavior is unchanged (everything passes through).

### Behavior When the Fetch Fails

- **Token request fails** (bad credentials, locked account, MFA enforced) — the Logic App run fails at the `Get_PM_oauth_token` action. No users are synced until the credentials are fixed. This is deliberately noisy so that stale/broken credentials don't silently allow role bloat.
- **Roles HTML fetch fails** (Process Manager down, network error, unauthorized) — same: the run fails.
- **HTML parse returns zero roles** — `validRolesLower` is empty, and the filter expressions treat an empty list as "no filter" and pass everything through. This is a safety fallback but also a **silent failure mode** you should monitor for. If the Nintex team ever changes the HTML structure of the roles page, filtering will stop working without error. See [Monitoring the Filter](#monitoring-the-filter) below.

### Dynamic Mode vs. Mapped Mode With the Filter On

| | Dynamic + Filter | Mapped + Filter |
|---|---|---|
| **What gets synced** | Any AD group/department whose name exactly matches a PM role name (case-insensitive, trimmed) | Any AD group/department that maps (via `role-mapping.json`) to a name that exists in PM |
| **New roles in PM** | Never | Never — even the `_default` fallback is dropped if it doesn't exist |
| **Best for** | Simple 1:1 name alignment between Entra ID and PM | Naming mismatches you can't fix, or consolidating multiple AD groups to one PM role |
| **Maintenance** | None | Update `role-mapping.json` when either side changes |
| **Extra API calls per run** | 2 (OAuth token + roles HTML) | 3 (OAuth token + roles HTML + blob storage read) |

Both combinations solve the "don't create new roles" concern. Pick dynamic unless you have a concrete mapping reason to use mapped.

### Monitoring the Filter

The filter relies on parsing an undocumented HTML endpoint (`/Lookup/AssociateRoles.aspx`), which is designed for Process Manager's UI — not as a public API. If Nintex changes attribute order or HTML structure, the parser may start returning zero roles, at which point the filter silently becomes a no-op.

**Recommended safeguards:**
1. After a Logic App run, inspect the `Set_valid_roles_lower` action's output and confirm `validRolesLower` has a reasonable count of roles (e.g. dozens or hundreds).
2. Set an Azure Monitor alert for Logic App runs where `Set_valid_roles_lower` output length is below a threshold (e.g. `< 10`).
3. If Nintex ever publishes a proper JSON roles API, switch to it — the current HTML parser is fragile by design.

### Limitations and Caveats

1. **Password-grant OAuth flow.** The Logic App uses `grant_type=password` because that's what Process Manager's token endpoint supports. This is considered legacy by modern OAuth specs. If the service account has MFA enforced, the flow will fail outright.
2. **Service account lockout risk.** If the password is wrong, every polling run (every few minutes) will hit the token endpoint with bad credentials. Depending on your tenant's lockout policy, this could lock the account. Rotate passwords during a maintenance window.
3. **Limited HTML entity decoding.** Only `&amp;`, `&#39;`, `&quot;`, `&nbsp;`, and `&#246;` are decoded. PM role names containing other numeric or named entities (e.g. `&#241;` for `ñ`) will fail to match. Extend the decode chain in the workflow's `Extract_PM_role_names` Select action if your roles use additional entities.
4. **No normalization beyond `trim()` and `toLower()`.** Multiple internal spaces, curly quotes, em-dashes vs. hyphens, zero-width characters, etc. are *not* normalized. If you hit a mismatch, the fix is either renaming in one of the two systems or extending the normalization chain.
5. **Extra tokens per run.** In `azuredeploy.json` (delta polling), one token is fetched per polling interval. In `azuredeploy-separate.json` (webhooks), one token is fetched per user update or group change event. High-volume tenants may want to consider caching, which is not implemented today.

### Troubleshooting the Filter

| Symptom | Likely Cause | Fix |
|---|---|---|
| Logic App fails at `Get_PM_oauth_token` with 400/401 | Wrong username, password, or site URL | Verify credentials directly with `curl` against `{siteUrl}/oauth2/token` |
| Logic App fails at `Get_PM_roles_html` with 401 | Token not accepted — service account may lack permission | Log into Process Manager as the service account and confirm they can view the roles list |
| User is synced but expected role isn't assigned | The AD group/department name doesn't exist as a role in PM (or matches after normalization) | Inspect `Set_valid_roles_lower` output and look for the expected role (lowercased/trimmed) |
| *No* users are being synced anymore | `validRolesLower` might be returning empty due to HTML structure change | Inspect `Set_valid_roles_lower` output; if empty, the parser is broken and you may need to extend `Extract_PM_role_names` |
| Service account keeps getting locked | Password wrong and polling runs hammer the token endpoint | Temporarily set `filterToExistingRoles: false`, fix credentials, re-enable |

## Migration Between Modes

You can switch between modes by redeploying the Logic App with a different `mappingMode` parameter.

### From Dynamic to Mapped

1. Create your `role-mapping.json` file
2. Upload it to Azure Blob Storage:
   ```bash
   az storage blob upload \
     --account-name $STORAGE_ACCOUNT \
     --account-key $STORAGE_KEY \
     --container-name config \
     --name role-mapping.json \
     --file ./config/role-mapping.json
   ```
3. Update deployment parameter to `"mappingMode": "mapped"`
4. Redeploy the Logic App

### From Mapped to Dynamic

1. Ensure all department names in Entra ID match role names in Process Manager
2. Update deployment parameter to `"mappingMode": "dynamic"`
3. Redeploy the Logic App
4. (Optional) Delete the mapping file from blob storage

**Note:** The mapping file will remain in storage but won't be used in dynamic mode.

## Decision Tree

Use this flowchart to choose the right mode:

```
Do you want to prevent AD groups/departments from creating NEW roles in Process Manager?
├─ Yes → Enable filterToExistingRoles (see "Filtering to Existing Process Manager Roles")
│        Then pick dynamic or mapped below.
└─ No  → Leave filterToExistingRoles = false.

Do your department/group names in Entra ID exactly match role names in Process Manager?
├─ Yes → Use Dynamic Mode
└─ No
   ├─ Can you rename departments/groups in Entra ID to match?
   │  ├─ Yes → Rename and use Dynamic Mode
   │  └─ No → Use Mapped Mode
   └─ Or: Can you rename roles in Process Manager to match?
      ├─ Yes → Rename and use Dynamic Mode
      └─ No → Use Mapped Mode
```

## Real-World Examples

### Example 1: Tech Startup (Dynamic Mode)

**Scenario:** Small startup with consistent naming

**Entra ID Departments:**
- Engineering
- Sales
- Marketing
- Operations

**Process Manager Roles:**
- Engineering
- Sales
- Marketing
- Operations

**Solution:** Dynamic mode - perfect 1:1 match

---

### Example 2: Enterprise with Acquisitions (Mapped Mode)

**Scenario:** Company acquired multiple businesses, each with their own department naming conventions

**Entra ID Departments:**
- Engineering (original company)
- Eng (Company A)
- Development (Company B)
- R&D (Company C)

**Process Manager Roles:**
- Engineering Team

**Solution:** Mapped mode - consolidate all engineering departments to one role
```json
{
  "departmentMapping": {
    "Engineering": "Engineering Team",
    "Eng": "Engineering Team",
    "Development": "Engineering Team",
    "R&D": "Engineering Team"
  }
}
```

---

### Example 3: Regional Organization (Mapped Mode)

**Scenario:** Company with regional sales teams that should all have the same Process Manager role

**Entra ID Departments:**
- Sales - North America
- Sales - Europe
- Sales - Asia Pacific

**Process Manager Roles:**
- Sales

**Solution:** Mapped mode - consolidate regions
```json
{
  "departmentMapping": {
    "Sales - North America": "Sales",
    "Sales - Europe": "Sales",
    "Sales - Asia Pacific": "Sales"
  }
}
```

## Troubleshooting by Mode

### Dynamic Mode Issues

**Problem:** User not getting role assigned

**Checklist:**
- [ ] Department field is populated in Entra ID
- [ ] Role with exact department name exists in Process Manager
- [ ] Names match exactly (case-sensitive)
- [ ] No extra spaces or special characters

**Example:**
```
✗ Entra ID: "Engineering " (trailing space)
  Process Manager: "Engineering"
  Result: No match

✓ Entra ID: "Engineering"
  Process Manager: "Engineering"
  Result: Match!
```

### Mapped Mode Issues

**Problem:** User not getting role assigned

**Checklist:**
- [ ] role-mapping.json is uploaded to blob storage
- [ ] Department key exists in mapping file
- [ ] Mapped role exists in Process Manager
- [ ] `_default` is configured for unmapped departments

**Example:**
```
Entra ID Department: "Customer Support"
role-mapping.json: (doesn't contain "Customer Support")

✗ Without _default: No role assigned
✓ With "_default": "Standard User": Gets "Standard User"
```

## Performance Considerations

### Dynamic Mode
- **Faster**: One less API call (no blob storage lookup)
- **Lower cost**: No blob storage read operations
- **More reliable**: Fewer moving parts

### Mapped Mode
- **Slightly slower**: Additional blob storage read
- **Cached**: Mapping file is cached by Azure for performance
- **Minimal impact**: <100ms difference in typical scenarios

For most organizations, the performance difference is negligible.

## Recommendations

1. **Start with Dynamic Mode** if possible - it's simpler and easier to maintain
2. **Enable `filterToExistingRoles`** if you don't want AD groups/departments to create new roles in Process Manager. This is the recommended combination for most customers: **Dynamic Mode + Role Filter**.
3. **Use Mapped Mode** when:
   - You have legacy department naming in Entra ID that can't be changed
   - You need to consolidate multiple departments to one role
   - You want a default fallback role
4. **Plan for the future**: Consider standardizing names to eventually move to Dynamic Mode
5. **Test both**: Deploy in a test environment to see which works better for your organization

## Getting Help

- For general questions: See main README.md
- For deployment issues: Check Azure Logic App run history
- For mapping file syntax: See config/role-mapping-example.json
