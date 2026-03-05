# Mapping Modes Guide

This guide explains the two mapping modes available in the Process Manager SCIM Sync Logic App and helps you choose the right one for your organization.

Both **Department Sync** and **Group Sync** workflows support these mapping modes.

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
Do your department names in Entra ID exactly match role names in Process Manager?
├─ Yes → Use Dynamic Mode
└─ No
   ├─ Can you rename departments in Entra ID to match?
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
2. **Use Mapped Mode** when:
   - You have legacy department naming in Entra ID that can't be changed
   - You need to consolidate multiple departments to one role
   - You want a default fallback role
3. **Plan for the future**: Consider standardizing names to eventually move to Dynamic Mode
4. **Test both**: Deploy in a test environment to see which works better for your organization

## Getting Help

- For general questions: See main README.md
- For deployment issues: Check Azure Logic App run history
- For mapping file syntax: See config/role-mapping-example.json
