# Quick Start Guide

Get your Process Manager SCIM sync running in 15 minutes!

## What You'll Need

Before starting, gather:

1. **Azure subscription** with permissions to create resources
2. **Process Manager SCIM API Key**
   Find it in Process Manager: Admin → SCIM → API Key
3. **Entra ID admin access** to authorize API connections

## Installation

### Option 1: Automated Deployment (Recommended)

Run the automated deployment script:

```bash
./deploy.sh
```

The script will prompt you for:
- Resource group name
- Azure region
- SCIM API key
- Mapping mode (dynamic vs mapped)
- Update mode (preserve vs replace)

Then it will automatically:
- Create all Azure resources
- Configure the Logic App
- Upload configuration files

**Time:** ~5-10 minutes

### Option 2: Manual Deployment

Follow the detailed steps in [DEPLOY.md](./DEPLOY.md) if you prefer manual control.

**Time:** ~15-20 minutes

## Post-Installation Setup

After deployment completes:

### 1. Authorize Office 365 Connection

The Logic App needs permission to read Entra ID user and group data:

1. Go to the [Azure Portal](https://portal.azure.com)
2. Navigate to **Resource Groups** → **rg-processmanager-scim** (or your resource group name)
3. Click on the API Connection named **office365-xxxxx**
4. Click **Edit API connection**
5. Click **Authorize**
6. Sign in with your Entra ID admin account
7. Click **Save**

### 2. Verify Logic App is Running

```bash
az logic workflow show \
  --resource-group rg-processmanager-scim \
  --name ProcessManagerSCIMSync \
  --query state
```

Should return `"Enabled"`

## Testing

### Test Department Sync

1. **Update a user's department** in Entra ID:
   - Go to Azure AD → Users → Select a user
   - Update the "Department" field
   - Save

2. **Check Process Manager**:
   - Log into Process Manager
   - Go to Admin → Users
   - Find the user
   - Verify their role matches the department

### Test Group Sync

1. **Add a user to a group** in Entra ID:
   - Go to Azure AD → Groups → Select a group
   - Add Members → Add the user
   - Save

2. **Check Process Manager**:
   - The user should now have a role matching the group name
   - If using mapped mode, the role will be the mapped value from role-mapping.json

## Configuration Modes

### Dynamic Mode (Default)

Department and group names are used directly as role names.

**Example:**
- User's department: "Engineering"
- User is member of: "ProcessManager-Admins"
- Roles assigned: "Engineering", "ProcessManager-Admins"

**Best for:** Organizations where Entra ID names match Process Manager role names exactly.

### Mapped Mode

Use `config/role-mapping.json` to map Entra ID names to Process Manager roles.

**Example configuration:**
```json
{
  "departmentMapping": {
    "Eng": "Engineering Team",
    "HR": "Human Resources",
    "_default": "Standard User"
  },
  "groupMapping": {
    "PM-Admins": "Administrator",
    "PM-Editors": "Process Editor",
    "_default": "Standard User"
  }
}
```

**Best for:** Organizations with different naming conventions or complex mappings.

## Update Modes

### Preserve Mode (Default)

Adds department/group roles while keeping existing roles.

**Example:**
- User currently has: "Admin"
- Department/groups map to: "Engineering", "Process Editor"
- Final roles: "Admin", "Engineering", "Process Editor"

### Replace Mode

Replaces all roles with only department/group roles.

**Example:**
- User currently has: "Admin", "Custom Role"
- Department/groups map to: "Engineering", "Process Editor"
- Final roles: "Engineering", "Process Editor"

## Monitoring

### View Recent Runs

```bash
az logic workflow run list \
  --resource-group rg-processmanager-scim \
  --name ProcessManagerSCIMSync \
  --top 5
```

### View in Azure Portal

1. Go to your Logic App in the Azure Portal
2. Click **Overview**
3. See run history with success/failure status
4. Click any run to see detailed execution steps

## Troubleshooting

### Logic App not triggering

**Check Office 365 connection authorization:**
```bash
az resource show \
  --ids $(az logic workflow show \
    --resource-group rg-processmanager-scim \
    --name ProcessManagerSCIMSync \
    --query "parameters.\$connections.value.office365users.connectionId" -o tsv) \
  --query properties.statuses
```

**Solution:** Re-authorize the Office 365 connection (see Post-Installation Setup above)

### Roles not updating

1. **Check run history** for errors
2. **Verify role names match exactly** (case-sensitive)
3. **For dynamic mode:** Department/group names must match Process Manager role names exactly
4. **For mapped mode:** Check `config/role-mapping.json` has correct mappings

### User not found in SCIM

1. **Verify user exists** in Process Manager
2. **Check email matches:** Entra ID email must match Process Manager userName
3. **Test SCIM API directly:**
   ```bash
   curl -H "Authorization: Bearer YOUR_API_KEY" \
     "https://api.promapp.com/api/scim/users?filter=userName%20eq%20%22user@domain.com%22"
   ```

## Common Scenarios

### Scenario 1: New employee onboarding

1. Create user in Entra ID with department set
2. Add user to relevant groups
3. Logic App automatically assigns roles in Process Manager
4. User can log into Process Manager with correct permissions

### Scenario 2: Employee department change

1. Update user's department in Entra ID
2. Logic App detects change and updates roles
3. Old department role remains (preserve mode) or is removed (replace mode)
4. New department role is added

### Scenario 3: Bulk role assignment

1. Create a group in Entra ID (e.g., "ProcessManager-Editors")
2. Add multiple users to the group
3. Update any field on each user (or wait for next user update)
4. All users get the corresponding role

## Next Steps

- **Configure custom mappings:** Edit `config/role-mapping.json` if using mapped mode
- **Set up monitoring:** Configure Azure Monitor alerts for failed runs
- **Review documentation:** See [README.md](./README.md) for complete documentation
- **Test thoroughly:** See [TESTING.md](./TESTING.md) for comprehensive testing procedures

## Getting Help

- **Logic App issues:** Check run history in Azure Portal
- **SCIM API errors:** Contact Nintex/Promapp support
- **General questions:** See [README.md](./README.md)

## Cost

Typical costs for 1000 user updates per month: **~$1-2/month**

- Logic Apps: ~$1.25/month
- Storage Account: <$0.01/month
- API Connections: Free

## Security Notes

- ✅ SCIM API key is stored securely as a Logic App parameter
- ✅ Office 365 connection uses OAuth (no stored passwords)
- ✅ All traffic uses HTTPS
- ⚠️ Anyone with access to the Logic App can view the SCIM API key
- 💡 Consider using Azure Key Vault for enhanced security in production

---

**Congratulations!** Your Process Manager SCIM sync is now running. Users' departments and group memberships will automatically sync to Process Manager roles.
