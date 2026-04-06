# Deployment Guide

This guide will help you deploy the Process Manager SCIM Sync Logic Apps to Azure.

## Prerequisites

Before deploying, ensure you have:

1. **Azure CLI** installed and authenticated (`az login`)
2. **Process Manager SCIM API Key** from Admin → SCIM in Process Manager
3. **Azure subscription** with permissions to create resources
4. **Entra ID admin access** to authorize API connections

## Quick Start Deployment

### Option 1: Using the deploy.sh Script

The `deploy.sh` script automates the entire deployment process:

```bash
# Make the script executable
chmod +x deploy.sh

# Run the deployment script
./deploy.sh
```

The script will prompt you for:
- Resource group name
- Azure region
- SCIM API key
- Mapping mode (dynamic or mapped)

### Option 2: Manual Deployment

If you prefer manual control, follow these steps:

#### Step 1: Set Variables

```bash
# Configure these variables for your environment
RESOURCE_GROUP="rg-processmanager-scim"
LOCATION="eastus"  # or westus2, westeurope, australiaeast, etc.
STORAGE_ACCOUNT="pmscimconfig$(date +%s)"  # Must be globally unique
CONTAINER_NAME="config"
LOGIC_APP_NAME="ProcessManagerSCIMSync"
SCIM_API_KEY="YOUR_SCIM_API_KEY_HERE"
MAPPING_MODE="dynamic"  # or "mapped"
UPDATE_MODE="preserve"  # or "replace"
```

#### Step 2: Create Resource Group (if needed)

```bash
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION
```

#### Step 3: Create Storage Account

```bash
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

#### Step 4: Upload Configuration (Mapped Mode Only)

If using **mapped mode**, upload the role-mapping.json:

```bash
# Upload role mapping configuration
az storage blob upload \
  --account-name $STORAGE_ACCOUNT \
  --account-key $STORAGE_KEY \
  --container-name $CONTAINER_NAME \
  --name role-mapping.json \
  --file ./config/role-mapping.json
```

#### Step 5: Create Parameters File

Create a file `logic-app/azuredeploy.parameters.local.json` (this file is gitignored):

```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "logicAppName": {
      "value": "ProcessManagerSCIMSync"
    },
    "scimApiKey": {
      "value": "YOUR_ACTUAL_SCIM_API_KEY"
    },
    "roleMappingStorageAccountName": {
      "value": "YOUR_STORAGE_ACCOUNT_NAME"
    },
    "roleMappingContainerName": {
      "value": "config"
    },
    "updateMode": {
      "value": "preserve"
    },
    "mappingMode": {
      "value": "dynamic"
    },
    "filterToExistingRoles": {
      "value": false
    },
    "processManagerSiteUrl": {
      "value": ""
    },
    "processManagerUsername": {
      "value": ""
    },
    "processManagerPassword": {
      "value": ""
    }
  }
}
```

Replace the values with your actual configuration.

**About the role filter parameters** (`filterToExistingRoles`, `processManagerSiteUrl`, `processManagerUsername`, `processManagerPassword`):

Leave these at their defaults (`filterToExistingRoles: false`, the rest empty) for standard behavior. Set `filterToExistingRoles: true` and provide the three Process Manager credentials if you want the Logic App to filter user groups/departments so only those that already exist as roles in Process Manager are synced. See [MAPPING_MODES.md](./MAPPING_MODES.md#filtering-to-existing-process-manager-roles) for details.

**Security note:** `processManagerPassword` is a `securestring`. For production, reference an Azure Key Vault secret in your parameters file instead of inlining the password:

```json
"processManagerPassword": {
  "reference": {
    "keyVault": { "id": "/subscriptions/.../Microsoft.KeyVault/vaults/YOUR_VAULT" },
    "secretName": "pm-scim-service-account-password"
  }
}
```

#### Step 6: Deploy Logic Apps

```bash
# Deploy both Logic Apps
az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file ./logic-app/azuredeploy.json \
  --parameters ./logic-app/azuredeploy.parameters.local.json \
  --parameters roleMappingStorageAccountName=$STORAGE_ACCOUNT \
  --parameters scimApiKey="$SCIM_API_KEY" \
  --parameters mappingMode="$MAPPING_MODE" \
  --parameters updateMode="$UPDATE_MODE"
```

#### Step 7: Authorize API Connections

After deployment, you must authorize the Office 365 connection:

1. Open the [Azure Portal](https://portal.azure.com)
2. Navigate to your Resource Group
3. Find the API Connection resource named `office365-xxxxx`
4. Click **Edit API connection**
5. Click **Authorize** and sign in with your Entra ID admin account
6. Click **Save**

#### Step 8: Verify Deployment

Check that both Logic Apps are enabled:

```bash
# Check Department Sync Logic App
az logic workflow show \
  --resource-group $RESOURCE_GROUP \
  --name ProcessManagerSCIMSync \
  --query "state"

# Check Group Sync Logic App
az logic workflow show \
  --resource-group $RESOURCE_GROUP \
  --name ProcessManagerSCIMSync-GroupSync \
  --query "state"
```

Both should return `"Enabled"`.

## Testing the Deployment

### Test Department Sync

1. Update a user's department in Entra ID
2. Check the Logic App run history:
   ```bash
   az logic workflow run list \
     --resource-group $RESOURCE_GROUP \
     --name ProcessManagerSCIMSync \
     --top 5
   ```
3. Verify the user's role was updated in Process Manager

### Test Group Sync

1. Add a user to a group in Entra ID (or remove them from a group)
2. Check the Group Sync Logic App run history:
   ```bash
   az logic workflow run list \
     --resource-group $RESOURCE_GROUP \
     --name ProcessManagerSCIMSync-GroupSync \
     --top 5
   ```
3. Verify the user's roles were updated in Process Manager

## Monitoring

View Logic App runs in the Azure Portal:

1. Navigate to your Logic App
2. Click **Overview** to see run history
3. Click on any run to see detailed execution
4. Check for errors in failed runs

## Updating Configuration

### Update Role Mapping (Mapped Mode)

To update the role mapping after deployment:

```bash
az storage blob upload \
  --account-name $STORAGE_ACCOUNT \
  --account-key $STORAGE_KEY \
  --container-name $CONTAINER_NAME \
  --name role-mapping.json \
  --file ./config/role-mapping.json \
  --overwrite
```

The Logic Apps will use the updated mapping on the next trigger.

### Switch Between Dynamic and Mapped Mode

To switch mapping modes, redeploy with different parameters:

```bash
az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file ./logic-app/azuredeploy.json \
  --parameters ./logic-app/azuredeploy.parameters.local.json \
  --parameters mappingMode="mapped"  # or "dynamic"
```

## Troubleshooting

### Common Issues

**Logic Apps not triggering:**
- Verify Office 365 API connection is authorized
- Check that webhooks are registered (visible in Logic App designer)
- Ensure Logic Apps are in "Enabled" state

**Authentication errors:**
- Verify SCIM API key is correct
- Check API key hasn't expired
- Ensure API key has appropriate permissions in Process Manager

**Roles not updating:**
- Check Logic App run history for errors
- Verify role names match exactly (case-sensitive, unless `filterToExistingRoles` is on — then case-insensitive with trim)
- For mapped mode: Check role-mapping.json is uploaded correctly
- Verify user exists in both Entra ID and Process Manager
- If `filterToExistingRoles: true`: inspect the `Set_valid_roles_lower` action output to confirm the filter is populating `validRolesLower` with a sensible list of PM roles

**Role filter (`filterToExistingRoles: true`) errors:**
- `Get_PM_oauth_token` 400/401: wrong service-account credentials, site URL, or MFA is enforced on the account
- `Get_PM_roles_html` 401: token issued but service account lacks permission to view the roles list
- Filter silently no-ops: check that `validRolesLower` is non-empty in the run output; if empty, the HTML parser may need updating

**Deployment failures:**
- Check Azure CLI is authenticated: `az account show`
- Verify you have permissions in the subscription
- Ensure storage account name is globally unique

## Cleanup

To remove all deployed resources:

```bash
az group delete --name $RESOURCE_GROUP --yes --no-wait
```

**Warning:** This will delete ALL resources in the resource group!

## Security Best Practices

1. **Never commit** `azuredeploy.parameters.local.json` to git (it contains secrets)
2. Use **Azure Key Vault** for production deployments to store SCIM API keys
3. Consider **Managed Identity** instead of storage account keys
4. Enable **diagnostic logging** to monitor API calls
5. Restrict **network access** to Logic Apps if required by your security policies

## Cost Estimates

Based on East US pricing:

- **Logic Apps**: ~$1-2/month for typical usage (1000 user updates)
- **Storage Account**: <$0.01/month for config file
- **API Connections**: Free
- **Total**: ~$1-2/month

## Next Steps

After successful deployment:

1. Review the [TESTING.md](./TESTING.md) guide for comprehensive testing procedures
2. Monitor Logic App runs for the first few days
3. Set up Azure Monitor alerts for failed runs
4. Document your specific department/group → role mappings
5. Train your team on how to manage the sync

## Getting Help

- **Azure deployment issues**: Check Azure deployment logs
- **Logic App errors**: Review run history in Azure Portal
- **SCIM API errors**: Contact Nintex support
- **General questions**: See [README.md](./README.md)
