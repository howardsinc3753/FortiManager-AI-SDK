# FortiManager ADOM Init — Skills

## How to Call

Use this tool when:
- Onboarding a new tenant to an FMG that has NEVER been touched by BOR-SASE tooling (greenfield ADOM)
- Rebuilding a tenant ADOM from scratch after a wipe or migration
- Standing up a test/lab ADOM identical to production
- Any partner using this SDK repo needs to reproduce the BOR-SASE state in their own FMG

Do **not** use for:
- Adding new sites to an existing tenant (use `model-device-import-csv` instead — this tool is Phase 1 only)
- Cloning between ADOMs on the same FMG (FMG GUI right-click "Clone ADOM" is faster)

## What it creates

This tool encodes **Phase 1** of the BOR-SASE deployment workflow. See `docs/BOR-SASE-DEPLOYMENT-WORKFLOW.md` for the full architecture.

| Object type | Count | Notes |
|---|---|---|
| Meta variables | 56 | 48 BOR spoke vars + 8 SPA hub fabric vars. Tenant defaults overridable via `--tenant-config`. |
| Normalized interfaces | 3 | `LAN_ZONE` (system zone), `SDWAN_ZONE` (sdwan zone), `Underlay_ZONE` (sdwan zone). Each gets 45 `platform_mapping` entries. |
| CLI templates | 22 | 12 spoke (`BOR-01..BOR-11` + platform variants) + 10 SPA hub (`BOR-SPA-01..24`). Scripts loaded from `content/templates/**/*.j2`. |
| Template groups | 4 | `BOR-SINGLE-STD` (VM spoke), `BOR-SINGLE-STD-HW` (HW spoke), `BOR-SPA-SINGLE-STD-VM` (VM hub), `BOR-SPA-SINGLE-STD-HW` (HW hub). |
| Firewall addresses | 3 | `LOCAL-LAN` (meta-var driven), `BOR_Primary_PUBLIC` + `BOR_Secondary_PUBLIC` (FQDN from tenant config). |
| Traffic shapers | 2 | `BOR_UP_SHAPER`, `BOR_DOWN_SHAPER` (100Mbps default). |
| Policy packages | 2 | `BOR-SINGLE-STD-PKG` (spoke, 3 policies), `BOR-SPA-SINGLE-STD-PKG` (hub, 5 policies including SDWAN-Hairpin). Both include a `BOR_OUTBOUND_SHAPER` shaping-policy. |
| Device blueprints | 8 | `BOR-SINGLE-STD-{VM,30G,50G,120G}` (spoke) + `BOR-SPA-SINGLE-STD-{VM,30G,50G,120G}` (hub). |
| DVMDB device groups | 3 | `BOR_Branch_Single`, `BOR_Branch_Dual`, `BOR_Branch_SPA_Hub`. |

**Idempotent** — safe to re-run. Uses `set` on named URLs (create-or-update). Collection adds tolerate `-2 already exists`.

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FortiManager hostname/IP |
| `adom` | string | Yes | — | Target ADOM name |
| `tenant_config` | string | No | *(uses manifest defaults)* | Path to a YAML file with tenant-specific meta var overrides. See `content/tenant-defaults.example.yaml` |
| `create_adom` | bool | No | `false` | Auto-create the ADOM if it doesn't exist (needs FMG admin privileges). Default: fail if missing |
| `dry_run` | bool | No | `false` | Print what would be done without calling FMG |

## Partner workflow — start-to-finish

```
                    ┌──────────────────────────────────────────────────┐
                    │  1. Partner clones this SDK repo                 │
                    │  2. Copy content/tenant-defaults.example.yaml    │
                    │     to my-tenant.yaml and fill in real values    │
                    │     (ADMIN_PASSWORD, SEED_PSK, POP FQDNs, etc.)  │
                    └────────────────────────┬─────────────────────────┘
                                             ↓
                    ┌──────────────────────────────────────────────────┐
                    │  3. Run this tool (Phase 1):                     │
                    │                                                   │
                    │  python .../org.ulysses.noc.fortimanager-\       │
                    │      adom-init.py \                              │
                    │      --fmg-host their-fmg.local \                │
                    │      --adom BOR_Customer_8 \                     │
                    │      --tenant-config my-tenant.yaml \            │
                    │      --create-adom                               │
                    │                                                   │
                    │  Output: 56 meta vars + 22 templates + 4 groups  │
                    │          + 8 blueprints + 3 device groups all    │
                    │          created. ADOM is READY for imports.     │
                    └────────────────────────┬─────────────────────────┘
                                             ↓
                    ┌──────────────────────────────────────────────────┐
                    │  4. SE fills config generator schema per site    │
                    │     → generator produces site-N.fmg.csv          │
                    │                                                   │
                    │  5. Run model-device-import-csv v1.2.1+ (Phase 2)│
                    │     with the CSV → device lands install-ready    │
                    │                                                   │
                    │  6. Install Wizard in FMG GUI → done             │
                    └──────────────────────────────────────────────────┘
```

## Example — first-time partner onboarding

```bash
# 1. Copy the example tenant config
cp content/tenant-defaults.example.yaml my-customer-8.yaml

# 2. Edit my-customer-8.yaml with real tenant values:
#    ADMIN_PASSWORD, SEED_PSK, POP1_FQDN, POP2_FQDN, etc.

# 3. Dry-run first to see what would happen
python org.ulysses.noc.fortimanager-adom-init.py \
    --fmg-host 192.168.1.100 \
    --adom BOR_Customer_8 \
    --tenant-config my-customer-8.yaml \
    --create-adom \
    --dry-run

# 4. Fire for real
python org.ulysses.noc.fortimanager-adom-init.py \
    --fmg-host 192.168.1.100 \
    --adom BOR_Customer_8 \
    --tenant-config my-customer-8.yaml \
    --create-adom
```

## Example — re-run to sync template updates

```bash
# After editing a .j2 template file, re-run to push changes to FMG
python org.ulysses.noc.fortimanager-adom-init.py \
    --fmg-host 192.168.1.100 \
    --adom BOR_Customer_1
# All templates are `set` (create-or-update); existing ones get their
# scripts refreshed with the new content.
```

## Where the truth lives

- **Templates**: `content/templates/bor-single/*.j2` and `content/templates/bor-spa-single/*.j2`. Edit these directly + re-run the tool to sync FMG.
- **Object definitions** (meta vars, groups, policies, blueprints, etc.): `content/adom-manifest.yaml`. Edit here to add/remove/modify objects.
- **Tenant defaults**: `content/tenant-defaults.example.yaml`. Copy per tenant; the copy becomes the input to `--tenant-config`.
- **Platform list**: `content/platform-list.yaml`. 45 FortiGate platforms mapped to the 3 normalized interfaces. Add more platforms here if you need to support new FortiGate models.

## Error handling

| Error | Cause | Fix |
|---|---|---|
| `ADOM 'X' does not exist` | Missing ADOM + `--create-adom` not set | Add `--create-adom` OR create ADOM in FMG GUI first |
| `code=-6 Invalid url` on pkg add | ADOM name typo | Verify `--adom` matches an ADOM (e.g. GET `/dvmdb/adom`) |
| `code=-9001 XSS` | Description or template body contains rejected chars (parens, `<>`) | Fix the offending template or manifest description; re-run |
| `code=-9001 value too long` on policy name | Policy name > 35 chars | Shorten in `adom-manifest.yaml` |
| Many `code=-2 already exists` messages | Re-run (idempotent) | Not an error; expected on re-runs |

## Pairs With

- **`model-device-import-csv v1.2.1+`** — Phase 2 of the workflow. Import per-site devices via CSV once this tool has bootstrapped the ADOM.
- **`device-group-create`** — for adding NEW device groups beyond the 3 defaults. This tool creates the base 3.
- **`metadata-create` / `cli-template-create` / etc.** — individual object tools for surgical additions. This tool is bulk-provision; individual tools are for targeted updates.

## Reference

- Full deployment workflow: `docs/BOR-SASE-DEPLOYMENT-WORKFLOW.md`
- FMG API quirks encoded here: see the workflow doc section 5 (there are 14 documented gotchas, all handled in this tool + `model-device-import-csv v1.2.1`)
