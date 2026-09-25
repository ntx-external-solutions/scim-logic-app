# Process Manager SCIM Sync

Keep **Nintex Process Manager** roles in step with **Microsoft Entra ID** (formerly Azure AD), automatically.

When someone changes department or joins a group in Entra ID, their roles in Process Manager are updated within minutes. Nobody has to remember to do it by hand.

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fntx-external-solutions%2Fscim-logic-app%2Fmain%2Flogic-app%2Fazuredeploy.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Fntx-external-solutions%2Fscim-logic-app%2Fmain%2Flogic-app%2FcreateUiDefinition.json)

## What it does

```mermaid
flowchart LR
    A["Someone's department<br/>or groups change<br/>in Entra ID"] --> B["Every 15 minutes,<br/>the sync checks<br/>for changes"]
    B --> C["Works out their<br/>Process Manager roles"]
    C --> D["Updates them in<br/>Process Manager"]
```

You choose:

- **What decides roles:** the person's **department**, their **groups**, or **both**.
- **How names become roles:**
  - use the department or group names as they are
  - translate them with a short mapping file
  - assign roles to groups in the **Entra admin center**, just like giving a group access to an app
- **What happens to existing roles:** by default the sync only removes roles *it* gave out, and roles added by hand in Process Manager are left alone.

Not sure which to pick? [Choosing your setup](docs/CHOOSING-YOUR-SETUP.md) explains each option with examples. The defaults (department, names as-is) are a fine place to start, and you can change them later.

## What you need

| | Who usually has it |
|---|---|
| An Azure subscription, with permission to create resources and assign access (**Owner** role) | Your Azure / cloud team |
| An Entra ID **Global Administrator** (or Privileged Role Administrator) for one 2-minute step | Your identity / Microsoft 365 admin |
| A Process Manager **SCIM API token** | Your Process Manager administrator (My Profile → Access Tokens) |

People must already exist in Process Manager: the sync updates their roles but doesn't create accounts. It matches people by email address.

## Install

**About 15 minutes**, all in your web browser.

1. Click **Deploy to Azure** above and fill in the form.
2. Open **Azure Cloud Shell** and run one command to give the sync read access to Entra ID.
3. Test it by changing someone's department.

Step-by-step instructions, with what to click: **[Setup guide](docs/SETUP.md)**.

Prefer the command line? Run `./deploy.sh` from this repository. It asks the same questions and does all three steps.

## Cost

Typically **$2–4 a month** in Azure charges at the default 15-minute check interval. It runs on a Logic App (pay-per-use; the first 4,000 actions each month are free) and a small storage account (pennies). Checking every 5 minutes costs roughly three times as much. Nothing else is billed: no servers, no databases, no licences.

The optional *Enterprise App roles* mapping has no Azure cost. Assigning **groups** to an Enterprise App does need Entra ID P1 or P2, which is included in Microsoft 365 E3, E5 and Business Premium.

## Documentation

| | |
|---|---|
| [Setup guide](docs/SETUP.md) | Installing, step by step |
| [Choosing your setup](docs/CHOOSING-YOUR-SETUP.md) | Department vs groups, the three mapping options, and update modes |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | What to do when a run fails or a role doesn't change |

## Security

- The sync signs in to Microsoft Graph and Azure Storage with its own **managed identity**, so no passwords or keys are stored for either.
- It only ever **reads** Entra ID. The permissions it's granted are read-only.
- The Process Manager SCIM token is stored as a secure parameter in the Logic App. It's hidden from run history, but anyone who can edit the Logic App can see it. Limit who has access to the resource group.
- If you use the role filter, its Process Manager service-account password is stored the same way.

## Support

This is a community solution, not an official Nintex product. For problems with the sync itself, open an issue on this repository. For Process Manager or the SCIM API, contact Nintex support.
