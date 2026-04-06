#!/bin/bash

# Azure Logic App Deployment Script
# Process Manager SCIM Sync

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Temp file cleanup trap
PARAMS_FILE=""
cleanup() {
    if [ -n "$PARAMS_FILE" ] && [ -f "$PARAMS_FILE" ]; then
        rm -f "$PARAMS_FILE"
    fi
    unset SCIM_API_KEY
    unset STORAGE_KEY
    unset PM_PASSWORD
}
trap cleanup EXIT

# JSON string escaping for shell-sourced values that go into the parameters file.
# Escapes backslashes and double-quotes. Does NOT handle control characters.
json_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

# Input validation: alphanumeric and hyphens only
validate_resource_name() {
    local name="$1"
    local label="$2"
    if ! echo "$name" | grep -qE '^[a-zA-Z0-9-]+$'; then
        echo -e "${RED}✗ ${label} contains invalid characters. Only alphanumeric characters and hyphens are allowed.${NC}"
        exit 1
    fi
}

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Process Manager SCIM Sync - Azure Deployment Script     ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo -e "${RED}✗ Azure CLI is not installed. Please install it first:${NC}"
    echo "  https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
fi

# Check if user is logged in
if ! az account show &> /dev/null; then
    echo -e "${YELLOW}⚠ You are not logged into Azure. Please log in:${NC}"
    az login
fi

echo -e "${GREEN}✓ Azure CLI is configured${NC}"
echo ""

# Prompt for configuration
read -p "Enter Resource Group name [rg-processmanager-scim]: " RESOURCE_GROUP
RESOURCE_GROUP=${RESOURCE_GROUP:-rg-processmanager-scim}
validate_resource_name "$RESOURCE_GROUP" "Resource Group name"

read -p "Enter Azure region [eastus]: " LOCATION
LOCATION=${LOCATION:-eastus}
validate_resource_name "$LOCATION" "Azure region"

read -p "Enter Logic App name [ProcessManagerSCIMSync]: " LOGIC_APP_NAME
LOGIC_APP_NAME=${LOGIC_APP_NAME:-ProcessManagerSCIMSync}
validate_resource_name "$LOGIC_APP_NAME" "Logic App name"

echo ""
echo -e "${YELLOW}⚠ Storage Account name must be globally unique (3-24 lowercase letters and numbers)${NC}"
read -p "Enter Storage Account name [pmscimconfig$(date +%s)]: " STORAGE_ACCOUNT
STORAGE_ACCOUNT=${STORAGE_ACCOUNT:-pmscimconfig$(date +%s)}
validate_resource_name "$STORAGE_ACCOUNT" "Storage Account name"

read -p "Enter Storage Container name [config]: " CONTAINER_NAME
CONTAINER_NAME=${CONTAINER_NAME:-config}
validate_resource_name "$CONTAINER_NAME" "Storage Container name"

echo ""
echo -e "${YELLOW}⚠ Your SCIM API key will be stored securely but will be visible to Logic App editors${NC}"
read -sp "Enter Process Manager SCIM API Key: " SCIM_API_KEY
echo ""

if [ -z "$SCIM_API_KEY" ]; then
    echo -e "${RED}✗ SCIM API Key is required${NC}"
    exit 1
fi

read -p "Enter update mode (preserve/replace) [preserve]: " UPDATE_MODE
UPDATE_MODE=${UPDATE_MODE:-preserve}

if [ "$UPDATE_MODE" != "preserve" ] && [ "$UPDATE_MODE" != "replace" ]; then
    echo -e "${RED}✗ Update mode must be 'preserve' or 'replace'${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Role Mapping Mode:${NC}"
echo "  - ${GREEN}dynamic${NC}: Use Entra ID department/group names directly as Process Manager roles (1:1 mapping)"
echo "  - ${GREEN}mapped${NC}: Use role-mapping.json to map departments/groups to roles (flexible mapping)"
read -p "Enter mapping mode (dynamic/mapped) [dynamic]: " MAPPING_MODE
MAPPING_MODE=${MAPPING_MODE:-dynamic}

if [ "$MAPPING_MODE" != "dynamic" ] && [ "$MAPPING_MODE" != "mapped" ]; then
    echo -e "${RED}✗ Mapping mode must be 'dynamic' or 'mapped'${NC}"
    exit 1
fi

echo ""
read -p "Enter polling interval in minutes (1-60) [5]: " POLLING_INTERVAL
POLLING_INTERVAL=${POLLING_INTERVAL:-5}

if ! echo "$POLLING_INTERVAL" | grep -qE '^[0-9]+$'; then
    echo -e "${RED}✗ Polling interval must be a number${NC}"
    exit 1
fi

if [ "$POLLING_INTERVAL" -lt 1 ] || [ "$POLLING_INTERVAL" -gt 60 ]; then
    echo -e "${RED}✗ Polling interval must be between 1 and 60 minutes${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Role Filter (optional):${NC}"
echo "  Prevents AD groups/departments from creating new roles in Process Manager."
echo "  When enabled, only departments/groups whose names already exist as roles"
echo "  in Process Manager will be synced. Recommended for most customers."
read -p "Enable role filter? (y/n) [n]: " ENABLE_FILTER
ENABLE_FILTER=${ENABLE_FILTER:-n}

FILTER_TO_EXISTING_ROLES="false"
PM_SITE_URL=""
PM_USERNAME=""
PM_PASSWORD=""

if [ "$ENABLE_FILTER" = "y" ] || [ "$ENABLE_FILTER" = "Y" ]; then
    FILTER_TO_EXISTING_ROLES="true"
    echo ""
    echo -e "${YELLOW}Process Manager credentials required for the role filter.${NC}"
    echo "  Use a dedicated service account without MFA."
    read -p "Process Manager site URL (e.g. https://demo.promapp.com/{tenantId}, no trailing slash): " PM_SITE_URL
    if [ -z "$PM_SITE_URL" ]; then
        echo -e "${RED}✗ Process Manager site URL is required when role filter is enabled${NC}"
        exit 1
    fi
    if echo "$PM_SITE_URL" | grep -qE '/$'; then
        echo -e "${RED}✗ Process Manager site URL must not have a trailing slash${NC}"
        exit 1
    fi
    if ! echo "$PM_SITE_URL" | grep -qE '^https://'; then
        echo -e "${RED}✗ Process Manager site URL must start with https://${NC}"
        exit 1
    fi
    read -p "Process Manager service-account username: " PM_USERNAME
    if [ -z "$PM_USERNAME" ]; then
        echo -e "${RED}✗ Process Manager username is required when role filter is enabled${NC}"
        exit 1
    fi
    read -sp "Process Manager service-account password: " PM_PASSWORD
    echo ""
    if [ -z "$PM_PASSWORD" ]; then
        echo -e "${RED}✗ Process Manager password is required when role filter is enabled${NC}"
        exit 1
    fi
fi

echo ""
echo -e "${GREEN}Configuration Summary:${NC}"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Location: $LOCATION"
echo "  Logic App: $LOGIC_APP_NAME"
echo "  Storage Account: $STORAGE_ACCOUNT"
echo "  Container: $CONTAINER_NAME"
echo "  Update Mode: $UPDATE_MODE"
echo "  Mapping Mode: $MAPPING_MODE"
echo "  Polling Interval: ${POLLING_INTERVAL} minutes"
echo "  Role Filter: $FILTER_TO_EXISTING_ROLES"
if [ "$FILTER_TO_EXISTING_ROLES" = "true" ]; then
    echo "  PM Site URL: $PM_SITE_URL"
    echo "  PM Username: $PM_USERNAME"
    echo "  PM Password: (hidden)"
fi
echo ""

read -p "Proceed with deployment? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Deployment cancelled."
    exit 0
fi

echo ""
echo -e "${GREEN}Starting deployment...${NC}"
echo ""

# Step 1: Create Resource Group
echo -e "${YELLOW}[1/6]${NC} Creating resource group..."
if az group show --name "$RESOURCE_GROUP" &> /dev/null; then
    echo -e "${GREEN}  ✓ Resource group already exists${NC}"
else
    az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
    echo -e "${GREEN}  ✓ Resource group created${NC}"
fi

# Step 2: Create Storage Account
echo -e "${YELLOW}[2/6]${NC} Creating storage account..."
if az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" &> /dev/null; then
    echo -e "${GREEN}  ✓ Storage account already exists${NC}"
else
    az storage account create \
        --name "$STORAGE_ACCOUNT" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --sku Standard_LRS \
        --kind StorageV2 \
        --https-only true \
        --min-tls-version TLS1_2 \
        --allow-blob-public-access false \
        --output none
    echo -e "${GREEN}  ✓ Storage account created${NC}"
fi

# Get storage key
STORAGE_KEY=$(az storage account keys list \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$STORAGE_ACCOUNT" \
    --query '[0].value' -o tsv)

# Step 3: Create Container
echo -e "${YELLOW}[3/6]${NC} Creating storage container..."
if az storage container show --name "$CONTAINER_NAME" --account-name "$STORAGE_ACCOUNT" --account-key "$STORAGE_KEY" &> /dev/null; then
    echo -e "${GREEN}  ✓ Container already exists${NC}"
else
    az storage container create \
        --name "$CONTAINER_NAME" \
        --account-name "$STORAGE_ACCOUNT" \
        --account-key "$STORAGE_KEY" \
        --output none
    echo -e "${GREEN}  ✓ Container created${NC}"
fi

# Step 4: Upload Role Mapping (only needed for mapped mode)
echo -e "${YELLOW}[4/6]${NC} Uploading role mapping configuration..."
if [ "$MAPPING_MODE" = "mapped" ]; then
    if [ ! -f "./config/role-mapping.json" ]; then
        echo -e "${RED}  ✗ role-mapping.json not found in ./config/${NC}"
        echo -e "${YELLOW}  ⚠ Please ensure config/role-mapping.json exists for mapped mode${NC}"
        exit 1
    fi

    az storage blob upload \
        --account-name "$STORAGE_ACCOUNT" \
        --account-key "$STORAGE_KEY" \
        --container-name "$CONTAINER_NAME" \
        --name role-mapping.json \
        --file ./config/role-mapping.json \
        --overwrite \
        --output none
    echo -e "${GREEN}  ✓ Role mapping uploaded${NC}"
else
    echo -e "${GREEN}  ✓ Skipped (using dynamic mode)${NC}"
fi

# Step 5: Create Parameters File
echo -e "${YELLOW}[5/6]${NC} Generating deployment parameters..."
umask 077
PARAMS_FILE=$(mktemp "${TMPDIR:-/tmp}/azuredeploy.parameters.XXXXXX.json")

# Escape values that may contain backslashes or double quotes
SCIM_API_KEY_ESC=$(json_escape "$SCIM_API_KEY")
PM_SITE_URL_ESC=$(json_escape "$PM_SITE_URL")
PM_USERNAME_ESC=$(json_escape "$PM_USERNAME")
PM_PASSWORD_ESC=$(json_escape "$PM_PASSWORD")

cat > "$PARAMS_FILE" <<EOF
{
  "\$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "logicAppName": {
      "value": "$LOGIC_APP_NAME"
    },
    "scimApiKey": {
      "value": "$SCIM_API_KEY_ESC"
    },
    "roleMappingStorageAccountName": {
      "value": "$STORAGE_ACCOUNT"
    },
    "roleMappingContainerName": {
      "value": "$CONTAINER_NAME"
    },
    "updateMode": {
      "value": "$UPDATE_MODE"
    },
    "mappingMode": {
      "value": "$MAPPING_MODE"
    },
    "pollingIntervalMinutes": {
      "value": $POLLING_INTERVAL
    },
    "filterToExistingRoles": {
      "value": $FILTER_TO_EXISTING_ROLES
    },
    "processManagerSiteUrl": {
      "value": "$PM_SITE_URL_ESC"
    },
    "processManagerUsername": {
      "value": "$PM_USERNAME_ESC"
    },
    "processManagerPassword": {
      "value": "$PM_PASSWORD_ESC"
    }
  }
}
EOF
unset SCIM_API_KEY_ESC PM_PASSWORD_ESC
echo -e "${GREEN}  ✓ Parameters file created${NC}"

# Step 6: Deploy Logic App
echo -e "${YELLOW}[6/6]${NC} Deploying Logic App (this may take a few minutes)..."
DEPLOYMENT_OUTPUT=$(az deployment group create \
    --resource-group "$RESOURCE_GROUP" \
    --template-file ./logic-app/azuredeploy.json \
    --parameters "$PARAMS_FILE" \
    --output json 2>&1) || true

if echo "$DEPLOYMENT_OUTPUT" | grep -q '"provisioningState": "Succeeded"'; then
    echo -e "${GREEN}  ✓ Logic App deployed successfully${NC}"
else
    echo -e "${RED}  ✗ Deployment failed${NC}"
    echo -e "${RED}  Error details:${NC}"
    echo "$DEPLOYMENT_OUTPUT" | head -50
    exit 1
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              Deployment Complete!                          ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo -e "1. ${YELLOW}Authorize the Office 365 API Connection:${NC}"
echo "   - Go to: https://portal.azure.com/#resource/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Web/connections"
echo "   - Click on the 'office365-*' connection"
echo "   - Click 'Edit API connection'"
echo "   - Click 'Authorize' and sign in"
echo "   - Click 'Save'"
echo ""
echo -e "2. ${YELLOW}Verify the Logic App is enabled:${NC}"
echo "   az logic workflow show --resource-group $RESOURCE_GROUP --name $LOGIC_APP_NAME --query 'state'"
echo ""
echo -e "3. ${YELLOW}Test the deployment:${NC}"
echo "   - Update a user's department in Entra ID"
echo "   - Monitor Logic App runs in Azure Portal"
echo "   - Verify roles are updated in Process Manager"
echo ""
echo -e "4. ${YELLOW}View Logic App in Azure Portal:${NC}"
echo "   https://portal.azure.com/#resource/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Logic/workflows/$LOGIC_APP_NAME"
echo ""
echo -e "${GREEN}For detailed testing instructions, see TESTING.md${NC}"
echo ""
echo -e "${YELLOW}Note:${NC} This Logic App syncs BOTH departments AND group memberships to roles."
echo "When a user is updated in Entra ID, their department and all group memberships"
echo "will be mapped to Process Manager roles and assigned to the user."
echo ""
