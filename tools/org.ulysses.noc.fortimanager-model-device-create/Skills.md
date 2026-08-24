# FortiManager Model Device Create — Skills

## How to Call

Use this tool when:
- Staging a FortiGate in FMG **before the physical device arrives** (MSSP pre-build / ZTP flow)
- Creating a model device that will bind to templates + policy package on creation, then install automatically when the real device phones home via FGFM
- Zero-touch-like workflow from FMG alone (no FortiZTP dependency)
- Bulk pre-provisioning tenant fleets with per-device metadata variables baked in

**Example prompts:**
- "Create a model device for site 5 — platform FortiGate-50G, serial FGT50GTK26048289"
- "Pre-stage a FortiGate-120G spoke for customer BOR_Customer_1 with the SDWAN template attached"
- "Stage 10 FortiGate-30G branch devices with the same CLI template group and metadata var overrides per site"

## What's new in v2.0.0

- **Correct endpoint:** `/dvm/cmd/add/device` (7.6.7 daemon API — singular). v1 used the older `/dvm/cmd/add/dev-list`.
- **Inline device blueprint:** attach CLI template groups, policy package, auth template, and enforce-config setting in **one API call** via the nested `blueprint` object.
- **Enum flexibility:** `os_type` / `os_ver` / `mgmt_mode` accept friendly strings (`"fos"`, `"7.0"`, `"fmg"`) or integers — auto-mapped to what the wire wants.
- **Per-device metadata variables:** `meta_variables` param pre-populates `$(VAR)` overrides at create time.
- **Dry-run:** returns the exact payload that would be POSTed for inspection.

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | Yes | — | ADOM to register device in |
| `name` | string | Yes | — | Device name (mkey for later ops) |
| `sn` | string | Yes | — | Serial number. HW: real or synthetic. VM: real FortiFlex-issued |
| `platform` | string | Yes | — | `FortiGate-30G` / `FortiGate-50G` / `FortiGate-120G` / `FortiGate-VM64-KVM` etc. |
| `os_type` | string/int | No | `fos` | `fos`/`fsw`/`foc`/`fml`... or int (0=fos). Auto-mapped |
| `os_ver` | string/int | No | `7` | `"7.0"` or `7`. Auto-mapped |
| `mr` | int | No | `6` | Minor version (6 for 7.6.x) |
| `patch` | int | No | `0` | Patch level |
| `mgmt_mode` | string/int | No | `fmg` | `unreg`/`fmg`/`faz`/`fmgfaz` or int (3=fmg). Auto-mapped |
| `adm_usr` | string | No | `admin` | Admin user FMG uses over FGFM |
| `adm_pass` | string | No | — | Admin password (usually set at real-device promotion) |
| `description` | string | No | `""` | Free-form |
| `blueprint` | string OR object | No | — | Legacy: devprof name. New: full inline blueprint dict (see below) |
| `templates` | array[string] | No | — | Shortcut: CLI template groups to attach in blueprint |
| `pkg` | string | No | — | Shortcut: policy package name |
| `auth_template` | string | No | — | Shortcut: fabric auth template name |
| `enforce_device_config` | int | No | `0` | 0 = advisory, 1 = enforced from templates |
| `sdwan_management` | int | No | `0` | 0 = off, 1 = FMG owns SDWAN |
| `meta_variables` | object | No | — | `{VAR_NAME: value}` per-device overrides |
| `meta_fields` | object | No | — | Device-info tags (Address, Company, Contact, etc.) |
| `groups` | array[string] | No | — | Device group names to add device into |
| `faz_perm` | int | No | `15` | FortiAnalyzer permission bitmask |
| `faz_quota` | int | No | `0` | FAZ log quota MB (0 = unlimited) |
| `wait` | bool | No | `true` | Poll task until terminal |
| `max_wait_sec` | int | No | `60` | |
| `dry_run` | bool | No | `false` | Return payload without POSTing |

### Full inline blueprint fields (when `blueprint` is a dict)

```yaml
blueprint:
  platform: FortiGate-50G       # required if not passed at top level
  port-provisioning: 1          # 0/1 — enable port provisioning template
  vm-log-disk: 0                # VM only — log disk size
  linked-to-model: false
  prefer-img-ver: null          # FOS version to prefer at install
  download_from_fgd: false      # pull firmware from FortiGuard
  enforce-device-config: 0      # 0=advisory 1=enforced
  sdwan-management: 0
  folder: "/"                   # FMG folder path
  auth-template: null           # fabric authorization template name
  prerun-cliprof: null          # pre-run CLI profile name
  pkg: null                     # policy package name
  cluster-worker: []            # HA cluster worker device names
  templates: []                 # CLI template group names to attach
```

## Interpreting Results

**Created:**
```json
{
  "success": true,
  "action": "created",
  "name": "sdk-bor-50g-test-01",
  "adom": "BOR_Customer_1",
  "task_id": 15,
  "state": "done",
  "device_oid": 358,
  "platform_str_effective": "FortiGate-50G"
}
```

**Already exists** (idempotency-safe):
```json
{
  "success": false,
  "action": "already-exists",
  "name": "sdk-bor-50g-test-01",
  "adom": "BOR_Customer_1",
  "device_oid": 358,
  "error": "Device 'sdk-bor-50g-test-01' already exists in ADOM 'BOR_Customer_1' (oid=358, sn=FGT50GTK26048289)"
}
```

**Dry-run:**
```json
{
  "success": true,
  "action": "dry-run",
  "name": "...",
  "adom": "...",
  "payload_sent": {
    "url": "/dvm/cmd/add/device",
    "method": "exec",
    "data": { "adom": "...", "flags": [...], "device": { ... } }
  }
}
```

## Example — full MSSP branch onboarding workflow

```python
# 1. Ensure metadata vars exist (referenced by CLI templates via $(VAR))
metadata_create({"fmg_host": "184.73.7.106", "adom": "BOR_Customer_1",
                 "name": "SITE_ID", "value": ""})
metadata_create({"fmg_host": "184.73.7.106", "adom": "BOR_Customer_1",
                 "name": "LAN_SUBNET", "value": "10.0.0.0/24"})

# 2. Author CLI templates (System, Interface, BGP, IPsec, SDWAN) — see cli-template-create

# 3. Bundle CLI templates in order — see cli-template-group-create

# 4. Create model device with template group + policy pkg attached inline
model_device_create({
    "fmg_host": "184.73.7.106",
    "adom": "BOR_Customer_1",
    "name": "spoke-05",
    "sn": "FGT50GTK26048289",
    "platform": "FortiGate-50G",
    "templates": ["BOR-CLI-Group-Standard"],
    "pkg": "BOR-Policy-Default",
    "enforce_device_config": 1,
    "meta_variables": {
        "SITE_ID": "5",
        "LAN_SUBNET": "10.5.0.0/24",
        "LOOPBACK_IP": "172.16.0.5"
    },
    "description": "Model for site 5, dark shipping to branch"
})

# 5. When the physical FGT-50G at the site boots and dials FGFM, FMG matches
#    by serial, promotes the model to a real device, and installs the templated
#    config in one shot.
```

## Known FMG 7.6 behaviours worth knowing

1. **Endpoint is singular** — `/dvm/cmd/add/device`, NOT `/dvm/cmd/add/dev-list` (the older API). Fixed in v2.
2. **Serial determines platform for HW** — pass any valid HW serial (`FGT50GTK...`) and FMG derives `platform_str` automatically. For **VMs**, `platform_str` and a real FortiFlex-issued serial are BOTH required or you get `code -20084`.
3. **`flags: 262176`** is the observed GUI default — it enables `is_model` + `linked_to_model` + FGFM path bits. Passed by the tool automatically.
4. **`device blueprint` is now a rich nested object** (not just a name reference). This is where you attach templates / pkg / auth template / policy behaviour in one call.
5. **CLI Template Group scope-member does NOT bind here** — the `templates: [...]` array inside blueprint stores a reference on the device blueprint but does NOT populate the template group's `scope member` field. If you want the group to know it owns the device, use `template-bind-to-device` (which currently has its own bug for CLI groups — being addressed). For install-time behaviour, the blueprint reference is what FMG uses.
6. **Delete uses a different endpoint** — `exec /dvm/cmd/del/device` (not `delete /dvmdb/...`). Generic `object-delete` returns `code -9` on DVM devices.
7. **Meta variables** — the `meta_variables` param populates `$(VAR)` overrides, but only for vars that ALREADY EXIST in the ADOM. Create them first via `metadata-create`.

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG exec error: {'code': -20084, ...}` | VM serial not validated against FortiFlex | Use a real FortiFlex-issued VM serial OR switch to HW platform with synthetic SN |
| `FMG exec error: {'code': -3, ...}` | ADOM doesn't exist | Create the ADOM first (via `object-create` on `/dvmdb/adom`) |
| `FMG exec error: {'code': -22, ...}` | Object already exists | Check with `object-list` on `/dvmdb/adom/{adom}/device` — tool also does an existence pre-check |
| `already-exists` (action) | Device with this name already in DVM | Delete first via `exec /dvm/cmd/del/device` or pick a new name |
| `Task ended error / warning` (with detail) | FMG task fired but reported an error | Inspect FMG task log for the specific step that failed |
| `Device not in DVM after create` | Task completed but device didn't populate | Check FMG task history + admin permission on ADOM |

## Pairs With

- `metadata-create` — MUST run first if templates reference `$(VAR)` names
- `cli-template-create`, `cli-template-group-create`, `sdwan-template-create`, `system-template-create` — build templates before attaching
- `template-bind-to-device` — optional post-create binding (has a known limitation for CLI groups — see caveat #5 above)
- `metadata-set-device` — set per-device variable overrides after create (alternative to `meta_variables` param)
- `device-settings-install` — push templated config to the model device
- `policy-package-install` — push policy package to model device
- `task-status` — manually poll a task the tool didn't wait on
- `object-list` — verify device via `/dvmdb/adom/{adom}/device`
