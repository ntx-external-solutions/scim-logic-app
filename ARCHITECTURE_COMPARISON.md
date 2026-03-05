# Architecture Comparison: Unified vs Separate Logic Apps

This document compares the two architectural approaches for syncing Entra ID to Process Manager roles.

## Summary

| Aspect | Unified (1 Logic App) | Separate (2 Logic Apps) |
|--------|----------------------|------------------------|
| **Number of Logic Apps** | 1 | 2 |
| **Triggers** | User updates only | User updates + Group updates |
| **SCIM API calls per event** | 1 | 1-2 (depends on which triggers) |
| **Complexity** | Lower | Higher |
| **Maintenance** | Easier | More complex |
| **Cost** | Lower (~$1/month) | Slightly higher (~$1-2/month) |
| **Recommended** | ✅ Yes | Use only if you need group-only triggers |

## Unified Approach (Recommended)

**File**: `logic-app/azuredeploy-unified.json`

### How It Works

```
User Updated in Entra ID
         ↓
   Get User Profile
         ↓
   Get User's Groups
         ↓
Map Both Department & Groups to Roles (via mapping mode)
         ↓
  Combine All Roles
         ↓
 Filter Null/Empty Roles
         ↓
    Find User in SCIM
         ↓
 Update User with All Roles
```

### Advantages

1. **Simpler**: Single workflow to understand and maintain
2. **More efficient**: One SCIM update per user change (not two separate updates)
3. **Automatic deduplication**: Combines department and group roles without duplicates
4. **Lower cost**: Fewer action executions
5. **Easier troubleshooting**: Single run history to check

### Disadvantages

1. **Only triggers on user updates**: Won't update roles when you only change group membership without updating the user
2. **Workaround**: Update any user field (like job title) to trigger the sync after group changes

### When to Use

- **Default choice** for most scenarios
- When you primarily update users and their departments
- When you want simplicity and lower costs
- When occasional manual triggers are acceptable

## Separate Approach

**Files**: `logic-app/azuredeploy.json`

### How It Works

**Department Sync:**
```
User Updated in Entra ID
         ↓
   Get User Profile
         ↓
  Get Department
         ↓
Map Department to Role
         ↓
    Find User in SCIM
         ↓
Update User with Department Role
```

**Group Sync:**
```
Group Updated in Entra ID
         ↓
   Get Group Members
         ↓
For Each Member:
   Get User's Groups
         ↓
  Map Groups to Roles
         ↓
    Find User in SCIM
         ↓
Update User with Group Roles
```

### Advantages

1. **Immediate group sync**: Updates roles immediately when group membership changes
2. **Independent workflows**: Department and group sync don't interfere
3. **Fine-grained control**: Can enable/disable each sync independently

### Disadvantages

1. **More complex**: Two separate workflows to maintain
2. **Potential for conflicts**: If both trigger at once, roles might get overwritten
3. **Higher cost**: More action executions
4. **Harder to troubleshoot**: Need to check two run histories

### When to Use

- When you frequently add/remove users from groups without updating user profiles
- When you need immediate role updates on group membership changes
- When you want to sync only groups or only departments (disable one workflow)

## Migration Between Approaches

### From Separate to Unified

1. **Disable the separate Logic Apps**:
   ```bash
   az logic workflow update \
     --resource-group rg-processmanager-scim \
     --name ProcessManagerSCIMSync \
     --state Disabled

   az logic workflow update \
     --resource-group rg-processmanager-scim \
     --name ProcessManagerSCIMSync-GroupSync \
     --state Disabled
   ```

2. **Enable the unified Logic App**:
   ```bash
   az logic workflow update \
     --resource-group rg-processmanager-scim \
     --name ProcessManagerSCIMSync-Unified \
     --state Enabled
   ```

3. **Test**: Update a user's department in Entra ID and verify roles sync

### From Unified to Separate

1. **Disable the unified Logic App**:
   ```bash
   az logic workflow update \
     --resource-group rg-processmanager-scim \
     --name ProcessManagerSCIMSync-Unified \
     --state Disabled
   ```

2. **Enable both separate Logic Apps**:
   ```bash
   az logic workflow update \
     --resource-group rg-processmanager-scim \
     --name ProcessManagerSCIMSync \
     --state Enabled

   az logic workflow update \
     --resource-group rg-processmanager-scim \
     --name ProcessManagerSCIMSync-GroupSync \
     --state Enabled
   ```

3. **Test**: Update a user and change group membership

## Current Deployment Status

You currently have **all three Logic Apps** deployed:

| Logic App Name | Status | Purpose |
|----------------|--------|---------|
| ProcessManagerSCIMSync | Enabled | Department sync only |
| ProcessManagerSCIMSync-GroupSync | Enabled | Group sync only |
| ProcessManagerSCIMSync-Unified | Enabled | Both department and group sync |

**⚠️ Warning**: Having all three enabled may cause duplicate updates.

## Recommended Configuration

**Option 1: Use Unified Only** (Recommended)
```bash
# Disable separate Logic Apps
az logic workflow update --resource-group rg-processmanager-scim --name ProcessManagerSCIMSync --state Disabled
az logic workflow update --resource-group rg-processmanager-scim --name ProcessManagerSCIMSync-GroupSync --state Disabled
# Keep unified enabled (already enabled)
```

**Option 2: Use Separate Only**
```bash
# Disable unified Logic App
az logic workflow update --resource-group rg-processmanager-scim --name ProcessManagerSCIMSync-Unified --state Disabled
# Keep separate enabled (already enabled)
```

## Feature Comparison

| Feature | Unified | Separate |
|---------|---------|----------|
| Syncs department on user update | ✅ | ✅ |
| Syncs groups on user update | ✅ | ✅ |
| Syncs groups on group update | ❌ | ✅ |
| Combines department + group roles | ✅ | ⚠️ (may conflict) |
| Single SCIM update per trigger | ✅ | ❌ |
| No duplicate role assignments | ✅ | ⚠️ (possible) |
| Simple troubleshooting | ✅ | ❌ |
| Lower action count | ✅ | ❌ |

## Cost Comparison

Based on 1000 user updates per month:

**Unified Approach:**
- 1 trigger × 1000 = 1000 actions
- ~10 actions per run × 1000 = 10,000 actions
- Total: ~$1.25/month

**Separate Approach:**
- Department: ~10 actions × 1000 user updates = 10,000 actions
- Group: ~15 actions × 500 group updates = 7,500 actions
- Total: ~$2.19/month

## Testing Both Approaches

### Test Unified Logic App

1. Update a user's department in Entra ID
2. Add the user to a group
3. Check the Logic App run history:
   ```bash
   az logic workflow run list \
     --resource-group rg-processmanager-scim \
     --name ProcessManagerSCIMSync-Unified \
     --top 1
   ```
4. Verify the user has roles from both department and groups

### Test Separate Logic Apps

1. Update a user's department (triggers Department Sync)
2. Add a user to a group (triggers Group Sync)
3. Check both run histories:
   ```bash
   az logic workflow run list \
     --resource-group rg-processmanager-scim \
     --name ProcessManagerSCIMSync \
     --top 1

   az logic workflow run list \
     --resource-group rg-processmanager-scim \
     --name ProcessManagerSCIMSync-GroupSync \
     --top 1
   ```

## Recommendation

**Use the Unified approach** unless you have a specific requirement for immediate group-only updates.

To switch to unified:
```bash
# Disable the separate Logic Apps
az logic workflow update --resource-group rg-processmanager-scim --name ProcessManagerSCIMSync --state Disabled
az logic workflow update --resource-group rg-processmanager-scim --name ProcessManagerSCIMSync-GroupSync --state Disabled
```

The unified Logic App is already enabled and ready to use!

## Cleanup

If you decide to stick with one approach, you can delete the unused Logic Apps to reduce clutter:

**Keep Unified, Remove Separate:**
```bash
az logic workflow delete --resource-group rg-processmanager-scim --name ProcessManagerSCIMSync --yes
az logic workflow delete --resource-group rg-processmanager-scim --name ProcessManagerSCIMSync-GroupSync --yes
```

**Keep Separate, Remove Unified:**
```bash
az logic workflow delete --resource-group rg-processmanager-scim --name ProcessManagerSCIMSync-Unified --yes
```
