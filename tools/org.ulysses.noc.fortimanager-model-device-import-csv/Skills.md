# FortiManager Model Device Import CSV — Skills

## How to Call

Use this tool when:
- SE has an FMG-format CSV of model devices ready to bulk-provision (from your generator app's "Export FMG CSV" button)
- Onboarding a fleet of branches to a customer ADOM in one operation
- Automating the last-mile of a tenant deployment after templates + blueprints are in place

**Example prompts:**
- "Import all sites from `branches.csv` into ADOM `BOR_Customer_1`"
- "Dry-run this CSV to see the payload FMG will receive"
- "Bulk-onboard the 42 spokes in `customer_101_deploy.csv`"

## How this works

Mirrors the FMG GUI's "Add Model Devices from CSV" flow:
1. Reads the CSV file locally
2. Parses `Serial Number`, `Device Blueprint`, `Name` (required cols)
3. Any extra columns become per-device metadata variables
4. Builds ONE bulk `add-dev-list` payload with all rows
5. Fires `exec /dvm/cmd/add/dev-list`
6. Polls the returned task to completion
7. Verifies each row landed in DVM

**No multipart file upload** — the GUI parses the CSV client-side and calls the API. This tool does the same server-side.

## CSV format (per FMG 7.6/8.0 doc)

Required columns:
- `Serial Number` — real FortiFlex serial (VM) or synthetic HW serial
- `Device Blueprint` — name of a NAMED blueprint created via `device-blueprint-create`
- `Name` — device name (also becomes the mkey in DVM)

Optional metadata columns:
- Any additional column name is treated as a per-device metadata variable. Value goes into `meta variables[column_name] = value` for that row.
- Blank values are skipped (variable not set).

Optional HA columns (Phase 2, not yet wired): `Cluster Id`, `Cluster Name`, `Priority`, `HA Mode`.

### Minimal CSV
```csv
Serial Number,Device Blueprint,Name
FGT50GTK99000001,BOR-SINGLE-STD-50G,spoke-01
FGT50GTK99000002,BOR-SINGLE-STD-50G,spoke-02
```

### With metadata columns (typical Branch OnRamp deployment)
```csv
Serial Number,Device Blueprint,Name,SITE_ID,WAN_MODE,WAN_IP,WAN_MASK,WAN_GATEWAY,LAN_IP,LAN_MASK,ROUTER_ID
FGT50GTK99000001,BOR-SINGLE-STD-50G,spoke-01,1,static,203.0.113.10,255.255.255.0,203.0.113.1,10.1.0.1,255.255.255.0,10.30.1.100
FGT50GTK99000002,BOR-SINGLE-STD-50G,spoke-02,2,dhcp,,,,10.2.0.1,255.255.255.0,10.30.1.101
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | Yes | — | Target ADOM |
| `csv_path` | string | Yes | — | Absolute local path to CSV file |
| `default_platform` | string | No | — | Fallback platform if blueprint lookup fails |
| `default_os_type` | int | No | `0` | 0=fos |
| `default_os_ver` | int | No | `7` | Major FOS version |
| `default_mr` | int | No | `6` | Minor FOS version |
| `default_mgmt_mode` | int | No | `3` | 3=fmg |
| `default_adm_usr` | string | No | `admin` | |
| `default_adm_pass` | string | No | `""` | Blank = set later via device meta |
| `default_description` | string | No | `Model device (CSV import)` | |
| `resolve_blueprint_platform` | bool | No | `true` | Look up each blueprint's platform to fill `_platform` per row |
| `wait` | bool | No | `true` | Poll task to terminal state |
| `max_wait_sec` | int | No | `120` | |
| `dry_run` | bool | No | `false` | Return payload without POSTing |
| `auto_bind` | object | No | *(disabled)* | **v1.1.0** — opt-in post-import bindings. See below. |
| `set_hostname_from_name` | bool | No | `true` | **v1.2.0** — post-import update of each device's `hostname` field to match `name` (FMG's `add-dev-list` defaults `hostname=sn` until first install). |
| `pre_create_zone_shells` | bool | No | `true` | **v1.2.0** — before adding normalized-interface `dynamic_mapping`, create empty `system/zone/{zone}` shell on the device DB so FMG's `-10131 datasrc invalid` validation passes. CLI templates populate the zone at install time. |

### v1.1.0 `auto_bind` — post-import wiring

After the import succeeds (`action: imported`, at least one device created), the tool can attach the new devices to the tenant-scale infrastructure in one shot:

| Field | Type | Effect |
|---|---|---|
| `resolve_from_blueprint` | bool | If `true` and template_group/policy_package are omitted, infer them from the FIRST row's blueprint (`cliprofs[0]` + `pkg`). Zero manual config needed. |
| `template_group` | string | CLI Template Group name — appends new devices to its `scope member`. |
| `policy_package` | string | Policy Package name — appends new devices to its `scope member`. |
| `device_group` | string | DVMDB Device Group name — appends new devices to `object member`. ⚠ FMG 7.6.7 API accepts writes (code=0) but has no readback; verify in GUI. |
| `normalized_interfaces` | array | Normalized interface names to add `dynamic_mapping` for. String = same-name local-intf; `{name, local_intf}` = explicit mapping. |

**Scope-member semantics:** the tool does GET-extend-UPDATE (fetch existing → append new → dedup by `(name, vdom)` → write full list back). FMG's `update` REPLACES, so merging manually prevents wiping existing membership.

**Blueprint auto-magic caveat:** FMG blueprints with `port-provisioning: 1` ALREADY auto-bind new devices to their `cliprofs` + `pkg` scope members at device-creation time. The tool's template_group + policy_package bind is idempotent and will report `"nothing to add"` in that case — safe, not an error.

**Deferred-not-failed for normalized interfaces:** Fresh model devices have no device-side zones yet (they're created by CLI templates at first install). FMG returns `-10131 datasrc invalid`. **v1.2.0 fixes this** by pre-creating empty zone shells device-side. **v1.2.1 adds `zone_type` per zone** so shells go into the right table:

| zone_type | Shell path | When |
|---|---|---|
| `system` *(default)* | `set /pm/config/device/{dev}/vdom/{vdom}/system/zone/{name}` | Plain L2/L3 zone (LAN_ZONE, DMZ_ZONE, ...) — created by a CLI template with `config system zone` |
| `sdwan` | `set /pm/config/device/{dev}/vdom/{vdom}/system/sdwan/zone/{name}` | SDWAN zone (SDWAN_ZONE, Underlay_ZONE, ...) — created by the SDWAN template. **Required** when the zone name would otherwise collide with an SDWAN zone (`-553 name conflicts with a sdwan zone`) |
| `none` | *(skip)* | Rely on prior install having created the zone (dynamic_mapping ADD may fail with -10131 on fresh devices) |

### 🚨 Install-blocker context (v1.2.0)

**First spoke-2 install failed with:**
```
Copy device global objects
validation error on firewall policy 1..3 in policy package "BOR-SINGLE-STD-PKG", by dynamic interface check
validation error on firewall shaping-policy 1 in policy package "BOR-SINGLE-STD-PKG", by dynamic interface check
Vdom copy failed:
error 42 - entry not exist. detail: Dynamic interface "Underlay_ZONE" mapping undefined for device spoke-2
```

Root cause: dynamic_mapping was `deferred` (v1.1.0 behavior) → install-time validation had no per-device mapping → the entire Policy Package copy phase aborted. Even though CLI templates would eventually create the zones at install, the pkg validation runs *first* and blocks before any template gets a chance to run.

**v1.2.0 flow (default ON):**
1. Import via CSV → device lands in DVMDB (`hostname=sn` temporarily)
2. `set_hostname_from_name` → update `hostname` to match `name` (fixes FMG display / policy header)
3. `pre_create_zone_shells` (per zone, per device) → `set /pm/config/device/{dev}/vdom/root/system/zone/{ZONE}` with `{name: ZONE}` (empty shell, idempotent)
4. `add /pm/config/adom/{adom}/obj/dynamic/interface/{ZONE}/dynamic_mapping` → now validates OK (code=0)
5. Install runs → BOR-04-ZONE-LAN CLI template populates the zone with real interface members

All 4 steps happen in ONE tool call. Install is unblocked.

## Interpreting Results

**Success (all rows imported):**
```json
{
  "success": true,
  "action": "imported",
  "adom": "BOR_Customer_1",
  "csv_path": "C:/temp/deploy.csv",
  "rows_parsed": 3,
  "task_id": 47,
  "task_state": "done",
  "devices_created": [
    {"name": "spoke-01", "sn": "FGT50GTK99000001", "blueprint": "BOR-SINGLE-STD-50G", "oid": 401, "in_dvm": true},
    {"name": "spoke-02", "sn": "FGT50GTK99000002", "blueprint": "BOR-SINGLE-STD-50G", "oid": 402, "in_dvm": true},
    {"name": "hub-01",   "sn": "FGVMSLTM26000005", "blueprint": "BOR-SPA-SINGLE-STD-VM", "oid": 403, "in_dvm": true}
  ],
  "devices_failed": []
}
```

**Partial success:**
```json
{"success": false, "action": "partial", ..., "devices_created": [...], "devices_failed": [{...}]}
```

## Example

Minimal — CSV only, no auto-bind:
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-model-device-import-csv/1.1.0",
    parameters={
        "fmg_host": "184.73.7.106",
        "adom": "BOR_Customer_1",
        "csv_path": "C:/Users/howar/Downloads/customer_101_deploy.csv",
        "wait": True,
        "max_wait_sec": 180
    }
)
```

Full auto-bind — CSV + attach to all tenant-scale infrastructure in one shot:
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-model-device-import-csv/1.2.1",
    parameters={
        "fmg_host": "184.73.7.106",
        "adom": "BOR_Customer_1",
        "csv_path": "C:/Users/howar/Downloads/spoke-N.fmg.csv",
        "auto_bind": {
            "resolve_from_blueprint": True,   # -> BOR-SINGLE-STD + BOR-SINGLE-STD-PKG
            "device_group": "BOR_Branch_Single",
            # v1.2.1: per-zone zone_type prevents -553 install collisions
            "normalized_interfaces": [
                {"name": "LAN_ZONE",      "zone_type": "system"},   # BOR-04-ZONE-LAN creates as system zone
                {"name": "SDWAN_ZONE",    "zone_type": "sdwan"},    # BOR-09/SDWAN template creates as sdwan zone
                {"name": "Underlay_ZONE", "zone_type": "sdwan"},    # same
            ],
        },
    }
)
```

Live-tested 2026-08-25 on `BOR_Customer_1` importing spoke-2 (SN FGVMMLTM26012046). Result:
- `template_group` + `policy_package`: FMG auto-added at import time (blueprint's `port-provisioning: 1`); tool dedupe reported `"nothing to add"`.
- `device_group`: code=0 (verify in GUI).
- `normalized_interfaces` (v1.1.0): all 3 returned `status: deferred, code: -10131` — install then failed with "Dynamic interface 'Underlay_ZONE' mapping undefined for device spoke-2".
- **v1.2.0 fix:** pre-create zone shells → dynamic_mapping validated OK. But install then failed with `-553 name conflicts with a sdwan zone` on SDWAN_ZONE + Underlay_ZONE — my `system zone` shells collided with the SDWAN template's `sdwan zone` of the same name.
- **v1.2.1 fix (verified install-passing):** per-zone `zone_type` — `system` for LAN_ZONE, `sdwan` for SDWAN_ZONE + Underlay_ZONE. Also `set_hostname_from_name=true` default fixes hostname=SN display quirk.

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `CSV not found: <path>` | File missing | Verify absolute path |
| `CSV missing required columns: [...]` | Required headers absent | Add Serial Number / Device Blueprint / Name columns |
| `Row N: missing required value` | Blank required cell | Fill Serial/Blueprint/Name for that row |
| `FMG exec error: {'code': -22, ...}` | Duplicate device (SN or name already in DVM) | Change SN/name or delete existing device |
| `FMG exec error: {'code': -20084, ...}` | VM SN not FortiFlex-validated | Use a real FortiFlex-issued VM serial |
| `FMG exec error: {'code': -3, ...}` | ADOM or blueprint doesn't exist | Verify ADOM + blueprint names |
| `partial` action with `task_state: warning` | Some rows failed FMG-side | Inspect `devices_failed[]` + FMG task log |

## Pairs With

- `device-blueprint-create` — MUST create blueprints referenced by CSV Device Blueprint column FIRST
- `metadata-create` / `metadata-set-adom` — metadata columns in the CSV only take effect if the vars EXIST in the ADOM
- `model-device-create v2` — the alternative (single-device API create with inline blueprint)
- `object-list` — verify results at `/dvmdb/adom/{adom}/device`
- `task-status` — manually poll a task the tool didn't wait on
