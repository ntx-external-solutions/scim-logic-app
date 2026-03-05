# Deployment Validation Checklist

Use this checklist to verify your Process Manager SCIM Sync deployment is working correctly.

## Pre-Deployment Checklist

- [ ] Azure CLI installed and working (`az --version`)
- [ ] Logged into correct Azure subscription (`az account show`)
- [ ] Process Manager SCIM API key obtained (Admin → SCIM)
- [ ] Entra ID admin access available
- [ ] Roles exist in Process Manager matching your department/group names

## Post-Deployment Checklist

### 1. Azure Resources Created

Verify all resources were created successfully:

```bash
# Set your resource group name
RESOURCE_GROUP="rg-processmanager-scim"

# List all resources
az resource list --resource-group $RESOURCE_GROUP --output table
```

**Expected resources:**
- [ ] Logic App (ProcessManagerSCIMSync)
- [ ] Storage Account (pmscimconfig*)
- [ ] 2 API Connections (office365-*, azureblob-*)

### 2. Logic App Status

```bash
az logic workflow show \
  --resource-group $RESOURCE_GROUP \
  --name ProcessManagerSCIMSync \
  --query "{Name:name, State:state, Location:location}" \
  --output table
```

**Verify:**
- [ ] State: `Enabled`
- [ ] Location: Your selected region

### 3. API Connections Authorized

**Office 365 Connection:**

```bash
# Check Office 365 connection status
az resource show \
  --ids $(az resource list \
    --resource-group $RESOURCE_GROUP \
    --resource-type Microsoft.Web/connections \
    --query "[?contains(name, 'office365')].id" -o tsv) \
  --query "properties.statuses[0].status" -o tsv
```

**Expected:** `Connected` or `Error` (if not authorized yet)

- [ ] Office 365 connection shows as "Connected"
- [ ] If not connected: Go to Azure Portal and authorize

**Azure Blob Connection:**

```bash
# Check Blob connection status
az resource show \
  --ids $(az resource list \
    --resource-group $RESOURCE_GROUP \
    --resource-type Microsoft.Web/connections \
    --query "[?contains(name, 'azureblob')].id" -o tsv) \
  --query "properties.statuses[0].status" -o tsv
```

- [ ] Azure Blob connection shows as "Connected"

### 4. Configuration Files

**Dynamic Mode:**
- [ ] No configuration file needed ✓

**Mapped Mode:**

```bash
# List blobs in config container
STORAGE_ACCOUNT=$(az storage account list \
  --resource-group $RESOURCE_GROUP \
  --query "[0].name" -o tsv)

STORAGE_KEY=$(az storage account keys list \
  --resource-group $RESOURCE_GROUP \
  --account-name $STORAGE_ACCOUNT \
  --query "[0].value" -o tsv)

az storage blob list \
  --account-name $STORAGE_ACCOUNT \
  --account-key $STORAGE_KEY \
  --container-name config \
  --output table
```

- [ ] role-mapping.json exists in config container
- [ ] File size > 0 bytes

### 5. Logic App Workflow Definition

```bash
# Check workflow has correct trigger
az logic workflow show \
  --resource-group $RESOURCE_GROUP \
  --name ProcessManagerSCIMSync \
  --query "definition.triggers" \
  --output json | grep -q "When_a_user_is_updated" && echo "✓ Trigger configured" || echo "✗ Trigger missing"
```

- [ ] Trigger: "When_a_user_is_updated" exists

## Functional Testing

### Test 1: Department Sync

**Setup:**
1. Identify a test user in Entra ID
2. Note their current department
3. Note their current roles in Process Manager

**Test Steps:**

1. Update user's department in Entra ID:
   ```bash
   # Using Azure CLI (optional)
   az ad user update \
     --id user@domain.com \
     --department "Engineering"
   ```
   Or use Azure Portal: Azure AD → Users → Select user → Edit → Department

2. Wait 1-2 minutes for Logic App to trigger

3. Check Logic App run history:
   ```bash
   az logic workflow run list \
     --resource-group $RESOURCE_GROUP \
     --name ProcessManagerSCIMSync \
     --top 1 \
     --output table
   ```

4. Verify in Process Manager:
   - Log into Process Manager
   - Go to Admin → Users
   - Find the test user
   - Check their roles

**Expected Result:**
- [ ] Logic App run shows "Succeeded"
- [ ] User has role matching department name (or mapped role)
- [ ] Existing roles preserved (if preserve mode) or replaced (if replace mode)

### Test 2: Group Sync

**Setup:**
1. Create or identify a test group in Entra ID
2. Identify a test user

**Test Steps:**

1. Add user to group in Entra ID:
   ```bash
   # Using Azure CLI (optional)
   GROUP_ID=$(az ad group show --group "ProcessManager-Editors" --query id -o tsv)
   USER_ID=$(az ad user show --id user@domain.com --query id -o tsv)
   az ad group member add --group $GROUP_ID --member-id $USER_ID
   ```
   Or use Azure Portal: Azure AD → Groups → Members → Add

2. Trigger the Logic App by updating the user:
   ```bash
   # Update any user field to trigger the Logic App
   az ad user update \
     --id user@domain.com \
     --job-title "Test Title"
   ```

3. Wait 1-2 minutes

4. Check Logic App run:
   ```bash
   az logic workflow run list \
     --resource-group $RESOURCE_GROUP \
     --name ProcessManagerSCIMSync \
     --top 1 \
     --query "[].{Name:name, Status:status, StartTime:startTime}" \
     --output table
   ```

5. Verify in Process Manager

**Expected Result:**
- [ ] Logic App run shows "Succeeded"
- [ ] User has role matching group name (or mapped role)
- [ ] Both department role AND group role are assigned

### Test 3: Multiple Groups

**Test Steps:**

1. Add user to multiple groups
2. Update user to trigger Logic App
3. Verify user has roles for ALL groups they're a member of

**Expected Result:**
- [ ] User has roles for department + all groups
- [ ] No duplicate roles
- [ ] All roles from groups are present

### Test 4: Error Handling

**Test Steps:**

1. Update a user's department to a value that doesn't map to any role
2. Check Logic App run history
3. Verify appropriate handling

**Expected Result (Dynamic Mode):**
- [ ] Logic App run succeeds but doesn't update user (no matching role)

**Expected Result (Mapped Mode):**
- [ ] User gets the `_default` role if configured
- [ ] Or Logic App succeeds without updating if no default

## Performance Testing

### Test 5: Multiple User Updates

**Test Steps:**

1. Update 5-10 users in quick succession
2. Monitor Logic App runs
3. Check all runs complete successfully

```bash
# Monitor runs in real-time
watch -n 5 'az logic workflow run list \
  --resource-group $RESOURCE_GROUP \
  --name ProcessManagerSCIMSync \
  --top 10 \
  --output table'
```

**Expected Result:**
- [ ] All runs complete within 2-3 minutes
- [ ] All runs show "Succeeded"
- [ ] No throttling errors

## Monitoring Setup

### Test 6: Failed Run Alert (Optional)

Set up an alert for failed Logic App runs:

```bash
# Create action group (email notification)
az monitor action-group create \
  --resource-group $RESOURCE_GROUP \
  --name LogicAppFailureAlert \
  --short-name LAFailure \
  --email-receiver admin admin@yourcompany.com

# Create alert rule
az monitor metrics alert create \
  --resource-group $RESOURCE_GROUP \
  --name logic-app-failures \
  --scopes $(az logic workflow show \
    --resource-group $RESOURCE_GROUP \
    --name ProcessManagerSCIMSync \
    --query id -o tsv) \
  --condition "total RunsFailed > 0" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --action $(az monitor action-group show \
    --resource-group $RESOURCE_GROUP \
    --name LogicAppFailureAlert \
    --query id -o tsv)
```

- [ ] Alert rule created
- [ ] Test alert by intentionally causing a failure

## Security Validation

### Test 7: SCIM API Key Security

- [ ] SCIM API key is stored as SecureString parameter
- [ ] Key is not visible in run history
- [ ] Key is not in any git-tracked files

### Test 8: Least Privilege Access

```bash
# Verify Logic App uses managed connections
az logic workflow show \
  --resource-group $RESOURCE_GROUP \
  --name ProcessManagerSCIMSync \
  --query "parameters.\$connections" \
  --output json
```

- [ ] Connections use OAuth (Office 365)
- [ ] No hardcoded credentials in workflow

## Documentation Verification

- [ ] README.md exists and is up-to-date
- [ ] QUICKSTART.md provides clear setup instructions
- [ ] TESTING.md has comprehensive test cases
- [ ] config/role-mapping.json has example mappings
- [ ] .gitignore prevents committing secrets

## Cleanup Test

### Test 9: Resource Deletion (Optional)

To verify clean removal:

```bash
# Delete resource group
az group delete --name $RESOURCE_GROUP --yes --no-wait

# Verify deletion
az group exists --name $RESOURCE_GROUP
```

**Expected:** Returns `false` after deletion completes

---

## Validation Summary

**Total Tests:** 9 required, 0 optional
**Passed:** ___
**Failed:** ___

### Common Issues and Resolutions

| Issue | Likely Cause | Resolution |
|-------|--------------|------------|
| Logic App not triggering | Office 365 connection not authorized | Re-authorize in Azure Portal |
| User not found in SCIM | Email mismatch | Verify email matches userName in Process Manager |
| Role not assigned | Role doesn't exist in PM | Create role or update mapping |
| Multiple duplicate roles | Logic App ran multiple times | Use preserve mode or check for duplicate triggers |
| Slow execution | Many group memberships | Normal - each group requires API call |

### Next Steps After Validation

- [ ] Document your specific department/group → role mappings
- [ ] Train team on monitoring and troubleshooting
- [ ] Set up regular review of role assignments
- [ ] Consider automating onboarding/offboarding processes

---

**Last Validated:** ___________
**Validated By:** ___________
**Environment:** ___________
