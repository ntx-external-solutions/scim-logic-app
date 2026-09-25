#!/bin/bash
#
# Sets up an Entra ID Enterprise App whose app roles match your Process Manager roles,
# for the "entraAppRoles" mapping mode. Admins then assign groups (or users) to those
# roles in the Entra admin center: Enterprise applications > the app > Users and groups.
#
# Run in Azure Cloud Shell (Bash) or anywhere with Azure CLI, as an Entra ID
# Application Administrator or Global Administrator. Safe to re-run: roles that
# already exist are left alone, new ones are added.
#
# Usage:
#   ./create-role-app.sh                          Create "Process Manager Roles"; roles are read from Process Manager
#   ./create-role-app.sh "Role A" "Role B" ...    Create it with exactly these roles
#   APP_ID=<client id> ./create-role-app.sh ...   Add roles to an existing app instead (e.g. your
#                                                 Nintex Process Manager gallery app)
#
# Reading roles from Process Manager asks for your SCIM API token and collects every role
# currently assigned to at least one user. Add any unassigned roles by name.

set -e

APP_NAME="${APP_NAME:-Process Manager Roles}"
SCIM_BASE_URL="${SCIM_BASE_URL:-https://api.promapp.com/api/scim}"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

OUR_APP=false
fail() { echo -e "${RED}✗ $1${NC}"; exit 1; }

# ---------------------------------------------------------------- role names

ROLES_FILE=$(mktemp)
trap 'rm -f "$ROLES_FILE" "$ROLES_FILE.app" "$ROLES_FILE.body"' EXIT

if [ $# -gt 0 ]; then
    printf '%s\n' "$@" > "$ROLES_FILE"
else
    read -sp "Process Manager SCIM API token (used once to read role names, not stored): " SCIM_TOKEN
    echo ""
    [ -n "$SCIM_TOKEN" ] || fail "A SCIM token is required when no role names are given."
    SCIM_TOKEN="$SCIM_TOKEN" SCIM_BASE_URL="$SCIM_BASE_URL" python3 - "$ROLES_FILE" <<'EOF'
import json, os, sys, urllib.request
roles, start = set(), 1
while True:
    req = urllib.request.Request(f"{os.environ['SCIM_BASE_URL']}/users?startIndex={start}&count=200",
                                 headers={"Authorization": f"Bearer {os.environ['SCIM_TOKEN']}"})
    page = json.load(urllib.request.urlopen(req))
    users = page.get("Resources") or []
    for u in users:
        for r in u.get("roles") or []:
            name = (r.get("display") or r.get("value") or "").strip()
            if name:
                roles.add(name)
    start += len(users)
    if not users or start > page.get("totalResults", 0):
        break
open(sys.argv[1], "w").write("\n".join(sorted(roles, key=str.lower)) + "\n")
EOF
    unset SCIM_TOKEN
fi

echo "Roles to set up:"
sed 's/^/  - /' "$ROLES_FILE"
echo ""

# ---------------------------------------------------------------- app registration

if [ -n "$APP_ID" ]; then
    APP_OBJECT_ID=$(az ad app show --id "$APP_ID" --query id -o tsv) || fail "No app registration found with ID $APP_ID."
    echo -e "${GREEN}✓ Using existing app $APP_ID${NC}"
else
    OUR_APP=true
    APP_ID=$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv)
    if [ -z "$APP_ID" ]; then
        APP_ID=$(az ad app create --display-name "$APP_NAME" --sign-in-audience AzureADMyOrg --query appId -o tsv)
        echo -e "${GREEN}✓ Created app registration '$APP_NAME'${NC}"
    else
        echo -e "${GREEN}✓ Found existing app registration '$APP_NAME'${NC}"
    fi
    APP_OBJECT_ID=$(az ad app show --id "$APP_ID" --query id -o tsv)
fi

# Add one app role per Process Manager role. Existing roles (matched by display name,
# case-insensitive) are kept exactly as they are.
az rest --method get --url "https://graph.microsoft.com/v1.0/applications/$APP_OBJECT_ID?\$select=appRoles" -o json > "$ROLES_FILE.app"
python3 - "$ROLES_FILE" "$ROLES_FILE.app" > "$ROLES_FILE.body" <<'EOF'
import json, re, sys, uuid
existing = json.load(open(sys.argv[2]))["appRoles"]
have = {r["displayName"].lower() for r in existing}
values = {r.get("value") for r in existing}
added = []
for name in open(sys.argv[1]).read().splitlines():
    name = name.strip()
    if not name or name.lower() in have:
        continue
    # App role values can't contain spaces; they're only an internal identifier here.
    value = re.sub(r"\s+", ".", name)[:120]
    while value in values:
        value += "_"
    values.add(value)
    have.add(name.lower())
    existing.append({"id": str(uuid.uuid4()), "displayName": name, "value": value, "isEnabled": True,
                     "allowedMemberTypes": ["User"],
                     "description": f"Gives the Process Manager role '{name}'"})
    added.append(name)
print(json.dumps({"appRoles": existing}))
sys.stderr.write(f"{len(added)} new role(s): {', '.join(added) or 'none'}\n")
EOF
az rest --method patch --url "https://graph.microsoft.com/v1.0/applications/$APP_OBJECT_ID" \
    --headers "Content-Type=application/json" --body "@$ROLES_FILE.body" --output none
rm -f "$ROLES_FILE.body" "$ROLES_FILE.app"
echo -e "${GREEN}✓ App roles updated${NC}"

# The Enterprise App (service principal) is where assignments are made.
if ! az ad sp show --id "$APP_ID" &> /dev/null; then
    az ad sp create --id "$APP_ID" --output none
    echo -e "${GREEN}✓ Created Enterprise App${NC}"
fi
SP_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
# For our own roles app, hide it from users' My Apps portal: it only holds role
# assignments, there's nothing to sign in to. Existing apps are left untouched.
if [ "$OUR_APP" = true ]; then
    az rest --method patch --url "https://graph.microsoft.com/v1.0/servicePrincipals/$SP_ID" \
        --headers "Content-Type=application/json" --body '{"tags":["HideApp","WindowsAzureActiveDirectoryIntegratedApp"]}' \
        --output none
fi

TENANT_ID=$(az account show --query tenantId -o tsv)
echo ""
echo -e "${GREEN}Done.${NC}"
echo ""
echo "  Application (client) ID: $APP_ID"
echo "  Use this as the 'Entra App Id' setting when deploying with mapping mode 'entraAppRoles'."
echo ""
echo "Next: assign groups to roles here:"
echo "  https://entra.microsoft.com/#view/Microsoft_AAD_IAM/ManagedAppMenuBlade/~/Users/objectId/$SP_ID/appId/$APP_ID"
echo ""
echo -e "${YELLOW}Note:${NC} assigning groups (not just individual users) to an app needs Entra ID P1 or P2,"
echo "which is included in Microsoft 365 E3/E5 and Business Premium."
