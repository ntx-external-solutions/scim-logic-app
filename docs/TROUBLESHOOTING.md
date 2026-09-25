# Troubleshooting

## Where to look

Everything the sync does is recorded in the Logic App's **run history**:

1. In the Azure Portal, open your resource group, then the Logic App (`ProcessManagerSCIMSync` unless you renamed it).
2. Go to **Overview** → **Run history**. Each row is one check for changes.
3. Click a run to see every step. A green tick means the step worked, a red cross means it failed, and grey means it was skipped because it wasn't needed.

A run that failed has an error message at the top explaining why. The messages are listed below.

## A run failed

### "Microsoft Graph refused the request..."

The sync doesn't have permission to read Entra ID yet.

- **Just installed?** Make sure [step 4 of the setup guide](SETUP.md#step-4-give-the-sync-read-access-to-entra-id-and-switch-it-on) was run by an Entra ID Global Administrator and showed green ticks.
- **Just changed your setup** (for example from Department to Groups)? Run step 4 again. The new setup needs an extra permission.
- **Ran step 4 but it still fails?** Azure caches the sync's sign-in for a while. If the sync was already running when a permission was added, the permission can take **up to 24 hours** to take effect. It will start working on its own; no changes are lost in the meantime.

### "Could not read sync progress from the storage account..."

The sync can't reach its storage account. Straight after installing, this can happen for a few minutes while access is set up, and it fixes itself. If it continues, check that the Logic App still has the **Storage Blob Data Contributor** role on the storage account (storage account → **Access control (IAM)** → **Role assignments**). Redeploying puts it back.

### "Could not read role-mapping.json..."

Mapping mode is set to *mapping file*, but the file isn't in storage. Upload it: see [step 5 of the setup guide](SETUP.md#step-5-only-for-a-mapping-file-upload-role-mappingjson). The file must be called exactly `role-mapping.json`, in the `config` container.

If the run fails at **Save_mapping** instead, the file is there but isn't valid JSON (usually a missing comma or quote). Paste it into any online JSON validator to find the problem.

### "Could not read the Enterprise App's roles..."

- Check the **Enterprise App ID** setting is the *Application (client) ID*, not the Object ID. Both are on the app's Overview page.
- Run step 4 of the setup guide again: Enterprise App roles need an extra permission (`Application.Read.All`).

### "The role filter could not sign in to Process Manager..."

The role filter's service account can't sign in. Check the site URL (no slash at the end), username and password. The account must **not** use multi-factor sign-in. Repeated failures can lock the account; turn the filter off until the details are fixed.

### "One or more users could not be updated in Process Manager"

The sync worked out the right roles but Process Manager refused the update for some people.

1. Open the run and click **For_each_changed_user**. Use the arrows to page through the people it processed; failed ones are marked red.
2. Click the failed step (usually **Get_SCIM_user** or **Update_SCIM_user**) to see Process Manager's response.
   - **401 Unauthorized:** the SCIM token has expired or been regenerated. Create a new token in Process Manager and redeploy with it, then run step 4 of the setup guide.
   - **Other errors:** contact Nintex support with the response shown.

Failed people aren't retried automatically. Once the cause is fixed, make any small change to them in Entra ID (or re-save their department) to sync them again.

## A run succeeded, but someone's roles didn't change

Work through these in order:

1. **Has the change been picked up yet?** Entra ID can take a couple of minutes to report a change, so it may land in the run *after* the one you expected. Check the latest run: if **For_each_changed_user** ran, click it to see who was processed.
2. **Is the sync switched on?** On the Logic App's **Overview** page, the status should be **Enabled**. Redeploying switches it off; run step 4 of the setup guide to switch it back on.
3. **Does the person exist in Process Manager with the same email address?** The sync matches people by their Entra ID email (or, if they have none, their sign-in name). It doesn't create accounts.
4. **Is the Process Manager page up to date?** Refresh it. Pages opened before the sync ran show the old roles.
5. **Did the setup rules give them that role?**
   - *Use the names as they are:* the department or group name must be exactly the role name.
   - *Mapping file:* check the spelling in `role-mapping.json`. With `oneGroupRoleOnly`, only the first matching group line counts.
   - *Enterprise App roles:* check the person (or a group they're **directly** in) is assigned to the role on the app's **Users and groups** page.
   - *Role filter on:* the role must already exist in Process Manager.
   - *Groups:* only groups the person is **directly** in count. Membership through a group inside another group isn't included.
6. **Expected a role to be removed?** It depends on the [update mode](CHOOSING-YOUR-SETUP.md#3-update-mode):
   - *Managed* only removes roles the sync gave out. Roles someone had before the sync first touched them, or that were added by hand, are kept.
   - *Preserve* never removes roles.
   - *Replace* won't remove someone's last role.

## Update everyone again from scratch

To re-check every person (for example after changing your mapping), make the sync forget its progress:

1. Open the storage account (name starts with `pmscim`) → **Containers** → **config** → **state**.
2. Delete `users-delta.txt` and `groups-delta.txt`.
3. Redeploy with **Update every existing user on the first run** ticked, then run step 4 of the setup guide.

The next run then goes through everyone. In a large organisation this run can take a while.

## Still stuck?

Open an issue on this repository. Include the failed step's name and error message from the run history, but **not** your SCIM token or any passwords.
