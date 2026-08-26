# FortiSASE Branch OnRamp (BOR) Deployment Workflow

**Audience**: Partner engineers deploying MSSP-scale FortiSASE BOR through FortiManager 7.6+, and AI assistants (Claude, etc.) picking up this repo cold.

**Purpose**: End-to-end reference for the MSSP deployment model: how a tenant ADOM is prepped once, then how each branch site (spoke or SPA hub) is provisioned in a single tool call.

**Companion generator**: The `.fmg.csv` files consumed by this workflow are produced by [`FortiSASE-SDK/automation/sdwan-ztp/config-generator/`](https://github.com/howardsinc3753/FortiSASE-SDK) (a schema-first Streamlit app). Configs and CSVs live under `fmg-export/hardware-blueprints/{30G,50G,120G,SPA-HUB/...}/`.

---

## 1. The Two-Phase Model

```
┌────────────────────────────────────────────────────────────────────┐
│  PHASE 1: ADOM PREP  (once per tenant, ~2-4 hours end-to-end)      │
│  Establish templates, blueprints, policy packages, groups          │
└────────────────────────────────────────────────────────────────────┘
                                 ↓
┌────────────────────────────────────────────────────────────────────┐
│  PHASE 2: PER-SITE PROVISION  (minutes per site, ONE tool call)    │
│  SE fills schema → generator produces CSV → tool imports device    │
└────────────────────────────────────────────────────────────────────┘
                                 ↓
┌────────────────────────────────────────────────────────────────────┐
│  Install Wizard (GUI or API) → device dial-home → config applied   │
└────────────────────────────────────────────────────────────────────┘
```

Phase 1 is repeated **once per tenant ADOM**. Phase 2 is repeated **N times, one per branch site**. The reusability of Phase 1 assets across N sites is the MSSP economy.

---

## 2. Phase 1 — ADOM Prep

Everything below lives inside a single ADOM (e.g. `BOR_Customer_1`). To onboard another customer, either clone the ADOM (see §6) or re-run these steps in a fresh ADOM.

### 2.1 Meta variables (SE-facing knobs)

The generator schema and CLI templates share a variable vocabulary. Declare at ADOM level with `metadata-create` or `metadata-set-adom`. Each variable has an ADOM default; per-site overrides get pushed as `dynamic_mapping` entries at import time.

Categories:
- **Tenant vars** (~30): BGP_AS, ADMIN_PASSWORD, SEED_PSK, BASTION_IP, POP1_/POP2_ FQDN/COMMUNITY/PROBE, ONRAMP_PROPOSAL/DHGRP, SLA thresholds, ADMIN_SPORT/TIMEOUT, TIMEZONE, BGP_KEEPALIVE/HOLDTIME, etc.
- **Site vars** (~17): HOSTNAME, SITE_ID, LAN_IP/MASK/SUBNET/PORT, WAN_MODE/IP/MASK/GATEWAY/PORT/DHCP_DIST, MGMT_GATEWAY, ROUTER_ID, DEVICE_ALIAS, SITE_BW_MBPS.

**Quirk**: metavar `dynamic_mapping._scope.vdom` is `"global"` (not `"root"`). The `add-dev-list` CSV import auto-handles this; direct API updates use `/pm/config/adom/{adom}/obj/fmg/variable/{VAR}/dynamic_mapping/{dev}/global` with `data: {value: "..."}`.

### 2.2 Normalized Interfaces

Three dynamic interfaces let ADOM-level policies reference platform-agnostic zones:

| Name | Purpose | Zone type on device |
|---|---|---|
| `LAN_ZONE` | Bound to device-local LAN port (via CLI template `config system zone`) | `system zone` |
| `SDWAN_ZONE` | Overlay tunnels (BOR_Primary + BOR_Secondary IPsec, and SPA hub tunnels) | `system sdwan zone` (created by SDWAN template) |
| `Underlay_ZONE` | Underlay WAN port(s) | `system sdwan zone` (created by SDWAN template) |

**platform_mapping**: Each normalized interface has `platform_mapping` entries for **45 platforms** (see `PLATFORMS` list in `scratchpad/add-platform-mappings.py`) — every common FortiGate VM/ARM/HW variant. This lets FMG resolve the normalized interface to a device-local zone name at install time WITHOUT needing per-device `dynamic_mapping` in the common case.

**dynamic_mapping (per-device)**: Belt-and-suspenders — added at import time by the CSV importer for each new device (see Phase 2). Required when the platform is not in platform_mapping or when the zone name must be pinned explicitly.

### 2.3 CLI Templates

Numbered `BOR-01..BOR-11` with a bump to `BOR-20+` for role-specific additions. Each template uses Jinja `{{ VAR }}` for meta var substitution and `{% if %}` for branching (e.g. `WAN_MODE == "static"` vs `dhcp`).

**Standard templates (used by all roles)**:
| Template | Purpose | Notes |
|---|---|---|
| `BOR-01-SYSTEM-GLOBAL` | hostname, alias, admin, timezone, fortiguard | includes `set accprofile "super_admin"` (FMG install-check requires) |
| `BOR-03-INTERFACES-VM` | port1 + port2 physical interfaces w/ MTU 9001 | VM-specific: `set vdom "root"` + `set type physical` REQUIRED |
| `BOR-03-INTERFACES-HW` | wan + lan1 physical interfaces, no MTU-override | HW-specific: omits vdom/type/mtu |
| `BOR-04-ZONE-LAN` | `config system zone LAN_ZONE / set interface {{ LAN_PORT }}` | Same for VM + HW |
| `BOR-05-IPSEC-P1-P2` | 2 IPsec tunnels to BOR PoPs | DDNS+SEED_PSK based |
| `BOR-07-STATIC-ROUTES` | 6 static routes (WAN default, PoP /32s, PoP FQDN via WAN, bastion) | Route 10 precedence: `WAN_MODE=dhcp → dynamic-gateway > MGMT_GATEWAY > WAN_GATEWAY` (fixed 2026-08-26) |
| `BOR-08-BGP` | prefix-list, 3 route-maps (PRIMARY/SECONDARY/FAIL), BGP neighbors | Community math: `65001:{1000+SITE_ID}` |
| `BOR-09-SDWAN-BASE` | SDWAN zones + members + health-checks + neighbors | Creates `SDWAN_ZONE` + `Underlay_ZONE` as `system sdwan zone` |
| `BOR-11-SDWAN-RULES` | 3 SDWAN services (Private_Access, INET_via_BOR, Underlay_fallback) | |

**Prerun templates** (per platform, run BEFORE main cliprofs at install):
| Template | Purpose | Used for |
|---|---|---|
| `BOR-02-GREENFIELD-VM` | Only `config firewall policy purge` | VM (nothing else exists by default) |
| `BOR-02-GREENFIELD-HW-SMALL` | + `dhcp server purge`, `virtual-switch purge`, `firewall address delete "lan"` | 30G, 50G HW (small class) |
| `BOR-02-GREENFIELD-120G` | + `dhcp server edit 1 → ip-range purge → delete 1`, `virtual-switch edit "lan" → port purge → delete "lan"` | 120G (deeper drill) |

**Rule**: DO NOT include `y` confirmation lines in template scripts — FMG auto-confirms interactive purge prompts.

### 2.4 CLI Template Groups

Container that bundles templates in emit order. Blueprint's `cliprofs` field references ONE group.

| Group | Members | Reused by |
|---|---|---|
| `BOR-SINGLE-STD` | BOR-01, BOR-03-INTERFACES-**VM**, BOR-04..BOR-11 | VM blueprint |
| `BOR-SINGLE-STD-HW` | BOR-01, BOR-03-INTERFACES-**30G**, BOR-04..BOR-11 | 30G, 50G, 120G blueprints (port names via meta vars) |
| `BOR-SPA-HUB-STD-*` (future) | BOR-01..BOR-11 + BOR-20+ SPA-hub additions | SPA hub blueprints |

**Naming rationale**: `BOR-SINGLE-STD-HW` is deliberately platform-agnostic — used by 30G, 50G, AND 120G blueprints. Port names (`wan`/`lan1` for 30G/50G, `port1`/`port16` for 120G) come from CSV meta vars, not the template body.

### 2.5 Policy Package

Contains firewall addresses (referencing meta vars), policies (referencing normalized interfaces), shapers, shaping-policies.

| Package | Contents | Role |
|---|---|---|
| `BOR-SINGLE-STD-PKG` | 3 addresses (LOCAL-LAN, BOR_Primary_PUBLIC, BOR_Secondary_PUBLIC), 3 policies (LAN→SDWAN, SDWAN→LAN, LAN→Underlay), 2 shapers (100_MBPS_UP/DOWN), 1 shaping-policy (BOR_OUTBOUND_SHAPER) | All BOR spoke blueprints |
| `BOR-SPA-HUB-STD-PKG` (future) | Same + 1 additional HAIRPIN policy (SDWAN→SDWAN for spoke-to-spoke) | SPA hub blueprints |

**Quirk**: `firewall shaper traffic-shaper.maximum-bandwidth` is `uint32` — REJECTS `$(VAR)` at write time. Use fixed values (or per-device `dynamic_mapping`).

### 2.6 Device Blueprints

The atomic unit an SE picks by name. Contains platform + templates + prerun + package refs.

| Blueprint | Platform | cliprofs | prerun-cliprof | pkg | Live oid |
|---|---|---|---|---|---|
| `BOR-SINGLE-STD-VM` | FortiGate-VM64-KVM | `[BOR-SINGLE-STD]` | `[BOR-02-GREENFIELD-VM]` | `BOR-SINGLE-STD-PKG` | 6594 |
| `BOR-SINGLE-STD-HW` | FortiGate-30G | `[BOR-SINGLE-STD-HW]` | `[BOR-02-GREENFIELD-HW-SMALL]` | `BOR-SINGLE-STD-PKG` | 7392 |
| `BOR-SINGLE-STD-50G` | FortiGate-50G | `[BOR-SINGLE-STD-HW]` (reuse) | `[BOR-02-GREENFIELD-HW-SMALL]` (reuse) | `BOR-SINGLE-STD-PKG` (reuse) | 7411 |
| `BOR-SINGLE-STD-120G` | FortiGate-120G | `[BOR-SINGLE-STD-HW]` (reuse) | `[BOR-02-GREENFIELD-120G]` (new) | `BOR-SINGLE-STD-PKG` (reuse) | 7432 |

**Key flags on every blueprint**:
- `prov-type: 1` (templates)
- `port-provisioning: 1` — **triggers FMG auto-magic**: on CSV import, the blueprint's `cliprofs` template group + `pkg` policy package have the new device auto-appended to their `scope member` lists. Manual scope binding is NOT required.
- `linked-to-model: 1`
- `enforce-device-config: 0`

**Description quirk**: FMG's XSS check rejects parentheses `()` and other punctuation in `description`. Use plain text.

**Rename limitation**: FMG blueprint's `template-group` field is broken via API (all forms rejected). Use `cliprofs: ["group-name"]` instead.

### 2.7 DVMDB Device Groups

Organizational buckets per role. Blueprint doesn't reference these; they're a downstream target for bulk-install, filtering, and (future) shared scope binding.

| Group | Role | Live oid |
|---|---|---|
| `BOR_Branch_Single` | Single-circuit BOR spokes (spoke-1, spoke-2, 30G-spoke-4, 50-spoke-5, 120G-spoke-6) | 360 |
| `BOR_Branch_Dual` | Dual-circuit BOR spokes (empty, ready) | 361 |
| `BOR_Branch_SPA_Hub` | SPA hub role | 462 |

**Field-name quirks (FMG 7.6 requires EXACT names)**:
- `desc` NOT `description`
- `meta fields` (space) NOT `meta-fields`
- `object member` (space) NOT `object-member`
- `os_type` (underscore); values: `fos`, `fsw`, `fpx`, `foc`, `faz`, `fml`, etc.

**Critical readback quirk**: `set /object member` returns code=0 OK, but JSON-RPC has NO readback path. Only the GUI's `/gui/adoms/{adom_oid}/groups/{grp_oid}?fields=memb` (via `flatui_proxy`, session cookie required) can render membership. Tools must return `members_submitted` + `members_verified: null` + a `verify_hint` pointing to the GUI.

---

## 3. Phase 2 — Per-Site Provisioning

One SE, one CSV, one tool call — a device goes from nothing to install-ready.

### 3.1 Generator produces the CSV

SE fills the generator schema (site_id, hostname, WAN mode, port names, LAN subnet, etc.). Generator produces two files under `fmg-export/hardware-blueprints/{platform}/`:

- `site-N.fmg.csv` (or `DHCP-WAN-*-spoke-N.fmg.csv` / `STATIC-WAN-*-spoke-N.fmg.csv`) — the authoritative FMG import CSV
- `site-N.conf` — human-readable preview of the CLI FMG would push, for review

**Rule**: The generator CSV is the SOURCE OF TRUTH. Do NOT hand-craft CSVs — every gotcha we've documented came from someone (me) hand-crafting one. The generator encodes per-site addressing conventions (per-site WAN /24, per-site LAN /24 = `10.200.{SITE_ID*10}.0/24`, ROUTER_ID = `10.30.1.{100+SITE_ID}`, etc.).

**CSV columns (34)**:
```
Serial Number, Device Blueprint, Name,
HOSTNAME, SITE_ID, ADMIN_PASSWORD,
WAN_PORT, LAN_PORT, WAN_MODE, WAN_IP, WAN_MASK, WAN_GATEWAY, WAN_DHCP_DIST,
MGMT_GATEWAY, LAN_IP, LAN_MASK, LAN_SUBNET,
ROUTER_ID, TIMEZONE, ADMIN_SPORT, ADMIN_TIMEOUT,
DEVICE_ALIAS, BGP_AS, BGP_KEEPALIVE, BGP_HOLDTIME,
SLA_LATENCY_MS, SLA_JITTER_MS, SLA_PKTLOSS_PCT,
SITE_BW_MBPS, SITE_BW_DOWN_MBPS,
POP1_FQDN, POP2_FQDN, POP1_PROBE, POP2_PROBE
```

Blank cells → no per-device override (uses ADOM default).

### 3.2 Import with `model-device-import-csv v1.2.1`

**One tool call replaces ~10 manual steps.**

```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-model-device-import-csv/1.2.1",
    parameters={
        "fmg_host": "184.73.7.106",
        "adom": "BOR_Customer_1",
        "csv_path": "C:/.../fmg-export/hardware-blueprints/30G/DHCP-WAN-30G-spoke-4.fmg.csv",
        "auto_bind": {
            "resolve_from_blueprint": True,   # -> BOR-SINGLE-STD-HW + BOR-SINGLE-STD-PKG
            "device_group": "BOR_Branch_Single",
            "normalized_interfaces": [
                {"name": "LAN_ZONE",      "zone_type": "system"},  # LAN_PORT is a real system zone
                {"name": "SDWAN_ZONE",    "zone_type": "sdwan"},   # avoid -553 namespace collision
                {"name": "Underlay_ZONE", "zone_type": "sdwan"},
            ],
        },
        # Defaults ON (do not override unless you know why):
        # set_hostname_from_name: True
        # pre_create_zone_shells:  True
        # resolve_blueprint_platform: True
        # wait: True
    }
)
```

### 3.3 What the tool does under the hood (in ONE API sequence)

| # | Operation | Endpoint / method | Why |
|---|---|---|---|
| ① | Parse CSV client-side | (local) | Extract required cols + meta vars |
| ② | Look up blueprint platform | `get /pm/config/adom/{adom}/obj/fmg/device/blueprint/{bp}` | Fill `_platform` per row |
| ③ | Bulk add-dev-list | `exec /dvm/cmd/add/dev-list` | Creates device(s) in DVMDB in one call |
| ④ | Poll task to done | `get /task/task/{tid}` | Wait for FMG to finish adds |
| ⑤ | Per-row verify | `get /dvmdb/adom/{adom}/device/{name}` | Confirm each row landed |
| ⑥ | **hostname_fix** (v1.2.0) | `update /dvmdb/adom/{adom}/device/{name}` `{name, hostname: name}` | FMG defaults `hostname=sn` until first install; this fixes display immediately |
| ⑦ | **auto-resolve blueprint refs** (v1.1.0) | `get blueprint fields: cliprofs, pkg` | Read `cliprofs[0]` and `pkg` to auto-fill `template_group` + `policy_package` |
| ⑧ | **template group scope append** (v1.1.0) | `get /pm/config/adom/{adom}/obj/cli/template-group/{grp}` → merge → `update` | GET-extend-UPDATE (FMG `update` REPLACES). Dedup by (name,vdom). Usually reports "nothing to add" because `port-provisioning:1` blueprint magic already scoped it. Idempotent + safe. |
| ⑨ | **policy pkg scope append** (v1.1.0) | Same pattern on `/pm/pkg/adom/{adom}/{pkg}` | Same auto-magic; same dedup |
| ⑩ | **device group member add** (v1.1.0) | `add /dvmdb/adom/{adom}/group/{grp}/object member` | FMG 7.6.7 no-readback quirk — returns `members_verified: null` |
| ⑪ | **pre_create_zone_shells** (v1.2.1, per-zone) | `set /pm/config/device/{dev}/vdom/{vdom}/{system/zone \| system/sdwan/zone}/{name}` | Satisfies `-10131 datasrc invalid` validation. `zone_type: system` → `/system/zone/`. `zone_type: sdwan` → `/system/sdwan/zone/` (avoids `-553 conflicts with a sdwan zone`) |
| ⑫ | **dynamic_mapping add** (v1.1.0) | `add /pm/config/adom/{adom}/obj/dynamic/interface/{intf}/dynamic_mapping` `{_scope, local-intf}` | Per-device normalized-interface binding |

### 3.4 Post-import state expectation

For a healthy spoke import against a proven blueprint, the device DB should look like this (matches `spoke-1` / `30G-spoke-4` / `50-spoke-5` / `120G-spoke-6`):

```
system zone       : [LAN_ZONE]                                      (bound to LAN_PORT at install)
system sdwan zone : [virtual-wan-link, SDWAN_ZONE, Underlay_ZONE]   (created by SDWAN template)
```

Meta var overrides for the device should match the CSV row 1:1 (except blank cells → no override).

### 3.5 Install push

**GUI**: Device Manager → {ADOM} → {device} → Install Wizard.
**API**: `exec /securityconsole/install/preview` and `exec /securityconsole/install/package`.

Expected sequence at install:
1. Prerun runs first (`prerun-cliprof` templates) — purges greenfield state
2. CLI templates in group order (BOR-01, BOR-03, BOR-04...)
3. Policy Package copies to device DB
4. Device dial-home applies

If prerun is misconfigured OR pkg validation fails before templates run, you get chicken-and-egg errors — see §5 troubleshooting.

---

## 4. Object Naming Conventions

Consistent naming keeps the workflow legible for SEs and repeatable across tenants.

| Layer | Pattern | Example |
|---|---|---|
| Meta vars | `SCREAMING_SNAKE_CASE` | `WAN_MODE`, `POP1_FQDN`, `SITE_BW_MBPS` |
| CLI templates | `BOR-{NN}-{PURPOSE}[-{platform-family}]` | `BOR-01-SYSTEM-GLOBAL`, `BOR-03-INTERFACES-HW`, `BOR-02-GREENFIELD-120G` |
| CLI template groups | `BOR-{ROLE}-STD[-{platform-family}]` | `BOR-SINGLE-STD`, `BOR-SINGLE-STD-HW`, `BOR-SPA-HUB-STD` |
| Policy packages | `BOR-{ROLE}-STD-PKG` | `BOR-SINGLE-STD-PKG`, `BOR-SPA-HUB-STD-PKG` |
| Blueprints | `BOR-{ROLE}-STD-{platform}` | `BOR-SINGLE-STD-VM`, `BOR-SINGLE-STD-HW`, `BOR-SPA-HUB-STD-120G` |
| Device groups | `BOR_Branch_{Role}` (underscore, matches FMG UI convention for groups) | `BOR_Branch_Single`, `BOR_Branch_SPA_Hub` |
| Normalized interfaces | `{PURPOSE}_ZONE` | `LAN_ZONE`, `SDWAN_ZONE`, `Underlay_ZONE` |
| Devices | `[{platform-prefix}-]spoke-{site_id}` | `spoke-1` (VM), `30G-spoke-4`, `120G-spoke-6` |

**Roles supported today**:
- `SINGLE` — one WAN circuit, two BOR IPsec tunnels (Primary + Secondary)
- `DUAL` — two WAN circuits, four BOR IPsec tunnels (future; group + blueprint stubs exist)
- `SPA-HUB` — Single-circuit BOR + SPA Hub (terminates spoke tunnels for hairpin) (in progress)

**Numbering reserved**: `BOR-01..BOR-19` for base templates. `BOR-20..BOR-29` for SPA-Hub additions. `BOR-30..BOR-39` for dual-circuit. Leaves room for growth.

---

## 5. FMG 7.6 API Quirks + How the Tool Handles Them

Every quirk below cost hours of debugging on a real deployment. All are baked into `v1.2.1`.

### 5.1 Blueprint auto-magic (port-provisioning: 1)

**Behavior**: When a device is added via `add-dev-list` with a blueprint that has `port-provisioning: 1`, FMG AUTO-APPENDS the new device to the blueprint's `cliprofs[0]` template group + `pkg` policy package `scope member` lists.

**Impact**: Explicit template_group + policy_package binds in `auto_bind` become idempotent (report "nothing to add"). Do NOT remove them — they're valuable when blueprint has different flags OR SE calls the tool without a blueprint.

### 5.2 -10131 `datasrc invalid. object: system zone`

**Cause**: FMG validates `dynamic_mapping.local-intf` against device-DB zone tables. Fresh model devices have no zones yet.

**Fix**: `pre_create_zone_shells` (default true) — `set` an empty zone shell on the device DB BEFORE adding dynamic_mapping. CLI templates populate the zone at install.

### 5.3 -553 `the name "X" conflicts with a sdwan zone of the same name` at install

**Cause**: FortiOS shares namespace between `system zone` and `system sdwan zone`. `system zone SDWAN_ZONE` shell (from a naive pre_create) collides with SDWAN template's `system sdwan zone SDWAN_ZONE`.

**Fix**: v1.2.1 `zone_type` per normalized_interface. `LAN_ZONE` → `system` (real system zone). `SDWAN_ZONE`, `Underlay_ZONE` → `sdwan` (goes to `/system/sdwan/zone/`).

### 5.4 -10015 `used` when deleting a zone shell

**Cause**: Anything that references the zone (dynamic_mapping local-intf, device-DB firewall policies from a failed install push) holds a delete-lock.

**Fix ordering**: DELETE the references FIRST (dynamic_mapping entries, orphaned device-DB firewall policies), THEN delete the zone shell.

### 5.5 -9001 XSS-suspect chars in `description`

**Cause**: FMG description validator rejects parentheses `()`, colons in some contexts, other punctuation.

**Fix**: Plain-text descriptions only. Alphanumerics + hyphens + spaces.

### 5.6 -9001 write-time on undeclared meta vars

**Cause**: FMG validates every `{{ VAR }}` in a Jinja template at template-create time. Referring to a meta var that doesn't exist in the ADOM yet returns `-9001 unexpected char '$' at N` (or similar).

**Fix**: Bottom-up build order. Meta vars → CLI templates → CLI group → blueprint.

### 5.7 -9001 on interfaces missing `set vdom` / `set type`

**Cause**: FMG install-check is STRICTER than FortiOS. Model VM devices need `set vdom "root"` + `set type physical` inside every interface edit. HW devices don't.

**Fix**: `BOR-03-INTERFACES-VM` includes these lines; `BOR-03-INTERFACES-HW` (used by HW) omits them.

### 5.8 -9001 admin missing accprofile

**Cause**: Install-check requires `set accprofile` on admin edits.

**Fix**: `BOR-01-SYSTEM-GLOBAL` includes `set accprofile "super_admin"`.

### 5.9 Meta var `_scope.vdom` is `"global"` NOT `"root"`

**Cause**: ADOM meta vars aren't per-vdom. FMG uses `global` as the vdom marker in `_scope`.

**Fix**: Direct override updates use `/pm/config/adom/{adom}/obj/fmg/variable/{VAR}/dynamic_mapping/{dev}/global` with `data: {value: "..."}`. Whole-list embed in parent `update` returns -10. `set` on child collection with a list returns -10.

CSV imports handle this automatically via `add-dev-list`'s internal handling — this quirk only matters for POST-import surgical updates.

### 5.10 Device group `object member` write-then-read

**Cause**: FMG 7.6.7 accepts `set /dvmdb/adom/{adom}/group/{grp}/object member` (code=0) but JSON-RPC has no readback path. The GUI reads via `/gui/adoms/{oid}/groups/{oid}?fields=memb` through `flatui_proxy` (requires session cookie; API token rejected).

**Fix**: Tool returns `members_submitted` + `members_verified: null` + `verify_hint` pointing to GUI. Trust the write; eye-check in GUI if needed.

### 5.11 Device DELETE endpoint payload shape

**Cause**: `/dvm/cmd/del/device` requires `data.device` as a plain string, not an array or dict. `/dvm/cmd/del/dev-list` fails silently (`-20002`).

**Fix**: `exec /dvm/cmd/del/device` with `data: {adom: <name>, device: <device-name-string>}`. Direct `delete /dvmdb/adom/{adom}/device/{name}` returns -9 (invalid command).

**Cascade**: Deleting a device cleans up meta var overrides, dynamic_mapping entries, scope member refs, and device-DB zones. Idempotent for re-import.

### 5.12 SDWAN template import endpoint

**Cause**: Cannot clone SDWAN config via the standard `method: clone` on `system/sdwan`.

**Fix**: `exec /pm/config/adom/{adom}/_wanprof/import` with `data: {template: <target_wanprof>, device: {name, vdom}, description}`. Target wanprof shell must exist first.

### 5.13 System template import endpoint

**Cause**: Similar to SDWAN — dedicated endpoint, different payload from SDWAN.

**Fix**: `exec /pm/config/adom/{adom}/_devprof/import` with `data: {device: <name-string>, devprof: <target_name>, description}`. Note: `device` is a plain STRING here (not `{name,vdom}` dict like SDWAN uses).

### 5.14 BOR-07 route 10 (bastion) precedence

**Cause (fixed 2026-08-26)**: Old precedence was `MGMT_GATEWAY > WAN_MODE`, causing DHCP-mode devices with a set MGMT_GATEWAY to emit `set gateway <static>` which fails install if off-subnet.

**Fix**: New precedence is `WAN_MODE=dhcp > MGMT_GATEWAY > WAN_GATEWAY`. In BOR-07-STATIC-ROUTES template:
```jinja
{% if WAN_MODE == "dhcp" %}        set dynamic-gateway enable
{% elif MGMT_GATEWAY %}        set gateway {{ MGMT_GATEWAY }}
{% else %}        set gateway {{ WAN_GATEWAY }}
{% endif %}
```

---

## 6. Tenant Onboarding — Two Paths

### 6.1 Clone Template ADOM (fast — existing FMG has BOR_Customer_1)

- Copy `BOR_Customer_1` → `BOR_Customer_N`
- All meta vars, templates, groups, blueprints, pkg, normalized interfaces come with
- Update ADOM-level defaults (SEED_PSK, ADMIN_PASSWORD, tenant-specific vars) for the new tenant
- Proceed to Phase 2 (per-site imports)

**Time**: ~15 minutes to clone + customize.

### 6.2 Greenfield ADOM (partner has nothing)

- Create new ADOM
- Run full Phase 1 from scratch: meta vars → normalized interfaces → CLI templates → groups → pkg → blueprints → device groups
- Follow §2 in order

**Time**: ~2-4 hours for the initial ADOM; automated by an SDK "provision-greenfield-adom" toolchain (future).

**Both paths converge to the same Phase 2 workflow.**

---

## 7. Tools Involved (SDK Reference)

All tools live under `tools/` in this repo. Naming: `org.ulysses.noc.fortimanager-{purpose}`.

| Phase | Tool | Purpose |
|---|---|---|
| 1 | `metadata-create` / `metadata-set-adom` | Declare / update meta vars |
| 1 | `cli-template-create` | Author BOR-XX-* templates |
| 1 | `cli-template-group-create` | Bundle templates in order |
| 1 | `sdwan-template-create` | Create wanprof shell (import fills it) |
| 1 | `system-template-create` | Create devprof shell (import fills it) |
| 1 | `provisioning-template-create` | Create empty template shells (unified) |
| 1 | `device-blueprint-create` | Assemble blueprint (platform + cliprofs + prerun + pkg) |
| 1 | `device-group-create` | Create DVMDB device groups |
| 1 | `template-clone-from-device` v1.2.0 | Clone runtime config from DVMDB to dedicated templates (bgp/static/ipsec-p1/p2/sdwan/system presets) |
| 2 | **`model-device-import-csv` v1.2.1** | THE Phase-2 workhorse — CSV → device + auto-bind everything |

**Version pinning**: Always use the SEMVER-latest version in a fresh deployment. Older versions are kept for backward compat but lack the fixes documented in §5.

---

## 8. Troubleshooting Playbook

| Symptom | Likely cause | Diagnostic | Fix |
|---|---|---|---|
| `-553 conflicts with a sdwan zone` at install | Naive pre_create shells created system zones for SDWAN-named zones | Compare `system zone` on failing device vs known-good spoke | Use v1.2.1 with `zone_type: sdwan` for SDWAN_ZONE/Underlay_ZONE |
| `-10131 datasrc invalid. object: system zone` at add-dynamic_mapping | Fresh device has no zone yet | Check `pm/config/device/{dev}/vdom/{vdom}/system/zone` | Enable `pre_create_zone_shells` (default true in v1.2.1) |
| `-10015 used` when deleting a zone shell | dynamic_mapping or device-DB firewall policy still references it | List refs in ADOM + device DB | Delete refs first (dynamic_mapping child entries, orphaned firewall policies), then shell |
| `devsnexist1|<SN>|devsnexist2` err=-10 at import | SN already registered somewhere in FMG (any ADOM) | `get /dvmdb/device` search by SN | Delete or repurpose the existing device |
| Import succeeded but hostname shows as SN | v1.1.0 or older (no hostname_fix) | Check tool version | Upgrade to v1.2.0+; or manually `update /dvmdb/adom/{adom}/device/{name}` with `{name, hostname}` |
| Meta var override didn't land after direct API update | Wrong vdom in _scope | GET the variable and inspect _scope | Use vdom=`global` not `root` |
| Install fails on bastion route "gateway not in subnet" | Old BOR-07 with MGMT_GATEWAY precedence bug | Diff BOR-07-STATIC-ROUTES route 10 block | Apply the fix in §5.14 |
| Blueprint create fails -10131 datasrc invalid on cliprofs | Group referenced doesn't exist (e.g. group create failed on description) | GET the group | Fix the group create first (usually plain-text description) |
| Group scope member append returns "nothing to add" | Blueprint's port-provisioning already auto-scoped | Expected behavior — safe | No action needed |

**Golden state reference**: `spoke-1` in `BOR_Customer_1` on `184.73.7.106` — the first fully-working device. When something is broken on a new device, diff against spoke-1's state.

---

## 9. Live Reference — BOR_Customer_1 Snapshot

As of the last update to this doc, `BOR_Customer_1` on `184.73.7.106` contains:

- **48 metadata variables** (30 tenant + 17 site + 1 pre-existing `vm_interface_number`)
- **3 normalized interfaces** with 45 platform_mapping entries each (LAN_ZONE / SDWAN_ZONE / Underlay_ZONE)
- **14 CLI templates** (BOR-01..BOR-11 shared + BOR-02-GREENFIELD-{VM,30G,120G} + BOR-03-INTERFACES-{VM,30G})
- **2 CLI Template Groups** (BOR-SINGLE-STD, BOR-SINGLE-STD-HW)
- **1 Policy Package** (BOR-SINGLE-STD-PKG) with 3 addresses + 3 policies + 2 shapers + 1 shaping-policy
- **4 Device Blueprints** (BOR-SINGLE-STD-VM, -30G, -50G, -120G)
- **4 Device Groups** (BOR_Branch, BOR_Branch_Single, BOR_Branch_Dual, BOR_Branch_SPA_Hub)
- **6 devices** (spoke-1, spoke-2, 30G-spoke-4, 50-spoke-5, 120G-spoke-6, +1 legacy)

---

## 10. Meta

**Session that produced this workflow**: 2026-08-25 → 2026-08-26, Daniel Howard (Fortinet SE) + Claude (Opus 4.7).

**Bug-drive iteration count**: 4 major SDK versions of `model-device-import-csv` (v1.0.0 → v1.2.1), 5 install-blocking FMG quirks discovered + fixed, 1 config-generator bug identified (BOR-07 route 10 precedence — fixed in FMG template; user patching in generator).

**Update this doc when**: You add a new role (BOR-DUAL, BOR-SPA-HUB when done), discover a new FMG quirk, or bump a tool major version.

---

*This doc lives in the FortiManager-AI-SDK repo. If you're an AI reading this cold, you now know everything the previous session learned.*
