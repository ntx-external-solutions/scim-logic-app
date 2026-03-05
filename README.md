# Azure Logic App - Process Manager SCIM Sync

Automatically sync Entra ID departments and group memberships to Process Manager roles.

[![Azure](https://img.shields.io/badge/Azure-Logic%20Apps-0078D4?logo=microsoft-azure)](https://azure.microsoft.com/en-us/products/logic-apps)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## What It Does

This Azure Logic App automatically assigns Process Manager roles based on:
- ✅ User's **department** in Entra ID
- ✅ User's **group memberships** in Entra ID

When a user is updated in Entra ID, this Logic App:
1. Retrieves the user's department and all group memberships
2. Maps them to Process Manager roles (directly or via configuration)
3. Updates the user's roles in Process Manager via SCIM API

## Quick Start

```bash
# Clone or download this repository
git clone <repository-url>

# Run the automated deployment
./deploy.sh
```

See [QUICKSTART.md](./QUICKSTART.md) for a complete 15-minute setup guide.

## Overview

This Azure Logic App provides a workaround for the missing PATCH support in Process Manager's SCIM API.

### How It Works

When a user is updated in Entra ID, the Logic App:

1. **Detects** the user update via webhook trigger
2. **Retrieves** the user's department AND all group memberships from Entra ID
3. **Maps** both department and groups to Process Manager roles (dynamic or mapped mode)
4. **Combines** all roles without duplicates
5. **Queries** the SCIM API to find the user
6. **Updates** the user's roles in Process Manager using a single PUT request

## Architecture

```
Entra ID User Update
         ↓
   Webhook Trigger
         ↓
   Get User Profile & Group Memberships
         ↓
 Map Department + Groups → Roles
         ↓
   Combine All Roles
         ↓
  Find User in SCIM API
         ↓
Update User with All Roles
```

**Key Features:**
- Single unified workflow
- Combines department and group-based roles
- Automatic deduplication
- Configurable mapping modes
- Preserve or replace existing roles

## Mapping Modes

The Logic App supports two modes for mapping Entra ID departments and groups to Process Manager roles:

### Dynamic Mode (Recommended)

Uses the Entra ID department name or group name directly as the Process Manager role name. This provides a 1:1 mapping with no configuration file needed.

**Use when:**
- Your department names in Entra ID exactly match role names in Process Manager
- Your group names in Entra ID exactly match role names in Process Manager
- You want simple, straightforward mapping with no overhead
- You don't need flexible or custom mappings

**Examples:**
- Entra ID Department: "Engineering" → Process Manager Role: "Engineering"
- Entra ID Group: "ProcessManager-Admins" → Process Manager Role: "ProcessManager-Admins"

### Mapped Mode

Uses a configuration file (`role-mapping.json`) to map department names and group names to role names. This provides flexibility when names don't match or you need custom mappings.

**Use when:**
- Department/group names in Entra ID differ from role names in Process Manager
- You need multiple departments/groups to map to the same role
- You want a default/fallback role for unmapped departments/groups

**Examples:**
- Entra ID Department: "Eng" → Mapped to Process Manager Role: "Engineering Team"
- Entra ID Group: "PM-Editors" → Mapped to Process Manager Role: "Process Editor"

## Prerequisites

1. **Azure Subscription** with permissions to create:
   - Logic Apps
   - Storage Accounts
   - API Connections

2. **Entra ID (Azure AD)** with:
   - Global Administrator or appropriate permissions to set up webhooks
   - Users with the "Department" field populated

3. **Process Manager SCIM API**:
   - SCIM API enabled in your Process Manager instance
   - Valid Bearer token (API key)
   - Roles configured that match your mapping

4. **Azure CLI** or **Azure PowerShell** installed locally

## Deployment Steps

### Step 1: Create Storage Account for Configuration

The role mapping configuration needs to be stored in Azure Blob Storage.

```bash
# Set your variables
RESOURCE_GROUP="rg-processmanager-scim"
LOCATION="eastus"
STORAGE_ACCOUNT="pmscimconfig$(date +%s)"  # Must be globally unique
CONTAINER_NAME="config"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create storage account
az storage account create \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS \
  --kind StorageV2

# Get storage account key
STORAGE_KEY=$(az storage account keys list \
  --resource-group $RESOURCE_GROUP \
  --account-name $STORAGE_ACCOUNT \
  --query '[0].value' -o tsv)

# Create container
az storage container create \
  --name $CONTAINER_NAME \
  --account-name $STORAGE_ACCOUNT \
  --account-key $STORAGE_KEY
```

### Step 2: Upload Role Mapping Configuration (Mapped Mode Only)

**Note:** Skip this step if you're using **dynamic mode** (recommended for 1:1 department-to-role mapping).

```bash
# Upload the role mapping file (only needed for mapped mode)
az storage blob upload \
  --account-name $STORAGE_ACCOUNT \
  --account-key $STORAGE_KEY \
  --container-name $CONTAINER_NAME \
  --name role-mapping.json \
  --file ./config/role-mapping.json
```

**Important:** Edit `config/role-mapping.json` to match your organization's departments and Process Manager roles before uploading.

### Step 3: Update Deployment Parameters

Edit `logic-app/azuredeploy.parameters.json`:

```json
{
  "parameters": {
    "logicAppName": {
      "value": "ProcessManagerSCIMSync"
    },
    "scimApiKey": {
      "value": "YOUR_SCIM_BEARER_TOKEN_HERE"
    },
    "roleMappingStorageAccountName": {
      "value": "pmscimconfig1234567890"
    },
    "roleMappingContainerName": {
      "value": "config"
    },
    "updateMode": {
      "value": "preserve"
    },
    "mappingMode": {
      "value": "dynamic"
    }
  }
}
```

**Parameters:**
- `scimApiKey`: Your Process Manager SCIM Bearer token (found in Admin → SCIM)
- `roleMappingStorageAccountName`: The storage account name from Step 1
- `mappingMode`:
  - `dynamic`: Use department name directly as role (1:1 mapping) - **Recommended**
  - `mapped`: Use role-mapping.json for custom mappings
- `updateMode`:
  - `preserve`: Adds the department role while keeping existing roles
  - `replace`: Replaces all roles with only the department role

### Step 4: Deploy the Logic App

```bash
# Deploy using Azure CLI
az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file ./logic-app/azuredeploy.json \
  --parameters ./logic-app/azuredeploy.parameters.json
```

### Step 5: Authorize API Connections

After deployment, you need to authorize the Office 365 connection:

1. Go to the Azure Portal
2. Navigate to your Resource Group
3. Find the API Connection resource named `office365-xxxxx`
4. Click **Edit API connection**
5. Click **Authorize** and sign in with your Entra ID admin account
6. Click **Save**

### Step 6: Enable the Logic App

The Logic App should start automatically. Verify it's enabled:

```bash
az logic workflow show \
  --resource-group $RESOURCE_GROUP \
  --name ProcessManagerSCIMSync \
  --query "state"
```

Expected output: `"Enabled"`

## Configuration

### Dynamic Mode (Default)

No additional configuration needed! The Logic App uses the Entra ID department name directly as the Process Manager role.

**Requirements:**
- Department names in Entra ID must exactly match role names in Process Manager
- Case-sensitive matching

### Mapped Mode Configuration

**Only needed if you set `mappingMode` to `"mapped"`**

The `config/role-mapping.json` file controls how Entra ID departments and groups map to Process Manager roles:

```json
{
  "departmentMapping": {
    "Eng": "Engineering Team",
    "Sales Dept": "Sales Team",
    "HR": "Human Resources",
    "_default": "Standard User"
  },
  "groupMapping": {
    "ProcessManager-Admins": "Administrator",
    "ProcessManager-Editors": "Process Editor",
    "ProcessManager-Viewers": "Process Viewer",
    "_default": "Standard User"
  }
}
```

- **departmentMapping**: Maps Entra ID department names to Process Manager roles
- **groupMapping**: Maps Entra ID group names to Process Manager roles
- **Keys**: Exact department/group name from Entra ID
- **Values**: Exact role display name from Process Manager
- **_default**: Fallback role when no mapping is found

To update the mapping after deployment:

```bash
# Edit the file locally, then re-upload
az storage blob upload \
  --account-name $STORAGE_ACCOUNT \
  --account-key $STORAGE_KEY \
  --container-name $CONTAINER_NAME \
  --name role-mapping.json \
  --file ./config/role-mapping.json \
  --overwrite
```

The Logic App will use the updated mapping on the next trigger (no restart needed).

## How Department and Group Sync Work Together

Both workflows can run simultaneously and complement each other:

**Preserve Mode (Default):**
- Department sync adds department-based role
- Group sync adds group-based roles
- All roles are combined (no duplicates)
- Example: User in "Engineering" department + "ProcessManager-Admins" group gets both "Engineering" and "Administrator" roles

**Replace Mode:**
- Whichever workflow runs last will replace all roles
- Not recommended when using both department and group sync together
- Best for single-source-of-truth scenarios

**Recommended Configuration:**
- Use **Preserve Mode** when using both department and group sync
- Use **Mapped Mode** with explicit mappings to control exactly which groups/departments assign which roles

## Update Modes

### Preserve Mode (Default)
Adds the department/group-based role without removing existing roles.

**Example:**
- User has roles: `["Admin", "Process Editor"]`
- Department maps to: `"Engineering Team"`
- Result: `["Admin", "Process Editor", "Engineering Team"]`

### Replace Mode
Replaces all existing roles with only the department role.

**Example:**
- User has roles: `["Admin", "Process Editor"]`
- Department maps to: `"Engineering Team"`
- Result: `["Engineering Team"]`

To change modes, update the `updateMode` parameter and redeploy.

## Monitoring

### View Logic App Runs

```bash
# List recent runs
az logic workflow run list \
  --resource-group $RESOURCE_GROUP \
  --name ProcessManagerSCIMSync \
  --top 10

# View specific run details
az logic workflow run show \
  --resource-group $RESOURCE_GROUP \
  --name ProcessManagerSCIMSync \
  --run-name <run-id>
```

### Azure Portal Monitoring

1. Navigate to your Logic App in the Azure Portal
2. Click **Overview** to see run history
3. Click on any run to see detailed execution steps
4. Check for failed runs and error messages

### Common Issues

**Logic App not triggering:**
- Verify the Office 365 API connection is authorized
- Check that the webhook subscription is active in Entra ID
- Ensure the Logic App is in "Enabled" state

**User not found in SCIM:**
- Verify the user exists in Process Manager
- Check that the email in Entra ID matches the userName in SCIM
- Ensure the SCIM API key is valid

**Role not updating:**
- **Dynamic mode**: Verify the department/group name in Entra ID exactly matches the role name in Process Manager (case-sensitive)
- **Mapped mode**: Verify the role name in the mapping file exactly matches Process Manager
- Check that the role exists in Process Manager
- Review the Logic App run history for specific error messages
- For group sync: Verify the user is actually a member of the expected groups

**Authentication errors:**
- Verify the SCIM API key is correct and not expired
- Check that the API key has appropriate permissions

## Testing

See `TESTING.md` for detailed testing procedures.

## Cleanup

To remove all resources:

```bash
az group delete --name $RESOURCE_GROUP --yes --no-wait
```

## Security Considerations

1. **API Key Storage**: The SCIM API key is stored as a secure parameter in the Logic App. It's encrypted at rest but visible to anyone with access to the Logic App definition.

2. **API Connection Authentication**: The Office 365 connection uses OAuth and doesn't store passwords.

3. **Storage Account Access**: The storage account key is used by the Logic App connection. Consider using Managed Identity for enhanced security.

4. **Network Security**: Consider restricting the Logic App to a Virtual Network if your security requirements demand it.

## Cost Estimates

Approximate monthly costs (based on East US pricing):

- **Logic App**: $0.000125 per action execution
  - Assuming 1000 user updates/month × 8 actions = $1.00/month
- **Storage Account**: ~$0.01/month for config file
- **API Connections**: No additional cost

**Total estimated cost**: ~$1-2/month for typical usage

## Support

For issues related to:
- **Logic App deployment**: Check Azure deployment logs
- **SCIM API**: Contact Nintex support
- **Entra ID webhooks**: Check Azure AD audit logs

## Future Enhancements

Once Process Manager supports SCIM PATCH:
1. Update the Logic App to use PATCH instead of PUT
2. This will allow partial updates without fetching the full user object
3. Reduced risk of overwriting other fields during concurrent updates
