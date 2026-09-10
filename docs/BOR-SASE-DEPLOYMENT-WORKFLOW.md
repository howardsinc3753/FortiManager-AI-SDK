# FortiSASE Branch OnRamp (BOR) Deployment Workflow

**Audience**: Partner engineers deploying MSSP-scale FortiSASE BOR through FortiManager 7.6+, and AI assistants (Claude, etc.) picking up this repo cold.

**Purpose**: End-to-end reference for the MSSP deployment model — how a tenant ADOM is prepped once (Phase 1), how each branch site is provisioned (Phase 2), and how the config is pushed to the device (Phase 3). Includes the machine-checkable **cross-repo contract** with the [FortiSASE-SDK](https://github.com/howardsinc3753/FortiSASE-SDK) config generator, the four supported BOR roles, the PRIMARY_POP alt-primary feature, and the 22 documented FMG 7.6 gotchas with resolutions.

**Companion generator**: `.fmg.csv` files consumed by Phase 2 are produced by [`FortiSASE-SDK/automation/sdwan-ztp/config-generator/`](https://github.com/howardsinc3753/FortiSASE-SDK) (a schema-first Streamlit app + MSSP Deploy provisioning page). CSVs live under `fmg-export/hardware-blueprints/{VM,30G,50G,120G, DUAL/*, SPA-Hub/*, DUAL-SPA-Hub/*}/`.

---

## 1. The Three-Tool Pipeline

Every deployment runs through three SDK tools in sequence. Each is idempotent, has structured output, and can be called from a UI (the FortiSASE-SDK Streamlit "MSSP Deploy" page invokes them via subprocess) or from a script.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  PHASE 1: adom-init            (once per tenant, ~30 seconds)            │
│  Provisions ~290 FMG objects: meta vars, normalized interfaces, CLI      │
│  templates, template groups, addresses, shapers, policy packages,        │
│  device blueprints, device groups.                                       │
│  Two fail-fast pre-flights: contract validator + tenant-FQDN gate.       │
└──────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌──────────────────────────────────────────────────────────────────────────┐
│  PHASE 2: model-device-import-csv     (seconds per site)                 │
│  One row per device. Creates offline model device in DVMDB; auto-binds   │
│  to blueprint's template group + policy package; adds to role's device   │
│  group; pre-creates the 3 normalized zone shells for install validation. │
└──────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌──────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: install-push          (seconds per device)                     │
│  Two exec calls: install/device (CLI templates → device DB) then         │
│  install/package (Policy Package → device DB). Task-based, polls to      │
│  terminal, returns per-device install log lines with root-cause history. │
│  Preview mode uses flags: ["preview"] for validation without commit.     │
└──────────────────────────────────────────────────────────────────────────┘
                                    ↓
                    Device dial-home (FGFM) → config live
```

**MSSP economy**: Phase 1 runs once per tenant ADOM. Phase 2 + Phase 3 repeat per branch site. Phase 1 assets are amortized across every site in the ADOM.

---

## 2. Phase 1 — `fortimanager-adom-init` (ADOM Prep)

Live at `tools/org.ulysses.noc.fortimanager-adom-init/`. Single command bootstraps a fresh ADOM from cold in ~30 seconds.

### 2.1 CLI

```bash
python org.ulysses.noc.fortimanager-adom-init.py \
    --fmg-host <hostname> \
    --adom <adom-name> \
    --tenant-config <yaml-path> \
    [--create-adom]           # auto-create if ADOM doesn't exist
    [--dry-run]               # print plan without writes
    [--skip-contract-check]   # emergency bypass (NOT recommended)
```

**Tenant config YAML** overrides manifest defaults with real values. Example (`content/tenant-defaults.example.yaml`):

```yaml
POP1_FQDN: ipsec-abc123-dfw-f3.prod.fortisase.com
POP2_FQDN: ipsec-abc123-mia-f3.prod.fortisase.com
POP1_NAME: DFW
POP2_NAME: MIA
POP1_BOR_NODE: 10.30.1.1
POP2_BOR_NODE: 10.30.2.1
ADMIN_PASSWORD: <your-password>
SEED_PSK: <your-psk>
```

### 2.2 Pre-flight gates (fail-fast before any FMG write)

Two guardrails run BEFORE the first FMG write. Both surface clear per-issue messages; both exit non-zero on failure.

#### Pre-flight #1 — Contract validator (exit code 2)

Reads `contract/roles-and-columns.yaml` (byte-vendored from FortiSASE-SDK App generator) and asserts:

1. Every role's `template_folder` exists on disk under `content/templates/`
2. Every `{blueprint_prefix}-{PLATFORM}` blueprint exists in `content/adom-manifest.yaml`
3. Every role's `template_group.{vm, hw}` exists in the manifest
4. Every role's `policy_package` + `device_group` exists in the manifest
5. Every UPPER_SNAKE var referenced by any `.j2` is declared in the contract's `meta_vars`
6. `SITE_ID` scope is `per_device` (gotcha #17 safety-belt)
7. Every VM/30G/50G/120G platform alias maps to a real FortiOS platform in `platform-list.yaml`

**Plus naming-drift guard** — sentinel-renders each role's templates with placeholder PoP names (`NAMINGDRIFT1/2`), fails loud if the sentinel leaks into any object-name context. Catches template regression to var-derived object naming (see §4).

#### Pre-flight #2 — Tenant-FQDN gate (exit code 3)

Overlays tenant-config on manifest defaults, refuses if any resolved FQDN meta-var (POP1_FQDN, POP2_FQDN) or firewall_address `fqdn` field still contains `<`/`>` chars. Catches "user forgot to fill in real tenant FQDN" upfront rather than letting FMG's XSS filter reject it later with a cryptic message. **Not skippable** — a placeholder FQDN can't produce a working config.

### 2.3 Objects bootstrapped (~290 total)

| Category | Count | Notes |
|---|---|---|
| Meta variables | 62 | Tenant-scope (BGP, SLA, PoPs, timing) + per-device-scope (WAN, LAN, ID) + PRIMARY_POP (v1.1+) |
| Normalized interfaces | 3 | `LAN_ZONE` (system), `SDWAN_ZONE` (sdwan), `Underlay_ZONE` (sdwan), each with 45 `platform_mapping` entries |
| CLI templates | 41 | Distributed across 4 role folders (see §2.5) |
| CLI template groups | 8 | 2 per role × VM/HW split |
| Firewall addresses | 10 | `LOCAL-LAN` + 6 `BOR_*_PUBLIC` (FQDN, `$(POP*_FQDN)` refs) + 3 RFC1918 (SPA hub uses underscore-named 10/172/192) |
| Traffic shapers | 2 | `BOR_UP_SHAPER`, `BOR_DOWN_SHAPER` |
| Policy packages | 2 | `BOR-SPOKE-STD-PKG` (both spoke roles) + `BOR-SPA-HUB-STD-PKG` (both hub roles) — see §2.6 |
| Device blueprints | 16 | 4 roles × 4 platforms (VM/30G/50G/120G) |
| DVMDB device groups | 3 | `BOR_Branch_Single`, `BOR_Branch_Dual`, `BOR_Branch_SPA_Hub` |

### 2.4 Meta variables (organized by concern)

```
IDENTITY:      HOSTNAME, SITE_ID, DEVICE_ALIAS, ROUTER_ID, TIMEZONE
CREDS:         ADMIN_PASSWORD, ADMIN_SPORT, ADMIN_TIMEOUT, SEED_PSK
LAN:           LAN_IP, LAN_MASK, LAN_PORT, LAN_SUBNET
BASTION:       BASTION_IP, BASTION_MASK
WAN1:          WAN_PORT, WAN_MODE, WAN_IP, WAN_MASK, WAN_GATEWAY, WAN_DHCP_DIST
WAN2 (dual):   WAN2_PORT, WAN2_IP, WAN2_MASK, WAN2_GATEWAY
LEGACY:        MGMT_GATEWAY, MGMT_GATEWAY2   ← optional bastion/mgmt override
POP/SASE:      POP1_FQDN, POP1_NAME, POP1_BOR_NODE, POP1_PROBE
               POP2_FQDN, POP2_NAME, POP2_BOR_NODE, POP2_PROBE
BGP:           BGP_AS, BGP_KEEPALIVE, BGP_HOLDTIME
BGP-POLICY:    FAIL_COMMUNITY, FAIL_LOCAL_PREF,
               POP1_COMMUNITY, POP1_LOCAL_PREF,
               POP2_COMMUNITY, POP2_LOCAL_PREF
SLA:           SLA_LATENCY_MS, SLA_JITTER_MS, SLA_PKTLOSS_PCT
BW:            SITE_BW_MBPS, SITE_BW_DOWN_MBPS
SPA-HUB only:  FABRIC_HUB_IP, FABRIC_HUB_REMOTE, FABRIC_NETWORK_ID, FABRIC_OVERLAY,
               FABRIC_POOL_START, FABRIC_POOL_END, HUB_LOOPBACK, HUB_PROPOSAL,
               ONRAMP_DHGRP, ONRAMP_NETWORK_ID, ONRAMP_PROPOSAL
PLATFORM AID:  vm_interface_number
FEATURE:       PRIMARY_POP           ← v1.1 (bor-single) + v1.2 (bor-dual)
```

Every var is declared in `content/adom-manifest.yaml` with a default value; per-site overrides flow in via Phase 2 CSV columns (see §3).

**Meta-var scope quirk**: ADOM meta-var overrides use `_scope.vdom = "global"` (NOT `"root"`). CSV importer handles this automatically. Direct API updates: `set /pm/config/adom/{adom}/obj/fmg/variable/{VAR}/dynamic_mapping/{dev}/global` with `data: {value: "..."}`.

### 2.5 CLI templates + template groups

Templates live at `content/templates/{role}/`. Numbered `BOR-01..BOR-24` (spoke) and `BOR-SPA-01..BOR-SPA-24` (hub). Numbering leaves room for growth (see §4).

**Four role folders**:

| Role folder | Templates | Purpose |
|---|---|---|
| `bor-single/` | 12 | Single-WAN spoke: BOR-01/03-VM/03-HW/04/05/07/08/09/11 + 3 greenfield-purge prerun variants (VM/HW-small/120G) |
| `bor-dual/` | 9 | Dual-WAN spoke: same shape as single with dual-tunnel BGP/SDWAN + WAN2 interface |
| `bor-spa-single/` | 10 | SPA hub, single-WAN: BOR-SPA-01/03-VM/03-HW/04/05 + BOR-SPA-20 loopback + BOR-SPA-21 SASE_Hub dial-up + BOR-SPA-22 routes + BOR-SPA-23 BGP-RR + BOR-SPA-24 SDWAN |
| `bor-spa-dual/` | 10 | SPA hub, dual-WAN: same as spa-single with 4 BOR tunnels + WAN2 |

**Template groups** (8, bundle templates in emit order):

```
bor-single:       BOR-SINGLE-STD          (VM)    /  BOR-SINGLE-STD-HW
bor-dual:         BOR-DUAL-STD-VM                 /  BOR-DUAL-STD-HW
bor-spa-single:   BOR-SPA-SINGLE-STD-VM           /  BOR-SPA-SINGLE-STD-HW
bor-spa-dual:     BOR-SPA-DUAL-STD-VM             /  BOR-SPA-DUAL-STD-HW
```

Naming asymmetry: `BOR-SINGLE-STD` (no `-VM` suffix, legacy) vs `BOR-SINGLE-STD-VM` (dual + SPA convention). Documented in contract v2_backlog; kept as-is because renaming would churn 2 live ADOMs (BOR_Customer_1 + BOR_Customer_10).

### 2.6 Policy packages (2, consolidated)

Policies reference NORMALIZED interfaces (zones), not tunnels. Single (2 tunnels in SDWAN_ZONE) and Dual (4 tunnels in SDWAN_ZONE) share the exact same policy shape per role.

| Package | Role bindings | Contents |
|---|---|---|
| `BOR-SPOKE-STD-PKG` | bor-single + bor-dual | 3 policies (LAN→BOR SIA, BOR→LAN return, LAN→Underlay fallback), addresses, shapers |
| `BOR-SPA-HUB-STD-PKG` | bor-spa-single + bor-spa-dual | Same shape + hairpin policies for SPA fabric spoke-to-spoke |

**Consolidation history**: Originally 4 pkgs (SINGLE, DUAL, SPA-SINGLE, SPA-DUAL). Consolidated on 2026-09-01 because the DUAL variants had byte-identical policy shape to their SINGLE siblings. Freed maintenance burden; no semantic loss.

### 2.7 Device blueprints (16, one per role × platform)

```
BOR-SINGLE-STD-{VM,30G,50G,120G}          → cliprofs BOR-SINGLE-STD(-HW), pkg BOR-SPOKE-STD-PKG
BOR-DUAL-STD-{VM,30G,50G,120G}            → cliprofs BOR-DUAL-STD-{VM,HW},  pkg BOR-SPOKE-STD-PKG
BOR-SPA-SINGLE-STD-{VM,30G,50G,120G}      → cliprofs BOR-SPA-SINGLE-STD-{VM,HW}, pkg BOR-SPA-HUB-STD-PKG
BOR-SPA-DUAL-STD-{VM,30G,50G,120G}        → cliprofs BOR-SPA-DUAL-STD-{VM,HW}, pkg BOR-SPA-HUB-STD-PKG
```

**Key flags on every blueprint**:
- `prov-type: 1` (templates)
- `port-provisioning: 1` — **triggers FMG auto-magic**: on CSV import, blueprint's cliprofs template group + pkg policy package have the new device auto-appended to their `scope member` lists. Manual scope binding is idempotent + safe (usually reports "nothing to add").
- `linked-to-model: 1`
- `enforce-device-config: 0`

**Blueprint description XSS quirk**: FMG rejects `()` and other punctuation. Plain text only.

### 2.8 DVMDB device groups

Organizational buckets per role. Downstream target for bulk-install, filtering, and (future) shared scope binding.

| Group | Role(s) |
|---|---|
| `BOR_Branch_Single` | bor-single |
| `BOR_Branch_Dual` | bor-dual |
| `BOR_Branch_SPA_Hub` | bor-spa-single AND bor-spa-dual (a dual-hub is still a hub) |

**Field-name quirks (FMG 7.6 exact-match required)**:
- `desc` NOT `description`
- `meta fields` (space) NOT `meta-fields`
- `object member` (space) NOT `object-member`
- `os_type` (underscore); values: `fos`, `fsw`, `fpx`, `foc`, `faz`, `fml`

**Membership readback quirk**: `set /dvmdb/adom/{a}/group/{g}/object member` succeeds (code=0) but JSON-RPC has no readback path. The GUI's `/gui/adoms/{oid}/groups/{oid}?fields=memb` (via `flatui_proxy`, session cookie only — API token rejected) is the only render path. Tool returns `members_submitted` + `members_verified: null` + `verify_hint`.

---

## 3. Phase 2 — `fortimanager-model-device-import-csv` (Per-Site Provision)

Live at `tools/org.ulysses.noc.fortimanager-model-device-import-csv/`. One CSV row → one offline model device, fully auto-bound.

### 3.1 CSV shape (column counts by role)

| Role | Column count | Delta |
|---|---|---|
| bor-single | 35 | base 34 + PRIMARY_POP (v1.1) |
| bor-dual | 40 | +5 WAN2 cols (WAN2_PORT/IP/MASK/GATEWAY/MGMT_GATEWAY2) |
| bor-spa-single | 42 | +8 SPA-fabric cols (HUB_LOOPBACK, FABRIC_*, HUB_PROPOSAL) |
| bor-spa-dual | 47 | +5 WAN2 + 8 SPA-fabric |

Blank cells → no per-device override (uses ADOM default). Generator produces the CSV from a form-fill; **do not hand-craft** — every gotcha in §5 came from a hand-crafted CSV.

### 3.2 What the importer does under the hood

One tool call replaces ~10 manual steps.

| # | Operation | Endpoint | Why |
|---|---|---|---|
| ① | Parse CSV | (local) | Extract required cols + meta vars |
| ② | Look up blueprint platform | `get /pm/config/adom/{a}/obj/fmg/device/blueprint/{bp}` | Fill `_platform` per row |
| ③ | Bulk add-dev-list | `exec /dvm/cmd/add/dev-list` | Creates device(s) in DVMDB in one call |
| ④ | Poll task to done | `get /task/task/{tid}` | Wait for FMG to finish adds |
| ⑤ | Per-row verify | `get /dvmdb/adom/{a}/device/{name}` | Confirm each row landed |
| ⑥ | hostname_fix | `update /dvmdb/adom/{a}/device/{name}` `{name, hostname: name}` | FMG defaults hostname=SN until first install |
| ⑦ | Auto-resolve blueprint refs | `get blueprint fields cliprofs, pkg` | Auto-fill template_group + policy_package |
| ⑧ | Template group scope append | GET+extend+UPDATE `template-group/{grp}` | Dedup by (name,vdom). Usually "nothing to add" (blueprint auto-magic). Safe. |
| ⑨ | Policy pkg scope append | Same on `/pm/pkg/adom/{a}/{pkg}` | Same auto-magic dedup |
| ⑩ | Device group member add | `add /dvmdb/adom/{a}/group/{g}/object member` | Gotcha #10 no-readback |
| ⑪ | Pre-create zone shells | `set /pm/config/device/{d}/vdom/{v}/{system,sdwan}/zone/{name}` | Gotcha #2 avoidance |
| ⑫ | Dynamic_mapping add | `add /pm/config/adom/{a}/obj/dynamic/interface/{i}/dynamic_mapping` | Per-device normalized-interface binding |

### 3.3 Post-import expectation

```
system zone       : [LAN_ZONE]                                     (bound to LAN_PORT at install)
system sdwan zone : [virtual-wan-link, SDWAN_ZONE, Underlay_ZONE]  (SDWAN template creates)
```

Meta var overrides for the device should match the CSV row 1:1 (blank cells = no override).

---

## 4. Phase 3 — `fortimanager-install-push` (Device Install)

Live at `tools/org.ulysses.noc.fortimanager-install-push/`. Equivalent to GUI "Install Wizard" — fires two exec tasks and polls each to terminal.

### 4.1 CLI

```bash
python org.ulysses.noc.fortimanager-install-push.py \
    --fmg-host <hostname> \
    --adom <adom> \
    --device <device-name> \
    [--vdom root] \
    [--preview-only]     # flags: ["preview"], validate without commit
    [--pkg <name>]       # override auto-discovered pkg
    [--skip-pkg]         # device-scope only (no policy pkg install)
    [--max-wait-sec 300]
```

### 4.2 Two-step install (both required for a complete device DB)

```
Step 1: exec /securityconsole/install/device
        flags: ["none"] (real) or ["preview"] (validate)
        → CLI templates rendered + copied to device DB
        (interfaces, static routes, sdwan zones, health-checks, addresses)

Step 2: exec /securityconsole/install/package
        Auto-discovered from pkg's scope member; can override with --pkg
        → Policy Package copied to device DB
        (firewall/policy, service groups, shapers)
```

**Historical bug**: install-push v1.0.0 shipped with Step 1 only. Devices "installed successfully" but had 0 policies in device DB. Fixed in v1.1.0 with auto-discovery + step 2. If you see 0 policies post-install on any device, upgrade the tool.

### 4.3 Return shape

```json
{
  "success": true,
  "action": "installed",
  "device_task": {
    "task_id": 141, "state": "done", "num_err": 0,
    "lines": [ {"name": "spoke-1[copy]", "state": "done",
                "detail": "Copy to device done",
                "history": [ {"percent": 1, "detail": "Start copying..."},
                             {"percent": 100, "detail": "Copy done"} ]} ]
  },
  "pkg_tasks": [
    {"label": "install/package[BOR-SPOKE-STD-PKG]",
     "task_id": 142, "state": "done", "num_err": 0, ...}
  ],
  "pkgs_to_install": ["BOR-SPOKE-STD-PKG"]
}
```

**Root-cause surface**: `line[].history[]` carries the real error when top-level `detail` says the useless "Aborted due to previous error." Verdict machinery walks history first when a task errors; you get "install/device task N failed: <the actual Jinja/CLI error>" not the downstream symptom.

---

## 5. The Cross-Repo Contract (v1.2)

Byte-vendored file: `contract/roles-and-columns.yaml`. Authored by FortiSASE-SDK App Claude; consumed here as a byte-identical read-only copy (sha-pinned in commit messages).

### Why a contract exists

FortiSASE-SDK App and this FMG SDK describe the SAME four BOR roles from two different angles:
- **App** models a deployment as `{role, dual_wan, is_vm}` (orthogonal axes)
- **FMG SDK** flattens to a single template_group / blueprint / pkg name

They **translate**, not mirror. The translation used to live only in `fmg_provision.py`, exactly where drift became failed installs. Contract makes the mapping machine-checkable + validators-both-sides.

### Ownership boundary

- **FortiSASE-SDK App owns**: config-generator + CSV export + Streamlit UI (MSSP Deploy page) + contract file (canonical location)
- **FMG SDK owns**: CLI templates + tools (adom-init/model-device-import-csv/install-push) + validator
- **Contract governs**: meta-var/column NAMES only. Rendered object names (RM_FABRIC_IN, RFC1918_10, BOR_Primary) are the shared shape aligned via App-generated reference `.conf` files.

### Feature evolution

| Contract | Feature | Notes |
|---|---|---|
| v1 | Initial 4-role registry + validators + adom-init boot check | Locked the drift risk |
| v1.1 | `PRIMARY_POP` for bor-single | Per-site meta-var flips both RFC1918 + INET traffic to prefer POP2 (see §7) |
| v1.1 | bor-single naming rename | `BOR_{{POP1_NAME}}` → literal `BOR_Primary`; multi-tenant NOC universality (see §6) |
| v1.2 | `PRIMARY_POP` for bor-dual | 4-tunnel group swap; App engine's PoP-group reorder generalizes automatically |
| v1.3 (naming/shape fidelity, no schema bump) | bor-spa-single naming rename + RFC1918 underscore + BGP-RR name align | Matches App generator + live production 120G-hub-1 |

Every change follows the same pipeline: role-spec in `MSSP-SE-Tools/BOR-Role-Registry/` → App builds App-side + generates reference `.conf` diff pair → SDK byte-verifies against it → both sides commit locally → coordinated push after user greenlights.

---

## 6. Object Naming Convention (role-based, tenant-portable)

Object names in the rendered device config are **LITERAL role strings** — not variable-substituted from PoP identity. Rationale: PoPs are tenant-specific (Tenant A: DFW/MIA; Tenant B: NY/Ashburn; Tenant C: two West Coast PoPs). A multi-tenant NOC reads `BOR_Primary` universally; `BOR_DFW` requires the operator to memorize per-tenant PoP mappings.

| Artifact | Single | Dual |
|---|---|---|
| IPSec tunnel / interface / update-source | `BOR_Primary`, `BOR_Secondary` | `BOR_Primary1`, `BOR_Primary2`, `BOR_Secondary1`, `BOR_Secondary2` |
| FQDN address + dstaddr | `BOR_Primary_PUBLIC`, `BOR_Secondary_PUBLIC` | `BOR_{Primary,Secondary}{1,2}_PUBLIC` |
| Health-check | `HC_Primary`, `HC_Secondary` | `HC_Primary1/2`, `HC_Secondary1/2` |
| Route-map | `RM_OUT_PRIMARY`, `RM_OUT_SECONDARY` | `RM_OUT_PRIMARY1/2`, `RM_OUT_SECONDARY1/2` |
| SPA hub RM (fabric demux) | `RM_FABRIC_IN` (single, applied to SASE_Hub neighbor-group) | (same) |
| SPA hub community-lists | `CL_ONRAMP_1..8` + `CL_ONRAMP_FAIL` (9 total, fixed canonical ladder) | (same) |

**`POP1_NAME` / `POP2_NAME` meta-vars** are display-only — used in `set comment "..."` for human context (`set comment "BOR Primary node (BGP peer, DFW PoP)"`). Never in an object name that gets cross-referenced.

**Naming-drift guard** (validate_contract.py): sentinel-renders each role's templates with placeholder PoP names (`NAMINGDRIFT1/2`), fails loud if the sentinel leaks into any object-name context (allows it only in `#` comments and `set comment/description` lines). Catches template regression to var-derived object naming; runs at every `adom-init --create-adom` + in CI.

---

## 7. PRIMARY_POP Alt-Primary Feature (v1.1 + v1.2)

Per-site meta-var (values `1` or `2`) that flips which PoP the site prefers for **all traffic** (RFC1918 private-access + INET). Enables MSSPs to split a fleet across POP1 and POP2 to use the full 2Gbps tenant SASE capacity, rather than pinning every site to POP1.

### 7.1 What flips (bor-single, PRIMARY_POP=2)

| Config item | Default (=1) | Alt (=2) |
|---|---|---|
| `RM_OUT_PRIMARY` community | `POP1_COMMUNITY` | `POP2_COMMUNITY` (swapped) |
| `RM_OUT_PRIMARY` local-pref | `POP1_LOCAL_PREF` | `POP2_LOCAL_PREF` (swapped) |
| `RM_OUT_SECONDARY` community + LP | POP2 values | POP1 values (swapped) |
| BOR_Private_Access priority-members | `1 2` | `2 1` |
| BOR_Private_Access SLA order | `HC_Primary, HC_Secondary` | `HC_Secondary, HC_Primary` |
| INET_via_BOR priority-members | `1 2` | `2 1` |
| INET_via_BOR SLA order | `HC_Primary, HC_Secondary` | `HC_Secondary, HC_Primary` |

Route-map + tunnel + HC + BGP-neighbor **NAMES** stay stable across the flip — only the values inside change. BGP-neighbor bindings never churn.

### 7.2 What flips (bor-dual, PRIMARY_POP=2)

Group-level swap: Primary group (Primary1+Primary2 tunnels) trades with Secondary group (Secondary1+Secondary2). Community/LP values swap between groups. SDWAN `priority-members 1 2 3 4` → `3 4 1 2`. SLA order flips to match.

### 7.3 PRIMARY_POP does NOT apply to SPA hub roles (architecturally N/A)

A SPA hub's BGP runs only on the `SASE_Hub` fabric neighbor-group (via `RM_FABRIC_IN`); BOR tunnels on the hub are SDWAN members only, outbound-only for local hub-site SIA. There's no BOR-tunnel BGP route-map to flip. Contract `applies_to: [bor-single, bor-dual]` documents this exclusion.

### 7.4 Implementation notes

- **Jinja pattern**: FMG's Jinja parser does NOT propagate `{% set %}` bindings across the config block (gotcha #20). Use inline conditionals at every substitution: `{{ POP2_COMMUNITY if (PRIMARY_POP | string) == '2' else POP1_COMMUNITY }}`.
- **Values**: bor-single uses meta-var refs (POP1_COMMUNITY etc.); bor-dual uses positional literal ladder (65001:10 / :20 / :30 / :40; lp 200/195/190/185) matching App generator's `AS:(10k) / lp=200-(k-1)*5` formula.
- **Byte-verified** against App generator's diff-pair `.conf` files in `FortiSASE-SDK/automation/sdwan-ztp/config-generator/generated/alt-primary-samples/`.

---

## 8. SPA Hub Architecture (v1.3 fidelity landed 2026-09-06)

### 8.1 Three IPSec tunnels (min)

```
SASE_Hub     type=dynamic (dial-up server), mode-cfg pool 10.10.x.1-252, network-id=1
             ↑ SPA spokes dial in here; ALL private-access flows over this tunnel
             ↑ BGP peers here via neighbor-group with RM_FABRIC_IN as route-map-in

BOR_Primary  type=ddns (client) → POP1_FQDN
BOR_Secondary type=ddns (client) → POP2_FQDN
             ↑ NEVER BGP; SDWAN members only, outbound SIA for local hub users
```

Dual-WAN SPA hub adds `BOR_Primary1`, `BOR_Primary2`, `BOR_Secondary1`, `BOR_Secondary2` = 5 tunnels total.

### 8.2 SDWAN service split

| Service | Priority-members | Purpose |
|---|---|---|
| Private-Access | `4` (SASE_Hub only) | Spoke-to-spoke + spoke-to-hub RFC1918 traffic via SPA fabric |
| INET_via_BOR | `1 2` (BOR tunnels) | Local hub-site users' outbound internet, SIA'd through SASE |
| Underlay_fallback | `3` (WAN port) | Last-resort direct-internet fallback |

Private-Access dst uses **three separate underscore-named address objects** (`RFC1918_10`, `RFC1918_172`, `RFC1918_192`) — different from spokes which use the Fortinet-built-in `RFC1918-GRP` single group. adom-init creates the 3 underscore objects at Phase 1 bootstrap.

### 8.3 BGP is 100% on `SASE_Hub` fabric

```
config router bgp
    config neighbor-group
        edit "SASE_Hub"
            set interface "SASE_Hub"
            set route-map-in "RM_FABRIC_IN"      ← the fabric demux
            set route-reflector-client enable
    config neighbor-range
        edit 1
            set prefix {{FABRIC_OVERLAY | net}} {{...mask}}
            set neighbor-group "SASE_Hub"
```

`RM_FABRIC_IN` uses 8 community-lists (`CL_ONRAMP_1..8`) plus `CL_ONRAMP_FAIL` to demux spoke-advertised communities into local-preference tiers (fixed canonical ladder: 200 stepping -5 for 8 slots + 50 for fail). This is the HUB-SIDE half of the spoke's `PRIMARY_POP` community-choice — spoke advertises with `CL_ONRAMP_k`, hub maps to matching LP.

---

## 9. Object Naming Reference (all layers)

| Layer | Pattern | Example |
|---|---|---|
| Meta vars | `SCREAMING_SNAKE_CASE` | `WAN_MODE`, `POP1_FQDN`, `PRIMARY_POP` |
| CLI templates | `BOR-{NN}-{PURPOSE}[-{platform-family}]` | `BOR-01-SYSTEM-GLOBAL`, `BOR-DUAL-08-BGP` |
| CLI template groups | `BOR-{ROLE}-STD[-{platform-family}]` | `BOR-SINGLE-STD`, `BOR-SPA-DUAL-STD-VM` |
| Policy packages | `BOR-{ROLE}-STD-PKG` | `BOR-SPOKE-STD-PKG`, `BOR-SPA-HUB-STD-PKG` |
| Blueprints | `BOR-{ROLE}-STD-{platform}` | `BOR-SINGLE-STD-VM`, `BOR-SPA-DUAL-STD-120G` |
| Device groups | `BOR_Branch_{Role}` | `BOR_Branch_Single`, `BOR_Branch_SPA_Hub` |
| Normalized interfaces | `{PURPOSE}_ZONE` | `LAN_ZONE`, `SDWAN_ZONE`, `Underlay_ZONE` |
| Devices | `[{platform-prefix}-]{purpose}-{site_id}` | `spoke-1` (VM), `30G-spoke-4`, `spa-hub-vm` |
| Rendered object names | LITERAL role | `BOR_Primary`, `HC_Secondary`, `RM_OUT_PRIMARY`, `CL_ONRAMP_1` |

**Template numbering reserved**: `BOR-01..BOR-19` for base spoke templates. `BOR-SPA-01..BOR-SPA-24` for SPA hub. `BOR-DUAL-*` for dual variants. Room for new roles.

---

## 10. FMG 7.6 Gotcha Catalog (24 gotchas, all with resolutions)

Every gotcha below cost hours on a real deployment. Each has a fix baked into the current tool + templates.

### Install / Zone / Namespace

**#1 — Blueprint auto-magic (port-provisioning: 1)** — `add-dev-list` with a `port-provisioning:1` blueprint auto-appends the device to blueprint's cliprofs group + pkg scope member. Explicit `auto_bind` binds become idempotent (report "nothing to add"). Do NOT remove — valuable when blueprint has different flags OR caller skips blueprint.

**#2 — `-10131 datasrc invalid. object: system zone`** — FMG validates `dynamic_mapping.local-intf` against device-DB zone tables. Fresh model devices have no zones. Fix: `pre_create_zone_shells` (default true).

**#3 — `-553 conflicts with a sdwan zone`** — FortiOS shares namespace between `system zone` and `system sdwan zone`. A `system zone SDWAN_ZONE` shell collides with SDWAN template's `system sdwan zone SDWAN_ZONE`. Fix: `zone_type` per normalized_interface. `LAN_ZONE` → `system`; `SDWAN_ZONE`, `Underlay_ZONE` → `sdwan`.

**#4 — `-10015 used` on zone shell delete** — dynamic_mapping or device-DB firewall policy holds a delete-lock. Fix: delete refs FIRST (dynamic_mapping children + orphaned device-DB firewall policies), THEN shell.

### Validation / Description

**#5 — `-9001` XSS on description parentheses** — FMG description validator rejects `()` and other punctuation. Fix: plain-text descriptions.

**#6 — `-9001` write-time on undeclared meta vars** — FMG validates every `{{ VAR }}` at template-create. Fix: bottom-up build order (meta vars → templates → groups → blueprint).

**#7 — `-9001` interfaces missing `set vdom` / `set type`** — FMG install-check stricter than FortiOS. VM model devices need `set vdom "root"` + `set type physical` in every interface edit; HW omits. Fix: `BOR-03-INTERFACES-VM` includes both; `BOR-03-INTERFACES-HW` doesn't.

**#8 — `-9001` admin missing accprofile** — Install-check requires `set accprofile` on admin edits. Fix: `BOR-01-SYSTEM-GLOBAL` includes `set accprofile "super_admin"`.

### Meta-var / Scope

**#9 — Meta var `_scope.vdom = "global"` NOT `"root"`** — ADOM meta vars aren't per-vdom. CSV imports handle automatically via `add-dev-list`. Direct API surgical updates: `/pm/config/adom/{a}/obj/fmg/variable/{VAR}/dynamic_mapping/{dev}/global`.

**#10 — Device group `object member` write-then-read** — FMG 7.6.7 accepts `set /dvmdb/adom/{a}/group/{g}/object member` (code=0) but no JSON-RPC readback. GUI reads via `flatui_proxy` with session cookie. Fix: tool returns `members_submitted` + `members_verified: null` + `verify_hint`.

**#11 — Device DELETE endpoint payload shape** — `/dvm/cmd/del/device` requires `data.device` as plain string, not array/dict. Direct `delete /dvmdb/adom/{a}/device/{name}` returns -9. Fix: `exec /dvm/cmd/del/device` with `data: {adom, device: <string>}`. `/dvm/cmd/del/dev-list` fails silently (-20002).

### Address / Datasource

**#12 — RFC1918 dash-vs-underscore naming** — Fortinet-built-in group is `RFC1918-GRP` (dash), individuals `RFC1918-10/172/192`. Custom underscore variants (`RFC1918_10/172/192`) need to be CREATED. Spokes use `RFC1918-GRP`; SPA hub uses the 3 underscore objects. Both coexist in the same ADOM. Fix: `bor-*` templates use dash; `bor-spa-*` templates use underscore; `adom-init` creates all 4 objects.

**#13 — Manifest FQDN address `<tenant>` XSS reject** — Manifest firewall_addresses that carried literal `ipsec-<tenant>-...` failed FMG XSS filter on create. Fix (2 layers): manifest addresses now use `$(POP1_FQDN)` FMG-var refs; pre-flight tenant-FQDN gate in adom-init refuses runs where a resolved POP*_FQDN still contains `<tenant>` placeholder.

**#14 — VLAN id error on `lan3` install** — 30G/50G/120G HW models have `internal` virtual-switch by default; interface template hitting `lan3` before purging virtual-switch triggers `-999 invalid value VLAN id must be between 1 and 4094`. Fix: prerun greenfield templates purge virtual-switch first; `BOR-03-INTERFACES-HW` includes `set type physical` + `set vdom "root"`.

**#15 — Health-check duplicate server IP** — 4 HCs using only 2 distinct server IPs (both `HC_Primary1/2` using POP1_PROBE, both `HC_Secondary1/2` using POP2_PROBE) triggers `entry "IP" duplicated within category "system sdwan health-check"`. Fix: `HC_Primary2` uses hardcoded 8.8.8.8, `HC_Secondary2` uses 8.8.4.4. 4 unique HC server IPs.

### Template Import

**#16 — SDWAN template import endpoint** — Cannot clone SDWAN via `method: clone`. Fix: `exec /pm/config/adom/{a}/_wanprof/import` with `data: {template, device: {name, vdom}, description}`.

**#17 — System template import endpoint** — Similar dedicated endpoint, different payload. Fix: `exec /pm/config/adom/{a}/_devprof/import` with `data: {device: <name-string>, devprof, description}`. Note: `device` is a plain STRING (not `{name, vdom}` dict).

### Route / Precedence

**#18 — BOR-07 route 10 (bastion) precedence** — Old order `MGMT_GATEWAY > WAN_MODE` caused DHCP-mode devices with MGMT_GATEWAY set to emit `set gateway <static>` → install fail off-subnet. Fix: `WAN_MODE=dhcp > MGMT_GATEWAY > WAN_GATEWAY` (fixed 2026-08-26).

**#19 — bor-single BOR-07 `MGMT_GATEWAY undefined`** — When CSV has blank `MGMT_GATEWAY`, `{% elif MGMT_GATEWAY %}` in the Jinja triggers UndefinedError at install-time. Fix: dropped the `elif MGMT_GATEWAY` branch entirely (WAN_MODE=dhcp → dynamic-gateway, else WAN_GATEWAY). MGMT_GATEWAY meta-var stays for the rare optional bastion/mgmt-gateway override case.

### Jinja Parser

**#20 — FMG Jinja doesn't propagate `{% set %}` across the config block** — Python Jinja2 accepts + propagates set-vars from a preamble into the config body. FMG's parser rejects references with "variable 'X' not exist" at install-preview time. Fix: use inline conditionals at every substitution instead of set-preamble + refs. Verified against every PRIMARY_POP template branch.

### FQDN / Tenant

**#21 — `<tenant>` placeholder XSS reject on greenfield adom-init** — Manifest defaults + tenant-config that still carry `<tenant>` (or any `<`/`>` char) fail FMG XSS filter with a cryptic message. Fix (2 layers): manifest fixed to use `$(POP1_FQDN)`/`$(POP2_FQDN)` FMG-var references; adom-init pre-flight `tenant_fqdn_gate()` refuses the run upfront with per-var actionable message ("enter your real FortiSASE BOR PoP FQDN before greenfield adom-init"). Not skippable.

### Template Naming Fidelity

**#22 — bor-*/bor-spa-single object-name drift (BOR_DFW instead of BOR_Primary)** — Templates rendered `edit "BOR_{{ POP1_NAME }}"` → tenant-identity names in device DB. Multi-tenant NOC hostile (operator has to memorize per-tenant PoP mappings). Fix (v1.1 for bor-single, v1.3 for bor-spa-single): all object names rendered as literal role strings (`BOR_Primary`, `HC_Secondary`, `RM_OUT_PRIMARY`, `BOR_Primary_PUBLIC`); `POP1_NAME`/`POP2_NAME` moved to `set comment` for display only. Naming-drift guard in validator prevents regression.

### Factory-Policy Collision (real-HW only)

**#23 — Factory `lan → wan` policy collides with sdwan-member validator on real HW** — Real FortiGate 30G/50G/120G ship from the factory with a firewall policy `srcintf=lan dstintf=wan action=accept`. That policy registers `wan` as a firewall-policy dstintf. When the SDWAN template renders `set interface "wan"` under `config system sdwan / config members`, FMG's install-check datasrc validator sees the dual registration and rejects with `datasrc invalid. object: system sdwan members.N:interface. detail: wan. reason: invalid value - prop[interface]: firewall policy dstintf`. VMs never hit this because their factory default uses `port1/port2` not `wan/lan`. Long-hidden by our matrix: we developed on VMs, hit the reject only when a real 30G was imported. Fix: `BOR-02-GREENFIELD-HW-SMALL` (which does `config firewall policy / purge`) must sit at **position 0** of every HW template group (`BOR-SINGLE-STD-HW`, `BOR-DUAL-STD-HW`, `BOR-SPA-SINGLE-STD-HW`, `BOR-SPA-DUAL-STD-HW`). The template exists in the manifest but for a long stretch was NOT bound into the group members list — that's the actual gap this fixed. The template is now idempotent (`edit "lan" / next / delete "lan"` guards against `Entry does not exist` on re-install after the address is already purged). Verified end-to-end 2026-09-09 on fresh FGT50GTK26048289 (real 50G, WAN_PORT=wan, never GUI-touched): install/device + install/package + install/device re-sync all green; SDWAN member 5 = wan / Underlay_ZONE clean.

### Optional Meta Vars

**#24 — Empty-string meta var is `undefined` to FMG's Jinja; `{% if VAR %}` raises** — FMG resolves a meta var whose effective value is the empty string (ADOM default `''`, or a per-device mapping of `''`) as *undefined*, and its Jinja raises `parse cli template fail: 'VAR' is undefined` on ANY reference, including the test expression of an `{% if %}`. Python Jinja2 would treat it as falsy and skip the block, so a template that renders fine offline fails at FMG install-preview. First hit on `HUB_LOOPBACK` (SPA hub, per-device, intentionally blank when the engineer doesn't want a loopback): `{% if HUB_LOOPBACK %}` failed on both the unmapped and the explicit-`''` device. Gotcha #19 (`MGMT_GATEWAY`) was the same mechanism seen earlier and solved by deleting the branch; this is the general fix. Rule: **guard every optional meta var with `{% if VAR is defined and VAR %}`**. Verified 2026-09-10 against FMG 7.6.7 on a throwaway SPA hub: `is defined and VAR`, `VAR | default('')`, and `VAR is defined` all parse and skip the block on blank; the `is defined and VAR` form is used because it reads as intent and also rejects a defined-but-empty value if FMG ever changes the empty-string semantics. The CSV importer skips blank cells (no per-device mapping is written), so the real-world path is the unmapped case. Applied to `BOR-SPA-20-LOOPBACK`, `BOR-SPA-23-BGP-RR` and their `BOR-SPA-DUAL-*` twins.

---

## 11. SDK Tool Reference

All tools live under `tools/`. Naming: `org.ulysses.noc.fortimanager-{purpose}`.

| Phase | Tool | Purpose | Latest ver |
|---|---|---|---|
| 1 | **`fortimanager-adom-init`** | Bootstrap greenfield ADOM (all Phase 1 objects) | 1.0.0 |
| 2 | **`fortimanager-model-device-import-csv`** | CSV → offline model device + auto-bind | 1.2.1 |
| 3 | **`fortimanager-install-push`** | Two-step install (device + auto-discovered pkg) | 1.1.0 |
| — | `metadata-create` / `metadata-set-adom` | Individual meta-var ops (adom-init uses these internally) | — |
| — | `cli-template-create` / `cli-template-group-create` | Individual template ops (adom-init uses internally) | — |
| — | `device-blueprint-create` | Individual blueprint ops (adom-init uses internally) | — |
| — | `device-group-create` | Individual device group ops | — |
| — | `template-clone-from-device` | Runtime → template capture (bgp/static/ipsec/sdwan/system presets) | 1.2.0 |
| — | `device-settings-install` | Device-scope install only (rarely needed; install-push is the general case) | 1.0.0 |
| — | `adom-list` | List ADOMs (used by Streamlit UI as connection canary) | 1.0.0 |

**Version pinning**: Always use SEMVER-latest in fresh deployments. Older versions kept for back-compat but lack the fixes documented in §10.

---

## 12. Troubleshooting Playbook

| Symptom | Likely cause | Diagnostic | Fix |
|---|---|---|---|
| `install-push` returns "Aborted due to previous error" | Real cause is upstream in task history | Read `line[].history[]` — walks first when task errors | Fix the upstream error surfaced in history |
| adom-init exits 3 with `[tenant-fqdn-gate] RED` | tenant-config missing or still has `<tenant>` placeholder FQDNs | Look at the per-var error message | Fill in real FortiSASE tenant FQDN in tenant-config |
| adom-init exits 2 with `[contract] RED` | Manifest drift from vendored contract | Read the drift messages | Re-vendor contract (byte-cp from App repo) OR fix the manifest |
| Naming-drift guard fires on a role | Template regressed to `{{ POP*_NAME }}` in an object-name context | Grep the role folder for `POP*_NAME` outside `#`/`set comment` | Rename to literal `Primary`/`Secondary` |
| Install task ends "num_err=1", history shows Jinja `X is undefined` | Meta var missing in ADOM OR blank in CSV | Check ADOM meta-var + CSV column | Add ADOM default OR fill CSV cell |
| Install task ends with `-131 datasrc invalid RFC1918_X` | SPA templates reference underscore addresses that don't exist | GET `/pm/config/adom/{a}/obj/firewall/address` | Re-run adom-init to create them |
| `-553 conflicts with a sdwan zone` at install | Naive pre-create used `system zone` for SDWAN-named zones | Compare `system zone` on failing device vs known-good | Use current csv-import (v1.2.1) with `zone_type: sdwan` |
| `-10131 datasrc invalid. object: system zone` at add-dynamic_mapping | Fresh device has no zone yet | Check `/pm/config/device/{d}/vdom/{v}/system/zone` | `pre_create_zone_shells: true` (default) |
| `devsnexist1|<SN>|devsnexist2 err=-10` at import | SN already registered somewhere in FMG | `get /dvmdb/device` search by SN | Delete or repurpose the existing device |
| Blueprint create fails `-10131` on cliprofs | Group doesn't exist (usually group create failed on description) | GET the group | Fix the group create first (plain-text description) |
| Group scope member append returns "nothing to add" | Blueprint's `port-provisioning:1` auto-scoped it already | Expected behavior — safe | No action needed |
| Device DB has 0 policies after "successful" install | install-push v1.0.0 (device-only, no pkg step) | Check tool version | Upgrade to install-push v1.1.0+ |

**Golden state reference**: `spoke-1` in `BOR_Customer_1` on the lab FMG. First fully-working device. Diff against it when something's broken.

---

## 13. Tenant Onboarding — Two Paths

### 13.1 Greenfield ADOM (partner has nothing) — recommended for new customers

```bash
# 1. Author tenant-config YAML with real FortiSASE tenant FQDNs
cp content/tenant-defaults.example.yaml my-customer.yaml
$EDITOR my-customer.yaml   # fill POP1_FQDN, POP2_FQDN, PoP names, etc.

# 2. Bootstrap the ADOM (pre-flights + all Phase 1 objects, ~30 sec)
python org.ulysses.noc.fortimanager-adom-init.py \
    --fmg-host <fmg> --adom BOR_Customer_MyCustomer \
    --tenant-config my-customer.yaml --create-adom

# 3. Import first site
python org.ulysses.noc.fortimanager-model-device-import-csv.py \
    --fmg-host <fmg> --adom BOR_Customer_MyCustomer \
    --csv-path <from-generator>.fmg.csv \
    --auto-bind ...  # see tool skills doc

# 4. Install
python org.ulysses.noc.fortimanager-install-push.py \
    --fmg-host <fmg> --adom BOR_Customer_MyCustomer \
    --device spoke-1
```

**Time**: ~2 minutes per new tenant + Phase 1. Phase 2+3 per site: ~1 minute wall-clock.

### 13.2 Clone Template ADOM (fast — reuses existing customer state)

Copy `BOR_Customer_1` → `BOR_Customer_N` via FMG GUI (Device Manager → ADOM → Clone). All Phase 1 objects come with. Update ADOM meta-var defaults for the new tenant, then proceed to Phase 2.

**Time**: ~15 minutes. Useful when Phase 1 has been customized with tenant-specific policy tweaks that would be lost in greenfield.

---

## 14. Live Reference Snapshot

As of 2026-09-06:

| ADOM | Purpose | Devices | Notes |
|---|---|---|---|
| `BOR_Customer_1` | Long-running template ADOM | spoke-1 (FGVMMLTM26000452, VM) | Golden state; first fully-working device |
| `BOR_Customer_10` | Multi-role test ADOM | (variable, cleared between test cycles) | Used for dual + SPA E2E |
| `BOR_Customer_V11_TEST` | v1.1/v1.2/v1.3 E2E validation | v11-spoke-1/2 + v12-30g/50g/120g-dual + v13-spa-hub-vm | Kept live for regression |

**Total Phase-1 objects per ADOM after adom-init**: ~292 (62 meta vars + 3 normalized interfaces + 41 CLI templates + 8 template groups + 10 addresses + 2 shapers + 2 pkgs + 16 blueprints + 3 device groups + ~145 platform_mapping entries).

---

## 15. Meta

**Cross-Claude coordination**: This SDK is one half of a two-repo pipeline. The other half is FortiSASE-SDK App (config generator + MSSP Deploy Streamlit page). Coordination happens through the `BOR-Role-Registry/` working folder (proposal, contract, role-spec templates) and byte-vendored `contract/roles-and-columns.yaml`. See the workflow's session commits — every push in a v1.1+/v1.2/v1.3 cycle was coordinated with the App side and byte-verified against generated reference `.conf` files before landing.

**Version history**:
- 2026-08-25 → 2026-08-26 initial workflow doc, 5 install-blocking FMG quirks (#2-#5, #14) fixed
- 2026-08-30 → 2026-09-01 bor-dual role added, 4 additional gotchas (#15, #18-#19) fixed, pkg consolidation
- 2026-09-01 install-push v1.1.0 (2-step install + history[]) shipped
- 2026-09-03 cross-Claude contract v1 shipped (BOR-Role-Registry pattern)
- 2026-09-04 contract v1.1 (PRIMARY_POP bor-single) + naming rename + drift guard (fixes gotcha #20, #22)
- 2026-09-05 contract v1.2 (PRIMARY_POP bor-dual)
- 2026-09-06 v1.3 SPA fidelity + gotcha #21 root-fix + tenant-FQDN gate

**Update this doc when**: You add a role, discover a new FMG quirk, bump a tool major version, or change contract shape.

---

*This doc lives in the FortiManager-AI-SDK repo. If you're an AI reading this cold, you now know the full three-tool pipeline, the four supported roles, the contract, the naming convention, and every documented gotcha with its fix. The next step is `adom-init --dry-run` against a lab FMG and reading its output alongside §2.*
