# FortiManager Device Group Create — Skills

## How to Call

Use this tool when:
- Onboarding a new tenant ADOM and setting up the standard org buckets (`BOR_Branch_Single`, `BOR_Branch_Dual`, `HQ`, `DataCenter`, etc.)
- Adding a freshly-imported device to an existing group
- Reorganizing membership (pass a new `members` list; existing members get replaced)

**Example prompts:**
- "Create the BOR_Branch_Single group in BOR_Customer_1 with spoke-1 as a member"
- "Set up empty Single/Dual groups for BOR_Customer_2"
- "Add spoke-5 and spoke-6 to BOR_Branch_Dual"

## What this unlocks at scale

Groups are the natural pivot for MSSP-scale ops. Once a device is in the right group, every downstream operation can target the group instead of individual devices:

```
                    ┌── BOR_Branch_Single ──┐   ┌── BOR_Branch_Dual ──┐
                    │ • spoke-1 root         │   │ • spoke-42 root      │
                    │ • spoke-3 root         │   │ • spoke-56 root      │
BOR_Customer_1 ADOM │ • spoke-7 root         │   │ • ...                │
                    └────────────────────────┘   └──────────────────────┘
                         │                             │
                         ├── scope member for          ├── scope member for
                         │   BOR-SINGLE-STD (CLI grp)  │   BOR-DUAL-STD (CLI grp)
                         │                             │
                         ├── scope for BOR-SINGLE-STD- ├── scope for BOR-DUAL-STD-
                         │   PKG (Policy Package)      │   PKG (Policy Package)
                         │                             │
                         └── bulk install target       └── bulk install target
```

Before groups existed, we bound `scope member` device-by-device — every new spoke needed a manual scope update on the CLI template group + Policy Package. With groups, the scope binds to `{grp: "BOR_Branch_Single"}` once and every future addition to the group is auto-scoped.

## Endpoints hit (per FMG 7.6 GUI curl)

| Op | Method | URL | Data shape |
|---|---|---|---|
| Create | `add` | `/dvmdb/adom/{adom}/group/{name}` | `{name, desc, type: "normal", meta fields: {}, os_type: "fos"}` |
| Update top-level | `update` | `/dvmdb/adom/{adom}/group/{name}` | same as create |
| Set members | `set` | `/dvmdb/adom/{adom}/group/{name}/object member` | `[{name, vdom}, ...]` |
| Read members | `get` | `/dvmdb/adom/{adom}/group/{name}/object member` | — |

**Field-name gotchas (FMG 7.6 requires these EXACT names):**
- `desc` — NOT `description`
- `meta fields` — space, NOT `meta-fields`
- `object member` — space, NOT `object-member` (child endpoint suffix, mirrors the CLI template group `scope member` quirk)
- `os_type` — underscore

### ⚠ Member persistence / readback quirk (FMG 7.6.7)

Writes on `object member` (`set` / `add` / `update`) all return `code=0 OK`, but the JSON-RPC API has **no read-back path** for group members. `GET` on the same child endpoint returns the PARENT group's metadata (not the member collection). The DEVICE side has no `grp` field either. Schema queries confirm `device_group.attr` has no `member` declared.

**FMG's own GUI reads membership through `/gui/adoms/{adom_oid}/groups/{grp_oid}?fields=memb` via `/cgi-bin/module/flatui_proxy` — that endpoint requires a session COOKIE (Bearer tokens are rejected as HTTP 400 "need session cookie").**

Practical impact for this tool:
- `member_count` in output = what we submitted (write returned OK)
- `members_verified` = `null` (API cannot re-read)
- `members_submitted` = the list you passed in, for your records
- `verify_hint` string points to the GUI location to eye-check

To confirm after running: **FMG GUI → Device Manager → {ADOM} → Device Group → {group name}**.

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | Target ADOM |
| `name` | string | Yes | — | Group name (unique within ADOM) |
| `desc` (alias `description`) | string | No | `""` | Free-text description |
| `type` | string | No | `normal` | `normal` or `default` |
| `os_type` | string | No | `fos` | Device family: `fos`, `fsw`, `fpx`, `foc`, `faz`, `fml`, `fdd`, `fac`, `fca` |
| `meta_fields` (alias `meta fields`) | object | No | `{}` | Group-scoped meta vars (rare) |
| `members` | array | No | omit | Devices to seed. Each entry: plain string OR `{name, vdom}` dict. If provided (even `[]`), REPLACES membership. If omitted entirely, membership is untouched. |
| `overwrite` | bool | No | `false` | If group exists: `true` → update, `false` → noop-error |

## Example

```python
# Set up the two standard BOR device groups in a tenant ADOM
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-device-group-create/1.0.0",
    parameters={
        "fmg_host": "184.73.7.106",
        "adom": "BOR_Customer_1",
        "name": "BOR_Branch_Single",
        "desc": "Single-BOR branches (one WAN + one SASE tunnel per site)",
        "members": [{"name": "spoke-1", "vdom": "root"}],
        "overwrite": True,
    }
)

execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-device-group-create/1.0.0",
    parameters={
        "fmg_host": "184.73.7.106",
        "adom": "BOR_Customer_1",
        "name": "BOR_Branch_Dual",
        "desc": "Dual-BOR branches (two WAN + two SASE tunnels per site)",
        "members": [],   # empty list = create empty group, ready for future DUAL sites
        "overwrite": True,
    }
)
```

## Interpreting Results

**Successful create with members:**
```json
{
  "success": true,
  "action": "created",
  "members_action": "set",
  "name": "BOR_Branch_Single",
  "adom": "BOR_Customer_1",
  "oid": 361,
  "os_type": 0,
  "type": 0,
  "member_count": 1,
  "members_submitted": [{"name": "spoke-1", "vdom": "root"}],
  "members_verified": null,
  "missing_devices": [],
  "verify_hint": "FMG GUI: Device Manager -> BOR_Customer_1 -> Device Group -> BOR_Branch_Single"
}
```

Note: `os_type`/`type` come back as integer enum values (FMG's internal rep — `os_type: 0` = fos, `type: 0` = normal). See schema in the module docstring for the full enum map.

**Successful create, empty group:**
```json
{
  "success": true,
  "action": "created",
  "members_action": "set",
  "member_count": 0,
  "members_submitted": [],
  "members_verified": null,
  ...
}
```

**Update existing (overwrite=true) preserving membership (omit `members` entirely):**
```json
{
  "success": true,
  "action": "updated",
  "members_action": null,     // untouched
  "member_count": 0,          // we sent nothing; existing membership unchanged in FMG
  "members_submitted": [],
  ...
}
```

**Exists but overwrite=false:**
```json
{
  "success": false,
  "action": "noop",
  "error": "Device group 'BOR_Branch_Single' already exists in ADOM 'BOR_Customer_1'. Set overwrite=true to update...",
  "missing_devices": []
}
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `Missing required parameter: name` | Group name wasn't passed | Pass `name` |
| `code=-10 The data is invalid for selected url` | Field name wrong (e.g. `description` vs `desc`, or `meta-fields` vs `meta fields`) | Tool sends the exact FMG-required names; check for custom payload overrides |
| `code=-3 Object does not exist` on member set | Member device name not found in DVMDB | Check `missing_devices` in result — either fix the name or create the model device first |
| `code=-6 Invalid url` | ADOM name or path typo | Verify ADOM exists via `get /dvmdb/adom` |
| `Device group already exists` | Duplicate name | Set `overwrite: true`, or pick a new name |

## Pairs With

- `model-device-create` / `model-device-import-csv` — creates the devices you'll add to the group
- `cli-template-group-create` — the CLI Template Group whose `scope member` should be the DEVICE group (bulk bind) instead of individual devices
- `metadata-set-group` (if we build it) — push meta var values to every device in a group at once
- `device-blueprint-create` — blueprints don't reference device groups directly, but the CLI template group + Policy Package attached to a blueprint pick up all devices in their scope groups at install

## When NOT to use

- **Dynamic groups** (filter-based membership): those use `/dvmdb/adom/{adom}/dynamic-group` (different endpoint). This tool creates STATIC normal groups only.
- **Cross-ADOM groups**: not supported in FMG. Create the group once per tenant ADOM.
