#!/bin/bash
#
# Grants the Process Manager SCIM Sync Logic App the read-only Microsoft Graph
# permissions it needs, then switches the sync on (it's deployed switched off).
# Run after every install or redeploy. Works in Azure Cloud Shell (Bash) or any
# machine with Azure CLI.
#
# Must be run by an Entra ID Global Administrator or Privileged Role Administrator.
#
# Usage:
#   ./grant-permissions.sh [resource-group] [logic-app-name]
#
# Defaults: rg-processmanager-scim / ProcessManagerSCIMSync

set -e

RESOURCE_GROUP="${1:-rg-processmanager-scim}"
LOGIC_APP_NAME="${2:-ProcessManagerSCIMSync}"
GRAPH_APP_ID="00000003-0000-0000-c000-000000000000"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo "Looking up Logic App '$LOGIC_APP_NAME' in resource group '$RESOURCE_GROUP'..."
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
WORKFLOW_URL="https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Logic/workflows/$LOGIC_APP_NAME?api-version=2019-05-01"

if ! WORKFLOW=$(az rest --method get --url "$WORKFLOW_URL" -o json 2>/dev/null); then
    echo -e "${RED}✗ Could not find that Logic App. Check the resource group and name, and that you're in the right subscription (az account show).${NC}"
    exit 1
fi

read -r PRINCIPAL_ID ROLE_SOURCE MAPPING_MODE < <(echo "$WORKFLOW" | python3 -c "
import json, sys
w = json.load(sys.stdin)
p = w['properties']['definition']['parameters']
print(w['identity']['principalId'], p.get('roleSource', {}).get('defaultValue', 'both'), p['mappingMode']['defaultValue'])
")

echo "  Managed identity: $PRINCIPAL_ID"
echo "  Role source:      $ROLE_SOURCE"
echo "  Mapping mode:     $MAPPING_MODE"
echo ""

# User.Read.All is always needed (department changes and user lookups).
PERMISSIONS="User.Read.All"
if [ "$ROLE_SOURCE" != "department" ]; then
    PERMISSIONS="$PERMISSIONS GroupMember.Read.All"
fi
if [ "$MAPPING_MODE" = "entraAppRoles" ]; then
    PERMISSIONS="$PERMISSIONS Application.Read.All"
fi

GRAPH_SP=$(az rest --method get \
    --url "https://graph.microsoft.com/v1.0/servicePrincipals(appId='$GRAPH_APP_ID')?\$select=id,appRoles" -o json)
GRAPH_SP_ID=$(echo "$GRAPH_SP" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

EXISTING=$(az rest --method get \
    --url "https://graph.microsoft.com/v1.0/servicePrincipals/$PRINCIPAL_ID/appRoleAssignments" \
    --query "value[].appRoleId" -o tsv)

NEWLY_GRANTED=false
for PERMISSION in $PERMISSIONS; do
    ROLE_ID=$(echo "$GRAPH_SP" | python3 -c "
import json, sys
roles = json.load(sys.stdin)['appRoles']
print(next(r['id'] for r in roles if r['value'] == '$PERMISSION' and 'Application' in r['allowedMemberTypes']))
")
    if echo "$EXISTING" | grep -q "$ROLE_ID"; then
        echo -e "${GREEN}✓ $PERMISSION already granted${NC}"
        continue
    fi
    az rest --method post \
        --url "https://graph.microsoft.com/v1.0/servicePrincipals/$PRINCIPAL_ID/appRoleAssignments" \
        --headers "Content-Type=application/json" \
        --body "{\"principalId\":\"$PRINCIPAL_ID\",\"resourceId\":\"$GRAPH_SP_ID\",\"appRoleId\":\"$ROLE_ID\"}" \
        --output none
    echo -e "${GREEN}✓ $PERMISSION granted${NC}"
    NEWLY_GRANTED=true
done

# The Logic App is deployed switched off. Switching it on only after new permissions
# have spread through Entra ID matters: Azure caches the Logic App's sign-in token, and
# a token fetched too early (without the permissions) can linger for hours.
if [ "$NEWLY_GRANTED" = true ]; then
    echo ""
    echo "Waiting 2 minutes for the new permissions to take effect before switching the sync on..."
    sleep 120
fi

az rest --method post \
    --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Logic/workflows/$LOGIC_APP_NAME/enable?api-version=2019-05-01" \
    --output none
echo -e "${GREEN}✓ Sync switched on${NC}"

echo ""
echo -e "${GREEN}Done.${NC} The first check runs now, then on the schedule you chose."
echo "If an early run fails with a message about Microsoft Graph permissions, give it a"
echo "little longer; it will start working on its own."
