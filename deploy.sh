#!/bin/bash
#
# Process Manager SCIM Sync - command-line installer.
# The "Deploy to Azure" button in README.md does the same thing from the Azure Portal.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PARAMS_FILE=""
cleanup() {
    if [ -n "$PARAMS_FILE" ] && [ -f "$PARAMS_FILE" ]; then
        rm -f "$PARAMS_FILE"
    fi
    unset SCIM_API_KEY PM_PASSWORD
}
trap cleanup EXIT

fail() {
    echo -e "${RED}✗ $1${NC}"
    exit 1
}

# Resource names: letters, numbers and hyphens only
validate_resource_name() {
    echo "$1" | grep -qE '^[a-zA-Z0-9-]+$' || fail "$2 can only contain letters, numbers and hyphens."
}

# ask <variable> <prompt> <default> [allowed values...]
ask() {
    local var="$1" prompt="$2" default="$3"
    shift 3
    local answer
    read -p "$prompt [$default]: " answer
    answer="${answer:-$default}"
    if [ $# -gt 0 ] && ! printf '%s\n' "$@" | grep -qx "$answer"; then
        fail "Please enter one of: $*"
    fi
    printf -v "$var" '%s' "$answer"
}

echo -e "${GREEN}Process Manager SCIM Sync - Azure installer${NC}"
echo ""

command -v az &> /dev/null || fail "Azure CLI is not installed: https://learn.microsoft.com/cli/azure/install-azure-cli"
if ! az account show &> /dev/null; then
    echo -e "${YELLOW}Please sign in to Azure:${NC}"
    az login
fi
echo -e "${GREEN}✓ Signed in to Azure as $(az account show --query user.name -o tsv) ($(az account show --query name -o tsv))${NC}"
echo ""

# ---------------------------------------------------------------- Azure location

ask RESOURCE_GROUP "Resource group name" "rg-processmanager-scim"
validate_resource_name "$RESOURCE_GROUP" "Resource group name"
ask LOCATION "Azure region" "eastus"
validate_resource_name "$LOCATION" "Azure region"
ask LOGIC_APP_NAME "Logic App name" "ProcessManagerSCIMSync"
validate_resource_name "$LOGIC_APP_NAME" "Logic App name"

echo ""
read -sp "Process Manager SCIM API token: " SCIM_API_KEY
echo ""
[ -n "$SCIM_API_KEY" ] || fail "The SCIM API token is required."

# ---------------------------------------------------------------- how roles are chosen

echo ""
echo -e "${YELLOW}What should decide a user's Process Manager roles?${NC}"
echo "  department - the Department field on their Entra ID profile (one role per user)"
echo "  groups     - the Entra ID groups they belong to"
echo "  both       - department and groups together"
ask ROLE_SOURCE "Role source" "department" department groups both

echo ""
echo -e "${YELLOW}How should Entra ID names become Process Manager role names?${NC}"
echo "  dynamic       - use the department/group name as the role name, exactly as-is"
echo "  mapped        - use config/role-mapping.json to translate names"
echo "  entraAppRoles - assign roles in the Entra admin center via an Enterprise App (groups/both only)"
ask MAPPING_MODE "Mapping mode" "dynamic" dynamic mapped entraAppRoles

ENTRA_APP_ID=""
if [ "$MAPPING_MODE" = "entraAppRoles" ]; then
    [ "$ROLE_SOURCE" != "department" ] || fail "entraAppRoles needs Role source 'groups' or 'both'."
    read -p "Application (client) ID of the Enterprise App: " ENTRA_APP_ID
    echo "$ENTRA_APP_ID" | grep -qE '^[0-9a-fA-F-]{36}$' || fail "That doesn't look like an application ID (a GUID)."
fi
if [ "$MAPPING_MODE" = "mapped" ] && [ ! -f "$SCRIPT_DIR/config/role-mapping.json" ]; then
    fail "config/role-mapping.json not found. Create it before choosing mapped mode."
fi

echo ""
echo -e "${YELLOW}When a user's roles change, what happens to roles they already have?${NC}"
echo "  managed  - remove only roles this sync gave them; keep roles added by hand (recommended)"
echo "  preserve - never remove anything, only add"
echo "  replace  - make their roles exactly match Entra ID"
ask UPDATE_MODE "Update mode" "managed" managed preserve replace

echo ""
ask POLLING_INTERVAL "Check for changes every how many minutes (1-60)" "15"
echo "$POLLING_INTERVAL" | grep -qE '^[0-9]+$' && [ "$POLLING_INTERVAL" -ge 1 ] && [ "$POLLING_INTERVAL" -le 60 ] \
    || fail "Enter a number of minutes between 1 and 60."

ask SYNC_EXISTING "Update every existing user on the first run? (y/n)" "n" y n Y N
SYNC_EXISTING_BOOL=false
[[ "$SYNC_EXISTING" =~ ^[Yy]$ ]] && SYNC_EXISTING_BOOL=true

# ---------------------------------------------------------------- optional role filter

echo ""
echo -e "${YELLOW}Role filter (optional)${NC}"
echo "  Only assign roles that already exist in Process Manager, so Entra ID never creates new ones."
echo "  Needs a Process Manager service account without MFA."
ask ENABLE_FILTER "Enable role filter? (y/n)" "n" y n Y N

FILTER_TO_EXISTING_ROLES=false
PM_SITE_URL=""
PM_USERNAME=""
PM_PASSWORD=""
if [[ "$ENABLE_FILTER" =~ ^[Yy]$ ]]; then
    FILTER_TO_EXISTING_ROLES=true
    read -p "Process Manager site URL (e.g. https://demo.promapp.com/{tenantId}): " PM_SITE_URL
    PM_SITE_URL="${PM_SITE_URL%/}"
    echo "$PM_SITE_URL" | grep -qE '^https://' || fail "The site URL must start with https://"
    read -p "Service-account username: " PM_USERNAME
    [ -n "$PM_USERNAME" ] || fail "Username is required for the role filter."
    read -sp "Service-account password: " PM_PASSWORD
    echo ""
    [ -n "$PM_PASSWORD" ] || fail "Password is required for the role filter."
fi

# ---------------------------------------------------------------- confirm

echo ""
echo -e "${GREEN}Summary${NC}"
echo "  Resource group:  $RESOURCE_GROUP ($LOCATION)"
echo "  Logic App:       $LOGIC_APP_NAME"
echo "  Role source:     $ROLE_SOURCE"
echo "  Mapping mode:    $MAPPING_MODE${ENTRA_APP_ID:+ ($ENTRA_APP_ID)}"
echo "  Update mode:     $UPDATE_MODE"
echo "  Checks every:    $POLLING_INTERVAL minutes"
echo "  Sync everyone on first run: $SYNC_EXISTING_BOOL"
echo "  Role filter:     $FILTER_TO_EXISTING_ROLES"
echo ""
ask CONFIRM "Deploy now? (y/n)" "y" y n Y N
[[ "$CONFIRM" =~ ^[Yy]$ ]] || { echo "Cancelled."; exit 0; }

# ---------------------------------------------------------------- deploy

echo ""
echo -e "${YELLOW}[1/4]${NC} Resource group..."
if az group show --name "$RESOURCE_GROUP" &> /dev/null; then
    echo -e "${GREEN}  ✓ Already exists${NC}"
else
    az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
    echo -e "${GREEN}  ✓ Created${NC}"
fi

echo -e "${YELLOW}[2/4]${NC} Deploying Logic App and storage (a few minutes)..."
umask 077
PARAMS_FILE=$(mktemp "${TMPDIR:-/tmp}/azuredeploy.parameters.XXXXXX")
# Values go through python's json module so any character in a password or token is escaped correctly.
SCIM_API_KEY="$SCIM_API_KEY" PM_SITE_URL="$PM_SITE_URL" PM_USERNAME="$PM_USERNAME" PM_PASSWORD="$PM_PASSWORD" \
    python3 - "$PARAMS_FILE" <<EOF
import json, os, sys
params = {
    "logicAppName": "$LOGIC_APP_NAME",
    "scimApiKey": os.environ["SCIM_API_KEY"],
    "roleSource": "$ROLE_SOURCE",
    "mappingMode": "$MAPPING_MODE",
    "entraAppId": "$ENTRA_APP_ID",
    "updateMode": "$UPDATE_MODE",
    "pollingIntervalMinutes": $POLLING_INTERVAL,
    "syncExistingUsersOnFirstRun": $( [ "$SYNC_EXISTING_BOOL" = true ] && echo True || echo False ),
    "filterToExistingRoles": $( [ "$FILTER_TO_EXISTING_ROLES" = true ] && echo True || echo False ),
    "processManagerSiteUrl": os.environ["PM_SITE_URL"],
    "processManagerUsername": os.environ["PM_USERNAME"],
    "processManagerPassword": os.environ["PM_PASSWORD"],
}
with open(sys.argv[1], "w") as f:
    json.dump({"\$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
               "contentVersion": "1.0.0.0",
               "parameters": {k: {"value": v} for k, v in params.items()}}, f)
EOF

if ! STORAGE_ACCOUNT=$(az deployment group create \
        --resource-group "$RESOURCE_GROUP" \
        --template-file "$SCRIPT_DIR/logic-app/azuredeploy.json" \
        --parameters "@$PARAMS_FILE" \
        --query "properties.outputs.storageAccountName.value" -o tsv); then
    fail "Deployment failed. The error above says why. If it mentions 'roleAssignments', your Azure account needs the Owner or User Access Administrator role on the subscription or resource group."
fi
echo -e "${GREEN}  ✓ Deployed (storage account: $STORAGE_ACCOUNT)${NC}"

echo -e "${YELLOW}[3/4]${NC} Role mapping file..."
if [ "$MAPPING_MODE" = "mapped" ]; then
    az storage blob upload \
        --account-name "$STORAGE_ACCOUNT" \
        --container-name config \
        --name role-mapping.json \
        --file "$SCRIPT_DIR/config/role-mapping.json" \
        --auth-mode key \
        --only-show-errors \
        --overwrite \
        --output none
    echo -e "${GREEN}  ✓ Uploaded config/role-mapping.json${NC}"
else
    echo -e "${GREEN}  ✓ Not needed for $MAPPING_MODE mode${NC}"
fi

echo -e "${YELLOW}[4/4]${NC} Microsoft Graph permissions..."
if ! "$SCRIPT_DIR/scripts/grant-permissions.sh" "$RESOURCE_GROUP" "$LOGIC_APP_NAME"; then
    echo -e "${YELLOW}  ⚠ Couldn't grant permissions with your account, so the sync is still switched off.${NC}"
    echo "    Ask an Entra ID Global Administrator to run this, which grants access and switches it on:"
    echo "     ./scripts/grant-permissions.sh $RESOURCE_GROUP $LOGIC_APP_NAME"
    exit 1
fi

echo ""
echo -e "${GREEN}Installation complete.${NC}"
echo ""
echo "The first check has just run; after that it checks every $POLLING_INTERVAL minutes."
echo "To test: change a user's ${ROLE_SOURCE/both/department or groups} in Entra ID, wait for the next run, and check their roles in Process Manager."
echo ""
echo "Run history: https://portal.azure.com/#resource/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Logic/workflows/$LOGIC_APP_NAME/logicApp"
