# QUICKSTART — Cold-start to first install in ~15 minutes

**Audience:** partner engineer receiving this SDK cold. You have an empty FortiManager and want to onboard your first BOR-SASE tenant end-to-end.

**Outcome:** a tenant ADOM with all templates, groups, blueprints, and policies pre-provisioned + one branch site imported and install-ready — all via two SDK tools, zero manual FMG GUI clicks.

---

## What you'll build

The BOR-SASE deployment model has two phases:

```
┌────────────────────────────────────────────────────────────────┐
│  PHASE 1 (once per tenant, ~30 seconds)                        │
│  fortimanager-adom-init                                        │
│    → 300 FMG objects bootstrapped in a fresh ADOM              │
│    → meta vars, normalized interfaces, CLI templates, groups,  │
│      firewall addresses, shapers, policy packages, blueprints, │
│      DVMDB device groups                                       │
└────────────────────────┬───────────────────────────────────────┘
                         ↓
┌────────────────────────────────────────────────────────────────┐
│  PHASE 2 (repeat per site, ~10 seconds each)                   │
│  model-device-import-csv                                       │
│    → one CSV row → device install-ready in FMG                 │
│    → auto-bind template group + policy pkg + device group      │
│    → auto pre-create zone shells + dynamic_mapping             │
└────────────────────────┬───────────────────────────────────────┘
                         ↓
┌────────────────────────────────────────────────────────────────┐
│  Install Wizard in FMG GUI  →  device dial-home  →  applied   │
└────────────────────────────────────────────────────────────────┘
```

**Roles supported today:** BOR-SINGLE spoke (1 WAN, 2 IPsec), BOR-SPA-SINGLE hub (SPA fabric for spoke-to-spoke), BOR-DUAL spoke (2 WAN, 4 IPsec cross-mesh), BOR-SPA-DUAL hub. Each × VM/30G/50G/120G. **16 role×platform combos, all install-verified.**

---

## Prerequisites

- **FortiManager 7.6+** (any edition) with admin access
- **Python 3.8+** on your workstation
- `pyyaml` (`pip install pyyaml`)
- Git

---

## Step 1: Clone the repo

```bash
git clone https://github.com/howardsinc3753/FortiManager-AI-SDK.git
cd FortiManager-AI-SDK
pip install pyyaml
```

---

## Step 2: Create an FMG API user + drop credentials

**In FMG GUI:** System Settings → Admin → Administrators → Create New:
- Name: `FMG_REST_API`
- Type: REST API Admin
- Admin Profile: Super_User (or a scope with ADOM edit rights)
- Trusted Hosts: your workstation IP

FMG will show a **Bearer token** — copy it now (only shown once).

**On your workstation:**
```bash
mkdir -p ~/.config/mcp   # Windows: C:\Users\<you>\.config\mcp
cat > ~/.config/mcp/fortimanager_credentials.yaml <<'EOF'
fortimanager:
  <your-fmg-hostname-or-ip>:
    api_token: <the-token-you-just-copied>
EOF
```

Test the connection:
```bash
python tools/org.ulysses.noc.fortimanager-adom-list/org.ulysses.noc.fortimanager-adom-list.py <fmg-host>
# → {"success": true, "adoms": [...]}
```

---

## Step 3: Prep the tenant config

```bash
cd tools/org.ulysses.noc.fortimanager-adom-init
cp content/tenant-defaults.example.yaml my-customer.yaml
```

**Edit `my-customer.yaml`** — override at minimum these 4 values:

| Key | Value | Where to get it |
|---|---|---|
| `ADMIN_PASSWORD` | Real admin password for this tenant's FortiGates | Your tenant admin policy |
| `SEED_PSK` | IPsec pre-shared key (customer-chosen) | Any strong secret; rotate per tenant |
| `POP1_FQDN` | Real BOR PoP FQDN | FortiSASE portal → Configuration → Network → BOR PoPs |
| `POP2_FQDN` | Real BOR PoP FQDN (secondary) | Same |

Everything else has safe defaults. See comments in the example for what each var controls.

---

## Step 4: PHASE 1 — Bootstrap the ADOM

**Dry-run first** (recommended — shows the plan without touching FMG):

```bash
python org.ulysses.noc.fortimanager-adom-init.py \
    --fmg-host <fmg-host> \
    --adom BOR_Customer_1 \
    --tenant-config my-customer.yaml \
    --create-adom \
    --dry-run
```

Expected: `~300 ops queued` across 10 stages (meta vars, normalized interfaces, CLI templates, groups, addresses, shapers, policy pkgs, blueprints, device groups).

**Fire for real:**

```bash
python org.ulysses.noc.fortimanager-adom-init.py \
    --fmg-host <fmg-host> \
    --adom BOR_Customer_1 \
    --tenant-config my-customer.yaml \
    --create-adom
```

Expected: `SUMMARY: OK: ~300, Failed: 0`. Takes ~30 seconds. Idempotent — safe to re-run.

**Verify in FMG GUI:** ADOM Manager should show `BOR_Customer_1`. Inside: Policy & Objects → CLI Templates should show 41 templates (22 single + 19 dual). Device Manager → Scripts → Device Blueprint should show 16 blueprints.

---

## Step 5: PHASE 2 — Import your first branch site

You need a per-site CSV. The companion **config-generator app** (in the `FortiSASE-SDK` repo, `automation/sdwan-ztp/config-generator/`) is a Streamlit UI where an SE fills the schema per site and clicks "Export FortiManager CSV".

For your first test, use one of the example CSVs shipped with the config-generator:
```
fmg-export/hardware-blueprints/{30G,50G,120G,VM}/STATIC-WAN-*.fmg.csv  (single-circuit spoke)
fmg-export/hardware-blueprints/SPA-Hub/{VM,30G,50G,120G}/STATIC-WAN-*.fmg.csv  (SPA hub)
fmg-export/hardware-blueprints/DUAL/{VM,30G,50G,120G}/STATIC-WAN-*.fmg.csv  (dual spoke)
fmg-export/hardware-blueprints/DUAL-SPA-Hub/{VM,30G,50G,120G}/STATIC-WAN-*.fmg.csv  (dual SPA hub)
```

**Override the placeholder SN with a real FortiFlex serial** (edit the first CSV cell) or leave a synthetic SN for offline model-device testing.

**Fire the importer:**

```bash
python tools/org.ulysses.noc.fortimanager-model-device-import-csv/org.ulysses.noc.fortimanager-model-device-import-csv.py \
    --fmg-host <fmg-host> \
    --adom BOR_Customer_1 \
    --csv-path /path/to/site-1.fmg.csv \
    --auto-bind '{
        "resolve_from_blueprint": true,
        "device_group": "BOR_Branch_Single",
        "normalized_interfaces": [
            {"name": "LAN_ZONE",      "zone_type": "system"},
            {"name": "SDWAN_ZONE",    "zone_type": "sdwan"},
            {"name": "Underlay_ZONE", "zone_type": "sdwan"}
        ]
    }'
```

**`device_group`** should be one of: `BOR_Branch_Single`, `BOR_Branch_Dual`, `BOR_Branch_SPA_Hub` — matching the role encoded in the CSV's `Device Blueprint` column.

Expected: `action: imported, task_state: done, devices_created: [...]`, all auto_bind ops `code=0`.

---

## Step 6: Install-test in FMG GUI

**Device Manager → BOR_Customer_1 → {device-name} → Install Wizard**

Expected: install-preview → install push → device dial-home → config applied.

If it errors, jump to Troubleshooting below.

---

## Troubleshooting quick reference

The gotchas we discovered during this SDK's build sessions — all now baked into the templates. If a partner hits any of these on a fresh FMG, the fix is in the repo. If you see something NEW, the pattern is: patch the .j2 file → re-run greenfield tool → retry install.

| Symptom | Cause | Fix (baked in) |
|---|---|---|
| `-131 datasrc invalid ... RFC1918` | Templates referenced custom RFC1918 objects that don't exist as Fortinet defaults | Templates now use `RFC1918-GRP` + `RFC1918-10/172/192` (dash, Fortinet defaults) |
| `-553 conflicts with a sdwan zone` on install | `pre_create_zone_shells` created SYSTEM zones for SDWAN-named zones | CSV importer `auto_bind.normalized_interfaces` takes `zone_type: system \| sdwan` — SDWAN_ZONE/Underlay_ZONE use `sdwan` |
| `-2 VLAN id must between 1-4094` on HW interface | FMG unaware `lan3` etc. is physical pre-prerun | HW interface templates explicitly `set vdom "root"` + `set type physical` |
| `MGMT_GATEWAY is undefined` in template render | Jinja strict on empty-string vars | Templates dropped `{% elif MGMT_GATEWAY %}` branches; bastion route uses `WAN_GATEWAY` |
| `duplicate ... within category system sdwan health-check` | Multiple HCs used same server IP | Templates use 4 unique probe IPs (Neustar + Google DNS) |
| `<tenant>` placeholder in POP FQDN meta var | Generator hasn't been given real tenant ID | Either: fix generator's tenant config, OR delete the per-device override so ADOM default (real FQDN) kicks in |

Full gotcha catalog with symptom → cause → fix: [`docs/BOR-SASE-DEPLOYMENT-WORKFLOW.md`](docs/BOR-SASE-DEPLOYMENT-WORKFLOW.md) §5.

---

## Onboarding a second (Customer_2) tenant

```bash
# Fresh tenant config
cp content/tenant-defaults.example.yaml my-customer-2.yaml
vim my-customer-2.yaml   # update ADMIN_PASSWORD, SEED_PSK, POP*_FQDN for new tenant

# New ADOM
python org.ulysses.noc.fortimanager-adom-init.py \
    --fmg-host <fmg-host> \
    --adom BOR_Customer_2 \
    --tenant-config my-customer-2.yaml \
    --create-adom
```

Same tool, same output shape — 300 objects in ~30 seconds. Different tenant defaults, same design.

---

## Adding a new role (for advanced users)

The greenfield tool auto-discovers subfolders in `content/templates/`. To add a new role:

1. Drop new `.j2` files into `content/templates/{new-role}/` (e.g. `bor-hub-cluster`)
2. Add entries to `content/adom-manifest.yaml`:
   - New meta vars (if the role needs them)
   - New template group referencing your new `.j2` filenames as `members`
   - New policy package if role needs different policies
   - New blueprints for each platform
   - New device group if role uses its own bucket
3. Re-run `fortimanager-adom-init` on any target ADOM — new objects added idempotently, existing untouched

**No orchestrator code changes needed.** The manifest IS the design.

---

## Where to go next

- **[docs/BOR-SASE-DEPLOYMENT-WORKFLOW.md](docs/BOR-SASE-DEPLOYMENT-WORKFLOW.md)** — full design manual (two-phase model, object naming, FMG API quirks, tools catalog, troubleshooting playbook)
- **[tools/org.ulysses.noc.fortimanager-adom-init/Skills.md](tools/org.ulysses.noc.fortimanager-adom-init/Skills.md)** — greenfield tool detailed usage
- **[tools/org.ulysses.noc.fortimanager-model-device-import-csv/Skills.md](tools/org.ulysses.noc.fortimanager-model-device-import-csv/Skills.md)** — CSV importer detailed usage
- **[tools/README.md](tools/README.md)** — full tool inventory (38 tools)
- **[NAMESPACE-FORK.md](NAMESPACE-FORK.md)** — how to fork the `org.ulysses.noc.*` namespace to your org

---

## Support

- SDK issues → GitHub Issues
- Design questions → the WORKFLOW doc first
- FMG API quirks → §5 of the WORKFLOW doc (all documented gotchas with fixes)
