# FortiManager Device Blueprint Create — Skills

## How to Call

Use this tool when:
- Building **named, reusable** Device Blueprints that a CSV model-device import references
- Setting up per (role × platform × feature-combo) blueprints for MSSP ZTP fleet deployment
- Bundling System / IPsec / BGP / Static / SDWAN provisioning templates + policy pkg + auth + HA settings into one anchor object

**Example prompts:**
- "Create a blueprint 'BOR-SINGLE-STD-50G' for FortiGate-50G with the System + IPsec + BGP + Static + SDWAN templates attached"
- "Add a blueprint for VM SPA hub with the BOR-SPA template group and BOR-SPA-PKG policy package"
- "Dry-run a blueprint payload so I can inspect before pushing"

## What this tool creates

**Named Device Blueprints** at `/pm/config/adom/{adom}/obj/fmg/device/blueprint`. These are the objects the FMG CSV import references in the `Device Blueprint` column. They differ from the **inline** blueprint used by `model-device-create v2` — that one is embedded in the device creation call, this one is a REUSABLE object.

## Automatic template-ref prefixing

FMG's blueprint schema requires provisioning templates in `templates[]` to be prefixed with a numeric family+stype ID:

| Template family | Prefix example | stype |
|---|---|---|
| System Template (devprof) | `1__sdk-sys-tpl-test` | (no stype — devprof namespace) |
| IPsec Tunnel Template | `4-1__sdk-bor-ipsec-tpl-v1` | `_ipsec` |
| Static Route Template | `4-2__sdk-bor-static-route-tpl-v1` | `_router_static` |
| BGP Template | `4-1240__sdk-bor-bgp-tpl-v1` | `router_bgp` |
| SDWAN Template (wanprof) | `5__sdk-sdwan-tpl-test` | (no stype — wanprof namespace) |

**You pass friendly names, tool auto-prefixes** by looking up each name in devprof + wanprof + `/pm/template/adom/{adom}` catalog. Advanced usage: pass pre-prefixed strings directly (e.g. `"4-1__my-tpl"`) and tool passes them through.

**CLI Templates go in `cliprofs`** (separate list, no prefix needed). **`prerun-cliprof`** for CLI templates that run BEFORE others (e.g. green-field cleanup).

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | Yes | — | Target ADOM |
| `name` | string | Yes | — | Blueprint name (mkey) |
| `platform` | string | Yes | — | e.g. `FortiGate-50G`, `FortiGate-VM64-KVM` |
| `description` | string | No | `""` | Free text |
| `pkg` | string | No | — | Policy package name |
| `folder` | string | No | — | FMG folder path |
| `templates` | array | No | — | Provisioning template names (friendly, auto-prefixed) — mutex with `template_group` |
| `template_group` | string | No | — | CLI Template Group name — mutex with `templates` |
| `cliprofs` | array | No | — | CLI Template names (separate list) |
| `prerun_cliprof` | array | No | — | CLI Templates run before others |
| `auth_template` | array | No | — | Fabric auth template names |
| `enforce_device_config` | bool | No | `false` | true = enforce config; false = advisory |
| `sdwan_management` | bool | No | `false` | true = FMG owns SDWAN |
| `vm_log_disk` | bool | No | `false` | VM only |
| `port_provisioning` | int | No | `1` | 0/1 — enable port provisioning |
| `prefer_img_ver` | string | No | — | Preferred FortiOS at install |
| `dev_group` | array | No | — | Device group refs |
| `ha_config` | bool | No | `false` | Enable HA |
| `ha_password` | string | No | — | HA password |
| `linked_to_model` | bool | No | `false` | HA-slave linkage |
| `cluster_worker` | array | No | — | HA cluster workers |
| `overwrite` | bool | No | `false` | Update if exists |
| `dry_run` | bool | No | `false` | Return payload without POSTing |

## Interpreting Results

**Created:**
```json
{
  "success": true,
  "action": "created",
  "name": "sdk-blueprint-50g-test",
  "adom": "BOR_Customer_1",
  "platform": "FortiGate-50G",
  "prov_type": "templates",
  "templates_resolved": [
    "1__sdk-sys-tpl-test",
    "4-1__sdk-bor-ipsec-tpl-v1",
    "5__sdk-sdwan-tpl-test",
    "4-2__sdk-bor-static-route-tpl-v1",
    "4-1240__sdk-bor-bgp-tpl-v1"
  ],
  "endpoint_used": "/pm/config/adom/BOR_Customer_1/obj/fmg/device/blueprint"
}
```

## Example

Build the same blueprint the FMG GUI creates when SE clicks "Create New" → picks FortiGate-50G → attaches 5 provisioning templates + 1 CLI template:

```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-device-blueprint-create/1.0.0",
    parameters={
        "fmg_host": "184.73.7.106",
        "adom": "BOR_Customer_1",
        "name": "BOR-SINGLE-STD-50G",
        "platform": "FortiGate-50G",
        "description": "Branch On-Ramp single-circuit std combo for FGT-50G",
        "templates": [
            "BOR-SYSTEM",           # System Template — auto-prefixed 1__
            "BOR-IPSEC",            # IPsec Template — auto-prefixed 4-1__
            "BOR-BGP",              # BGP Template — auto-prefixed 4-1240__
            "BOR-STATIC",           # Static Route Template — auto-prefixed 4-2__
            "BOR-SDWAN",            # SDWAN Template — auto-prefixed 5__
        ],
        "cliprofs": ["BOR-LAN-INTF"],    # CLI template — no prefix
        "pkg": "BOR-SINGLE-STD-PKG",
        "port_provisioning": 1,
        "enforce_device_config": False,   # Phase 1 = advisory
        "overwrite": True,
    }
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `Template 'X' not found in devprof, wanprof, or /pm/template catalog on ADOM 'Y'` | Template name not resolvable | Create the template first (via system-template-create / cli-template-create / provisioning-template-create / sdwan-template-create) |
| `Template 'X' has stype 'Y' — no numeric prefix mapping known` | New stype discovered | Pass pre-prefixed ref (`N__X`) or update tool's `_STYPE_TO_PREFIX` map |
| `Pass either 'templates' OR 'template_group', not both` | Mutex conflict | Choose one — `prov-type` derives from which is used |
| `Blueprint 'X' already exists in ADOM 'Y'` | Idempotent — collision | Set `overwrite: true` |
| `FMG {'code': -3, ...}` | ADOM not found | Verify ADOM |

## Pairs With

- `system-template-create`, `cli-template-create`, `cli-template-group-create`, `sdwan-template-create`, `provisioning-template-create` — templates must exist BEFORE blueprint references them
- `metadata-create` / `metadata-set-adom` — meta vars declared before templates reference `$(VAR)` or `{{ VAR }}`
- **CSV model-device import** — blueprints created here are what CSV rows reference in `Device Blueprint` column
- `model-device-create v2` — the alternative (uses inline blueprint dict; simpler for one-off API creation vs bulk CSV)
