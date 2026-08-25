# FortiManager Template Clone From Device — Skills

## How to Call

Use this tool when:
- You've provisioned a device via CLI Templates + Jinja `$(VAR)` refs, and now want the resolved config as human-editable per-family templates for long-term MAC (Move/Add/Change/Delete)
- Onboarding a "golden" reference device whose config becomes the ADOM's authoritative BGP/IPsec/Static Route templates
- Migrating from CLI-template-only architecture to dedicated-templates architecture without hand-rebuilding

**Example prompts:**
- "Clone spoke-1's BGP + Static + IPsec into human-facing templates for BOR_Customer_1"
- "Take the golden config from spoke-1 and drop it into IPsec/BGP/Static templates named BOR-*-SINGLE"
- "Dry-run: what URLs would the clone hit?"

## The workflow this completes

```
1. CSV import (per-tenant SE fills)   ─→  Model device in DVMDB
                                          + Meta vars per-device
2. Blueprint install (prerun → cliprofs → pkg)
                                      ─→  Device receives fully-resolved config (DVMDB)
3. THIS TOOL — clone from DVMDB       ─→  Named ADOM templates
                                          (BGP / IPsec / Static / etc.)
4. Long-term: SEs edit human templates in FMG GUI wizards for MAC ops
```

CLI templates stay as the initial-provision authority (Jinja + $(VAR) power); the human-facing templates become the ongoing-management surface.

## Confirmed presets (FMG 7.6.7)

| Preset | Mechanism | Source | Target |
|---|---|---|---|
| `bgp` | clone | `pm/config/device/{dev}/vdom/{vdom}/router/bgp` | `pm/template/router_bgp/adom/{adom}/{name}` |
| `static-route` (alias `static`) | clone | `pm/config/device/{dev}/vdom/{vdom}/router/static` | `pm/template/_router_static/adom/{adom}/{name}` |
| `ipsec-phase1` (alias `ipsec`) | clone | `pm/config/device/{dev}/vdom/{vdom}/vpn/ipsec/phase1-interface` | `pm/template/_ipsec/adom/{adom}/{name}` |
| `ipsec-phase2` | clone | `pm/config/device/{dev}/vdom/{vdom}/vpn/ipsec/phase2-interface` | `pm/template/_ipsec/adom/{adom}/{name}` |
| `sdwan` | exec `/_wanprof/import` | device's `system/sdwan` (implicit) | `pm/wanprof/adom/{adom}/{name}` |
| `system` (alias `devprof`) | exec `/_devprof/import` | device's system/dns/ntp/admin/snmp/log/etc. (implicit) | `pm/devprof/adom/{adom}/{name}` |

### SDWAN preset specifics

SDWAN does NOT use the JSON-RPC `clone` method — it uses a dedicated import endpoint:

```
exec /pm/config/adom/{adom}/_wanprof/import
data: {
  "template": "<target_wanprof_name>",   # MUST already exist
  "device":   {"name": "<dev>", "vdom": "<vdom>"},
  "description": "..."
}
```

The wanprof shell (`target_name`) must already exist in the ADOM — create it with `sdwan-template-create` first. The import MERGES the device's runtime SDWAN config (zones, members, health-checks, service rules, BGP neighbors) INTO the target wanprof. This matches FMG's GUI "Import SDWAN From Device" flow.

Endpoint discovered via FMG GUI curl capture (thanks Daniel).

### System / devprof preset specifics

System templates (aka `devprof` in FMG's data model) use a THIRD mechanism — similar shape to SDWAN but different payload:

```
exec /pm/config/adom/{adom}/_devprof/import
data: {
  "device":      "<dev_name>",           # PLAIN STRING here (not {name,vdom} dict!)
  "devprof":     "<target_devprof_name>",
  "description": "..."
}
```

Captures the device's `enabled options` subsystems in one call:
`dns / ntp / email / admin / snmp / repmsg / ftgd / log / interface / router / combined`

Verify content lands at `/pm/config/adom/{adom}/devprof/{name}/system/{section}` (device-shape path, NOT `/pm/devprof/...` — that shape only returns the top-level).

Endpoint discovered via FMG GUI curl capture 2026-08-25.

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | Yes | — | Target ADOM (where new templates land) |
| `device` | string | Yes | — | Source device in DVMDB |
| `vdom` | string | No | `root` | Source vdom on the device |
| `clones` | array | Yes | — | List of clone entries (see below) |
| `overwrite` | bool | No | `false` | If target template exists, delete first then clone |
| `stop_on_error` | bool | No | `false` | Halt on first failure vs. continue with remaining |

**Each clone entry:**
| Field | Required | Notes |
|---|---|---|
| `preset` | one of | Friendly shortcut — see preset table above |
| `source_path` | one of | Custom source under `.../vdom/{vdom}/` (e.g. `router/bgp`) |
| `stype` | with source_path | Target stype (e.g. `router_bgp`) |
| `target_name` | Yes | Name of the resulting human-facing template |

## Example

```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-template-clone-from-device/1.2.0",
    parameters={
        "fmg_host": "184.73.7.106",
        "adom": "BOR_Customer_1",
        "device": "spoke-1",
        "vdom": "root",
        "clones": [
            {"preset": "bgp",          "target_name": "BOR-BGP-SINGLE"},
            {"preset": "static-route", "target_name": "BOR-STATIC-SINGLE"},
            {"preset": "ipsec-phase1", "target_name": "BOR-IPSEC-P1-SINGLE"},
            {"preset": "ipsec-phase2", "target_name": "BOR-IPSEC-P2-SINGLE"},
            {"preset": "sdwan",        "target_name": "BOR-SDWAN-SINGLE"},
            {"preset": "system",       "target_name": "BOR-SYSTEM-SINGLE"},
        ],
        "overwrite": True,
    }
)
```

## Interpreting Results

**Fully successful clone (all entries landed):**
```json
{
  "success": true,
  "action": "cloned",
  "adom": "BOR_Customer_1",
  "device": "spoke-1",
  "results": [
    {"preset": "bgp",          "status": "cloned", "code": 0, "oid": 6793, "source_url": "pm/config/device/spoke-1/vdom/root/router/bgp", "target_url": "pm/config/adom/BOR_Customer_1/template/router_bgp/BOR-BGP-SINGLE"},
    {"preset": "static-route", "status": "cloned", "code": 0, "oid": 6810, ...},
    {"preset": "ipsec-phase1", "status": "cloned", "code": 0, "oid": 6824, ...},
    {"preset": "ipsec-phase2", "status": "cloned", "code": -10000, "oid": 6834, "message": "invalid value"}
  ]
}
```

Note: **IPsec Phase 2 clone can return non-zero `code` (e.g. -10000) but the template DOES land.** The tool verifies via post-clone GET and marks status "cloned" if the target exists regardless of the response code. This mirrors observed FMG behavior.

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `Unknown preset 'X'` | Preset name typo | Use one of: bgp, static-route, ipsec-phase1, ipsec-phase2, sdwan, system |
| `sdwan` preset: `-6 unknown template` | Target wanprof shell doesn't exist | Create with `sdwan-template-create` first (empty shell is fine) |
| `system` preset: `-6 unknown devprof` | Target devprof shell doesn't exist | Create with `system-template-create` first (empty shell is fine) |
| `Either preset OR both source_path+stype must be provided` | Custom clone missing fields | Provide both source_path and stype, or use a preset |
| `FMG HTTP 503` | Server temporarily busy | Retry after brief pause (2-3s); tool doesn't auto-retry today |
| `code=-1 invalid value` on target | Target URL shape wrong for this stype | Verify stype matches an /pm/template/ family (not /pm/wanprof or /pm/devprof) |
| `code=-2 Object already exists` | Target template already there | Use `overwrite: true` |
| `status: "failed"` in results with `landed: false` | Clone POST returned OK but nothing landed at target | Check FMG task log for the specific stype's install-validation errors |

## Pairs With

- `metadata-create` / `metadata-set-adom` — declare vars BEFORE authoring source CLI templates
- `cli-template-create` — the CLI templates whose install output gets cloned
- `device-blueprint-create` — bundles the CLI templates + pkg for install
- `model-device-import-csv` — imports devices from CSV; devices then get installed, THEN cloned via this tool
- `provisioning-template-create` — creates empty template shells (this tool populates them from a device)
