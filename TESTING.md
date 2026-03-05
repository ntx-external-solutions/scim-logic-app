# Testing Guide - Process Manager SCIM Sync Logic App

This guide provides comprehensive testing procedures for the Azure Logic App that syncs Entra ID user updates to Process Manager.

## Prerequisites for Testing

- Logic App deployed and running
- Office 365 API connection authorized
- Role mapping configuration uploaded
- Test user account(s) in Entra ID with Process Manager access
- SCIM API access to Process Manager

## Testing Strategy

We'll test three main scenarios:
1. **Initial sync** - User department is set and synced to Process Manager
2. **Department change** - User's department is updated in Entra ID
3. **Edge cases** - Missing mappings, non-existent users, etc.

## Test Setup

### 1. Prepare Test Users

Create or identify test users in Entra ID:

```bash
# Example: Get a test user's details
az ad user show --id testuser@yourdomain.com
```

Verify the test user:
- Has a valid email address
- Exists in Process Manager (check SCIM API)
- Has a department set (or will set during testing)

### 2. Verify SCIM User Exists

Use the SCIM API to confirm the user exists:

```bash
SCIM_API_KEY="your_scim_api_key"
USER_EMAIL="testuser@yourdomain.com"

curl -X GET \
  "https://api.promapp.com/api/scim/users?filter=userName%20eq%20%22${USER_EMAIL}%22" \
  -H "Authorization: Bearer ${SCIM_API_KEY}" \
  -H "Content-Type: application/json"
```

Expected response:
```json
{
  "Resources": [
    {
      "id": "1234",
      "userName": "testuser@yourdomain.com",
      "name": {
        "givenName": "Test",
        "familyName": "User"
      },
      "roles": [...]
    }
  ],
  "totalResults": 1
}
```

### 3. Check Current Roles

Note the user's current roles in Process Manager before testing.

## Test Cases

### Test Case 1: New Department Assignment (Preserve Mode)

**Objective**: Verify that setting a user's department adds the corresponding role without removing existing roles.

**Steps:**

1. **Note existing roles**:
   ```bash
   # Query SCIM for current roles
   curl -X GET \
     "https://api.promapp.com/api/scim/users?filter=userName%20eq%20%22testuser@yourdomain.com%22" \
     -H "Authorization: Bearer ${SCIM_API_KEY}" | jq '.Resources[0].roles'
   ```

2. **Update department in Entra ID**:
   ```bash
   az ad user update \
     --id testuser@yourdomain.com \
     --department "Engineering"
   ```

3. **Wait for Logic App to trigger** (typically 1-5 minutes):
   - Check Logic App run history in Azure Portal
   - Look for a new run triggered by the user update

4. **Verify the update**:
   ```bash
   # Query SCIM again
   curl -X GET \
     "https://api.promapp.com/api/scim/users?filter=userName%20eq%20%22testuser@yourdomain.com%22" \
     -H "Authorization: Bearer ${SCIM_API_KEY}" | jq '.Resources[0].roles'
   ```

**Expected Result**:
- Previous roles are still present
- New role "Engineering Team" (or your mapped role) is added
- Logic App run shows "Succeeded" status

---

### Test Case 2: Department Change (Preserve Mode)

**Objective**: Verify that changing a user's department adds the new role while preserving existing roles.

**Steps:**

1. Starting state: User has department "Engineering" and role "Engineering Team"

2. **Change department**:
   ```bash
   az ad user update \
     --id testuser@yourdomain.com \
     --department "Sales"
   ```

3. **Wait and verify**:
   ```bash
   curl -X GET \
     "https://api.promapp.com/api/scim/users?filter=userName%20eq%20%22testuser@yourdomain.com%22" \
     -H "Authorization: Bearer ${SCIM_API_KEY}" | jq '.Resources[0].roles'
   ```

**Expected Result**:
- User has both "Engineering Team" and "Sales Team" roles
- All other existing roles are preserved

---

### Test Case 3: Replace Mode

**Objective**: Verify that replace mode removes all existing roles and sets only the department role.

**Prerequisites**:
- Update Logic App parameter `updateMode` to `"replace"`
- Redeploy the Logic App

**Steps:**

1. **Note existing roles** (should have multiple roles from previous tests)

2. **Change department**:
   ```bash
   az ad user update \
     --id testuser@yourdomain.com \
     --department "Marketing"
   ```

3. **Wait and verify**:
   ```bash
   curl -X GET \
     "https://api.promapp.com/api/scim/users?filter=userName%20eq%20%22testuser@yourdomain.com%22" \
     -H "Authorization: Bearer ${SCIM_API_KEY}" | jq '.Resources[0].roles'
   ```

**Expected Result**:
- User has ONLY the "Marketing Team" role
- All previous roles are removed

**Cleanup**: Switch back to `preserve` mode if desired.

---

### Test Case 4: Unmapped Department (Default Role)

**Objective**: Verify that an unmapped department uses the `_default` role.

**Steps:**

1. **Set department to unmapped value**:
   ```bash
   az ad user update \
     --id testuser@yourdomain.com \
     --department "Legal"
   ```
   (Assuming "Legal" is not in your role-mapping.json)

2. **Wait and verify**:
   ```bash
   curl -X GET \
     "https://api.promapp.com/api/scim/users?filter=userName%20eq%20%22testuser@yourdomain.com%22" \
     -H "Authorization: Bearer ${SCIM_API_KEY}" | jq '.Resources[0].roles'
   ```

**Expected Result**:
- User has the default role (e.g., "Standard User")
- Logic App run shows successful execution

---

### Test Case 5: User Not Found in SCIM

**Objective**: Verify graceful handling when a user exists in Entra ID but not in Process Manager.

**Steps:**

1. **Create new user in Entra ID only** (don't add to Process Manager):
   ```bash
   az ad user create \
     --display-name "Test NoSCIM User" \
     --user-principal-name testnosscim@yourdomain.com \
     --password "TempPassword123!" \
     --department "Engineering"
   ```

2. **Wait and check Logic App run**:
   - Navigate to Logic App in Azure Portal
   - Check the latest run details
   - Verify it completes without error

3. **Verify SCIM not updated**:
   ```bash
   curl -X GET \
     "https://api.promapp.com/api/scim/users?filter=userName%20eq%20%22testnosscim@yourdomain.com%22" \
     -H "Authorization: Bearer ${SCIM_API_KEY}"
   ```

**Expected Result**:
- Logic App run succeeds
- "Check_if_user_exists" condition is false
- No SCIM API call is made
- No error is thrown

---

### Test Case 6: Empty Department

**Objective**: Verify handling when user's department is cleared/empty.

**Steps:**

1. **Clear department**:
   ```bash
   az ad user update \
     --id testuser@yourdomain.com \
     --department ""
   ```

2. **Wait and check Logic App run**

**Expected Result**:
- Logic App completes without error
- User's roles in Process Manager remain unchanged OR
- Default role is applied (depending on your mapping configuration)

---

### Test Case 7: Concurrent Updates

**Objective**: Test behavior when multiple updates happen quickly.

**Steps:**

1. **Update department multiple times rapidly**:
   ```bash
   az ad user update --id testuser@yourdomain.com --department "Engineering"
   sleep 2
   az ad user update --id testuser@yourdomain.com --department "Sales"
   sleep 2
   az ad user update --id testuser@yourdomain.com --department "Marketing"
   ```

2. **Monitor Logic App runs**:
   - Check for multiple runs
   - Verify they all complete successfully
   - Check for any conflicts

3. **Verify final state**:
   ```bash
   curl -X GET \
     "https://api.promapp.com/api/scim/users?filter=userName%20eq%20%22testuser@yourdomain.com%22" \
     -H "Authorization: Bearer ${SCIM_API_KEY}" | jq '.Resources[0].roles'
   ```

**Expected Result**:
- Multiple Logic App runs are triggered
- All complete successfully
- Final role matches the last department update
- No errors or conflicts

---

## Monitoring and Debugging

### View Logic App Run History

**Azure Portal:**
1. Navigate to the Logic App resource
2. Click **Overview**
3. Review the "Runs history" section
4. Click on any run to see step-by-step execution

**Azure CLI:**
```bash
# List recent runs
az logic workflow run list \
  --resource-group rg-processmanager-scim \
  --name ProcessManagerSCIMSync \
  --top 10 \
  --query "[].{Name:name, Status:status, StartTime:startTime}" \
  --output table

# View specific run details
az logic workflow run show \
  --resource-group rg-processmanager-scim \
  --name ProcessManagerSCIMSync \
  --run-name <run-name>
```

### Check Action Outputs

For a failed run, examine each action's output:

1. In the Azure Portal, open the failed run
2. Expand each action to see inputs/outputs
3. Look for error messages in HTTP actions
4. Check the "Get_SCIM_users" and "Update_SCIM_user" actions specifically

### Common Errors and Solutions

**Error: "401 Unauthorized" from SCIM API**
- Solution: Verify SCIM API key is correct in Logic App parameters
- Check if the API key has expired

**Error: "404 Not Found" from SCIM API**
- Solution: User doesn't exist in Process Manager
- Verify the userName (email) matches between systems

**Error: "Role not found"**
- Solution: The mapped role doesn't exist in Process Manager
- Check role names in your role-mapping.json
- Verify roles exist in Process Manager admin panel

**Error: "Office365 connection unauthorized"**
- Solution: Re-authorize the Office 365 API connection
- Navigate to the connection in Azure Portal → Edit → Authorize

## Performance Testing

### Bulk Update Test

Test how the Logic App handles many simultaneous updates:

```bash
# Update multiple users' departments
for user in user1@domain.com user2@domain.com user3@domain.com; do
  az ad user update --id $user --department "Engineering" &
done
wait
```

Monitor:
- Logic App throttling behavior
- SCIM API rate limiting
- Overall completion time

## Validation Checklist

After completing all tests, verify:

- [ ] User updates in Entra ID trigger the Logic App
- [ ] Department is correctly mapped to Process Manager role
- [ ] Preserve mode keeps existing roles
- [ ] Replace mode removes existing roles
- [ ] Default role is applied for unmapped departments
- [ ] Non-existent users are handled gracefully
- [ ] No errors in Logic App run history
- [ ] SCIM API updates are reflected in Process Manager UI
- [ ] Performance is acceptable for your user volume

## Test Cleanup

After testing, clean up test data:

```bash
# Remove test users (if created)
az ad user delete --id testnosscim@yourdomain.com

# Reset test user's department to original value
az ad user update \
  --id testuser@yourdomain.com \
  --department "OriginalDepartment"

# Reset test user's roles in Process Manager (use SCIM PUT)
curl -X PUT \
  "https://api.promapp.com/api/scim/users/1234" \
  -H "Authorization: Bearer ${SCIM_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "userName": "testuser@yourdomain.com",
    "name": {"givenName": "Test", "familyName": "User"},
    "active": true,
    "emails": [{"value": "testuser@yourdomain.com"}],
    "roles": [{"display": "Original Role"}]
  }'
```

## Automated Testing

For ongoing validation, consider creating an automated test script:

```bash
#!/bin/bash
# test-scim-sync.sh

RESOURCE_GROUP="rg-processmanager-scim"
LOGIC_APP="ProcessManagerSCIMSync"
TEST_USER="testuser@yourdomain.com"
SCIM_API_KEY="your_api_key"

echo "Starting automated test..."

# Update department
az ad user update --id $TEST_USER --department "Engineering"

# Wait for Logic App
sleep 60

# Check latest run
RUN_STATUS=$(az logic workflow run list \
  --resource-group $RESOURCE_GROUP \
  --name $LOGIC_APP \
  --top 1 \
  --query "[0].status" -o tsv)

if [ "$RUN_STATUS" = "Succeeded" ]; then
  echo "✓ Test passed: Logic App run succeeded"
else
  echo "✗ Test failed: Logic App run status = $RUN_STATUS"
  exit 1
fi

# Verify SCIM update
ROLES=$(curl -s -X GET \
  "https://api.promapp.com/api/scim/users?filter=userName%20eq%20%22${TEST_USER}%22" \
  -H "Authorization: Bearer ${SCIM_API_KEY}" | jq '.Resources[0].roles')

echo "Current roles: $ROLES"
```

## Support and Troubleshooting

If tests fail or unexpected behavior occurs:

1. **Review Logic App run history** for detailed error messages
2. **Check SCIM API directly** to isolate Logic App vs API issues
3. **Verify role mapping** configuration is correctly uploaded
4. **Check Entra ID audit logs** for user update events
5. **Test SCIM API independently** using curl commands
6. **Review Azure service health** for any platform issues

For additional help, refer to the main README.md documentation.
