# Releasing

## Before merging to `main`

The **Deploy to Azure** button and the Cloud Shell commands in the setup guide all pull from `main`. Anything merged is live for the next customer who installs.

- [ ] `python3 tools/generate_template.py` has been run, and `logic-app/azuredeploy.json` is committed with it.
- [ ] `az deployment group validate` passes for the template.
- [ ] The scenarios in [DEVELOPING.md](DEVELOPING.md#testing-changes) affected by the change pass on a test tenant.
- [ ] If parameters changed: `createUiDefinition.json`, `deploy.sh`, `azuredeploy.parameters.template.json` and the customer docs match.
- [ ] No secrets committed: `git grep -n -i "bearer\|password\|secret"` shows nothing real.

To try the portal form before merging, paste `createUiDefinition.json` into the [Create UI Definition sandbox](https://portal.azure.com/#view/Microsoft_Azure_CreateUIDef/SandboxBlade).

## Versioning

Tag releases `vMAJOR.MINOR.PATCH` and add release notes on GitHub.

- **Major:** existing installs need action to upgrade (for example a renamed parameter or a changed mapping file format).
- **Minor:** new options, backwards compatible.
- **Patch:** fixes.

## Upgrading existing installs

Customers upgrade by redeploying into the same resource group with the same Logic App name, then running `scripts/grant-permissions.sh` (redeploying leaves the Logic App disabled). Call out in the release notes anything that changes behaviour for an existing setup.

### v1 → v2 notes

- **New settings:** Role source (`roleSource`, default `department`; v1 always used both) and update mode `managed` (now the default; v1 defaulted to `preserve`). Customers relying on v1 behaviour should choose `both` and `preserve` explicitly.
- **Storage:** v2 creates its own storage account and reaches it with the managed identity. The `azureblob-*` API connection from v1 is no longer used and can be deleted. `deploy.sh` no longer asks for a storage account name. An upgrade through `deploy.sh` or the button therefore creates a new storage account and starts tracking changes from that moment. Copy `role-mapping.json` across if you use one.
- **Mapping file:** the v1 format still works, but `groupMapping._default` is no longer applied to every unmapped group. Use `defaultRole`.
- **Removed:** `azuredeploy-separate.json` (the old webhook-based version) and the Office 365 connection.
