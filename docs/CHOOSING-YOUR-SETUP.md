# Choosing your setup

Three settings decide how Process Manager SCIM Sync gives people roles. You pick them when you install, and you can change them later by redeploying. This page explains each one in plain terms, with a recommendation.

| Setting | Question it answers | Options |
|---|---|---|
| [Role source](#1-role-source) | What in Entra ID decides someone's roles? | Department, Groups, or Both |
| [Mapping mode](#2-mapping-mode) | How do Entra ID names turn into Process Manager role names? | Dynamic, Mapping file, or Enterprise App roles |
| [Update mode](#3-update-mode) | What happens to roles people already have? | Managed, Preserve, or Replace |

**Not sure? Start with Department + Dynamic + Managed.** It's the simplest to set up and the easiest to understand, and you can switch later.

---

## 1. Role source

### Department

The **Department** field on each person's Entra ID profile becomes their Process Manager role. Each person gets one role.

- The sync only runs for someone when their department changes.
- Best when your departments line up with how you organise Process Manager (Finance, HR, IT...).
- Needs the least setup and the fewest permissions.

### Groups

The Entra ID **groups** each person belongs to become their Process Manager roles.

- The sync runs for someone when they're added to or removed from a group.
- Best when you already manage access with groups, or people need more than one role.
- Most organisations have many groups that have nothing to do with Process Manager. Pair Groups with a [mapping file or Enterprise App roles](#2-mapping-mode), or with the [role filter](#role-filter), so only the groups you care about count.

### Both

Department **and** groups together. Someone in the Finance department who's also in the "PM - Editors" group gets both roles.

---

## 2. Mapping mode

### Dynamic: use names as they are

The department or group name *is* the role name. The department "Finance" gives the role "Finance". The group "PM - Editors" gives the role "PM - Editors".

- Nothing to configure.
- Names must match your Process Manager roles exactly. If a name doesn't match any role, Process Manager creates a new role with that name, unless you turn on the [role filter](#role-filter).
- With Groups, **every** group someone belongs to becomes a role, unless you turn on the [role filter](#role-filter).

### Mapping file (option A)

A short file, `role-mapping.json`, lists which departments and groups give which roles. Anything not listed is ignored.

```json
{
  "departmentRoles": [
    { "department": "Finance", "role": "Finance Team" },
    { "department": "Human Resources", "role": "HR Team" }
  ],
  "groupRoles": [
    { "group": "PM - Administrators", "role": "Administrator" },
    { "group": "PM - Process Editors", "role": "Process Editor" },
    { "group": "All Staff", "role": "Process Viewer" }
  ],
  "oneGroupRoleOnly": false,
  "defaultRole": ""
}
```

| Field | What it does |
|---|---|
| `departmentRoles` | Department name → role. Capitals and extra spaces don't matter. |
| `groupRoles` | Group → role. Use the group's name, or its **Object ID** from the Entra admin center if the group might be renamed. |
| `oneGroupRoleOnly` | `true` gives each person only **one** role from their groups: the **first** matching line in `groupRoles`. Put your most important groups at the top. Useful when people are in several groups but should have a single role. |
| `defaultRole` | Role for anyone who matches nothing. Leave as `""` to give no role. |

**Best for:** a handful of rules that rarely change, set up by someone comfortable editing a small text file.

**To change it later:** edit the file and upload it again. In the Azure Portal, open the storage account (its name starts with `pmscim`), go to **Containers** → **config**, and upload `role-mapping.json` with "Overwrite" ticked. The next run uses it.

<details>
<summary>Using a mapping file from an older version?</summary>

The old format (`departmentMapping` / `groupMapping` objects) still works. One behaviour changed: the old `groupMapping._default` gave the default role for *every* unmapped group. Now unmapped groups are ignored. Use `defaultRole` if you want a fallback.
</details>

### Enterprise App roles (option B)

You manage the mapping **in the Entra admin center**, with no file to edit. An Enterprise App (called "Process Manager Roles" unless you choose another name) has one *app role* per Process Manager role. You assign groups, or individual people, to those roles on the app's **Users and groups** page, just as you would give a group access to any other app.

- Only groups you assign count. Being in 200 other groups makes no difference.
- Changes are recorded in Entra ID's audit log, like any other access change.
- When you change an assignment, everyone it affects is updated on the next run.
- If you already use the **Nintex Process Manager** app from the Entra gallery, you can add roles to that app instead of creating a new one.

**Requirements:**
- Role source must be **Groups** or **Both**.
- Assigning *groups* to an app needs **Entra ID P1 or P2**. It's included in Microsoft 365 E3/E5 and Business Premium. Without P1 you can still assign individual people.
- An admin runs one setup script ([setup guide, step 2](SETUP.md#step-2-only-for-enterprise-app-roles-create-the-roles-app)).

**Best for:** organisations with many groups, where IT admins already manage access in Entra ID and want Process Manager handled the same way.

### Which should I choose?

| | Dynamic | Mapping file (A) | Enterprise App roles (B) |
|---|---|---|---|
| Setup effort | None | Edit one file | Run one script |
| Where you manage it | Entra ID names | A file in Azure Storage | Entra admin center |
| Many unrelated groups | Needs the role filter | Only listed groups count | Only assigned groups count |
| Group renamed | Role changes too | Use Object IDs to be safe | Not affected |
| Extra licence | No | No | Entra ID P1 for group assignments |
| Extra Azure cost | No | No | No |

---

## 3. Update mode

This decides what happens to roles someone **already has** in Process Manager.

| Mode | Adds roles from Entra ID | Removes roles the sync gave out | Removes roles added by hand in Process Manager |
|---|---|---|---|
| **Managed** (recommended) | ✓ | ✓ | ✗ |
| Preserve | ✓ | ✗ | ✗ |
| Replace | ✓ | ✓ | ✓ |

**Example:** Sam has the role "Auditor", which an admin added by hand in Process Manager. Their department changes from Finance to HR.

- **Managed:** Sam ends up with **HR** and **Auditor**. Finance goes, because the sync gave it; Auditor stays.
- **Preserve:** Sam ends up with **Finance**, **HR** and **Auditor**. Nothing is ever taken away.
- **Replace:** Sam ends up with **HR** only.

How Managed knows what it gave out: it records the roles it gives each person. With a mapping file or Enterprise App roles, it also treats every role named there as its own. The first time the sync touches someone, it can't know which of their existing roles came from an older setup, so it keeps them.

Replace mode never leaves someone with no roles. If Entra ID gives them none, they're left as they are.

---

## Role filter

*Optional, works with any mode.*

The role filter only hands out roles that **already exist** in Process Manager, so Entra ID can never create new roles. It's a safety net for Dynamic mode with Groups, where an unexpected group would otherwise become a new role.

It needs a Process Manager service account (a normal user account without multi-factor sign-in) so the sync can read your list of roles. Turn it on with the `filterToExistingRoles` setting.

## Existing users

By default the sync only updates people whose department, groups or app role assignments **change** after you install it. To bring everyone into line on day one, set **Sync existing users on first run** to `true` when you install.
