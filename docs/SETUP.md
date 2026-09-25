# Setup guide

This takes about **15 minutes**, all in a web browser. You don't need to install anything.

**Before you start**, decide on your setup. If you're unsure, use the defaults (**department**, **use the names as they are**, **managed**). [Choosing your setup](CHOOSING-YOUR-SETUP.md) explains the options.

You'll need:

- An Azure account with the **Owner** role on the subscription (or on the resource group you'll install into).
- For step 4, an Entra ID **Global Administrator** or **Privileged Role Administrator**. It takes two minutes, so they can do just that step.

---

## Step 1: Get your Process Manager SCIM token

1. Sign in to Process Manager as an administrator.
2. Go to **My Profile** → **Access Tokens**.
3. Generate a token and copy it somewhere safe for the next few minutes.

## Step 2 (only for Enterprise App roles): Create the roles app

*Skip this step unless you chose "Assign roles in the Entra admin center".*

1. Go to [portal.azure.com](https://portal.azure.com) and click the **Cloud Shell** icon (`>_`) at the top of the page.
2. If asked, choose **Bash**, then **No storage account required**, and pick your subscription.
3. Paste this and press Enter:

   ```bash
   bash <(curl -sL https://raw.githubusercontent.com/ntx-external-solutions/scim-logic-app/main/scripts/create-role-app.sh)
   ```

4. When asked, paste your SCIM token. The script uses it once to read your Process Manager role names; it isn't stored.
5. Copy the **Application (client) ID** it prints at the end. You'll need it in step 3.

The script creates an app called **Process Manager Roles** with one app role for each Process Manager role that's assigned to at least one person. To add a role nobody has yet, run it again with the role names in quotes:

```bash
bash <(curl -sL https://raw.githubusercontent.com/ntx-external-solutions/scim-logic-app/main/scripts/create-role-app.sh) "Auditor" "Process Owner"
```

<details>
<summary>Already use the Nintex Process Manager app from the Entra gallery?</summary>

You can add the roles to that app instead of creating a new one. Find its **Application ID** on the app's Overview page in the Entra admin center, then run:

```bash
APP_ID=<the application id> bash <(curl -sL https://raw.githubusercontent.com/ntx-external-solutions/scim-logic-app/main/scripts/create-role-app.sh)
```

Only the app roles you add here count towards Process Manager roles. The gallery app's built-in roles (such as "User" and "msiam_access") are ignored.
</details>

## Step 3: Deploy

1. Click this button (it opens the Azure Portal):

   [![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fntx-external-solutions%2Fscim-logic-app%2Fmain%2Flogic-app%2Fazuredeploy.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Fntx-external-solutions%2Fscim-logic-app%2Fmain%2Flogic-app%2FcreateUiDefinition.json)

2. On **Basics**:
   - **Subscription:** the one to bill.
   - **Resource group:** click **Create new** and call it something like `rg-processmanager-scim`.
   - **Region:** any; pick one near you.
   - **Process Manager SCIM API token:** paste the token from step 1.
3. On **How roles are chosen**, pick your setup. For Enterprise App roles, paste the Application ID from step 2.
4. On **Options**, the defaults are fine. You might want:
   - **Update every existing user on the first run:** tick this to bring everyone into line straight away. Otherwise only people who change after today are updated.
   - **Role filter:** see [Choosing your setup](CHOOSING-YOUR-SETUP.md#role-filter).
5. Click **Review + create**, then **Create**. It takes a minute or two.

> **"Authorization failed" or an error mentioning `roleAssignments`?** Your Azure account needs the **Owner** role (or *User Access Administrator*) to finish the install. It lets the sync store its progress without a password. Ask your Azure administrator.

## Step 4: Give the sync read access to Entra ID and switch it on

The sync is installed **switched off**. This step gives it permission to read people and groups from Entra ID, then switches it on. Only an Entra ID **Global Administrator** or **Privileged Role Administrator** can grant the permission.

1. Open **Cloud Shell** again (as in step 2).
2. Paste this, changing the resource group name if you used a different one:

   ```bash
   bash <(curl -sL https://raw.githubusercontent.com/ntx-external-solutions/scim-logic-app/main/scripts/grant-permissions.sh) rg-processmanager-scim
   ```

   You should see a green tick for each permission, a two-minute wait while the permissions take effect, then **Sync switched on**.

The script only grants what your setup needs, and all of it is read-only:

| Permission | Why |
|---|---|
| `User.Read.All` | Read people's department and email address |
| `GroupMember.Read.All` | Read group memberships (only with Groups or Both) |
| `Application.Read.All` | Read the Enterprise App's role assignments (only with Enterprise App roles) |

The sync is switched on only after the permissions have had time to take effect. If it started earlier, it could get stuck without them for hours.

## Step 5 (only for a mapping file): Upload role-mapping.json

*Skip this step unless you chose "Translate with a mapping file".*

1. Write your mapping file. Start from [the example](../config/role-mapping.json); [Choosing your setup](CHOOSING-YOUR-SETUP.md#mapping-file-option-a) explains each field.
2. In the Azure Portal, open your resource group, then the **storage account** (its name starts with `pmscim`).
3. Go to **Data storage** → **Containers** → **config**.
4. Click **Upload**, choose your `role-mapping.json`, tick **Overwrite if files already exist**, and click **Upload**.

To change the mapping later, upload a new version the same way. The next run picks it up.

## Step 6: Check it works

The first check runs as soon as step 4 switches the sync on, then every 15 minutes (or whatever interval you chose).

1. Pick a test person who already exists in Process Manager.
2. In the Entra admin center, change what drives their roles:
   - **Department:** Users → the person → **Properties** → edit **Department**.
   - **Groups:** Groups → a group → **Members** → **Add members**.
   - **Enterprise App roles:** Enterprise applications → *Process Manager Roles* → **Users and groups** → **Add user/group**, then pick a group and a role.
3. Wait for the next run. Entra ID can take a couple of minutes to report a change, so if it's not picked up straight away, it will be on the following run.
4. Check the person's roles in Process Manager (**Admin** → **Users**). Refresh the page if it was already open.

To see what happened, open the Logic App in the Azure Portal and go to **Overview** → **Run history**. Click a run to see each step. A green tick means it worked.

Something not right? See [Troubleshooting](TROUBLESHOOTING.md).

---

## Changing your setup later

Redeploy with the new choices: click **Deploy to Azure** again, choose the **same resource group**, and use the same Logic App name. Your sync progress is kept.

**Redeploying switches the sync off, so always repeat step 4 afterwards.** It adds any permissions your new setup needs, then switches the sync back on.

## Removing it

Delete the resource group in the Azure Portal. That removes the Logic App and its storage account. If you created the *Process Manager Roles* Enterprise App, delete it in the Entra admin center under **App registrations**. Nothing in Process Manager is changed by removing the sync.
