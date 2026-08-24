# FortiManager Provisioning Template Create — Skills

## How to Call

Use this tool when:
- Creating the SHELL of any FMG 7.6 "Recommended Templates" family object (IPsec Tunnel, BGP, Static Route, SD-WAN Overlay, FortiAP settings)
- Standing up a fresh Branch OnRamp / SD-WAN spoke pipeline (System → CLI → IPsec → BGP → Static → SDWAN)
- Onboarding a new tenant — one call per template family, all through one tool

**Example prompts:**
- "Create an IPsec tunnel template called BRANCH_IPSEC_BASE in the BOR_Customer_1 ADOM"
- "Add a BGP template BRANCH_BGP_v1 in the tenant ADOM with a revision note"
- "Create a static route template STATIC_DEFAULT in BOR_Customer_1"
- "Dry-run: show me the payload for a new SD-WAN overlay template"

## Which stypes this tool covers

Only the **unified** `/pm/template/{stype}/adom/{adom}` endpoint family. In FMG 7.6.7 that means:

| Friendly name | Raw stype | GUI menu |
|---|---|---|
| `ipsec` / `ipsec-tunnel` / `vpn` | `_ipsec` | IPsec Tunnel Templates |
| `bgp` / `router-bgp` | `router_bgp` | BGP Templates |
| `static` / `static-route` | `_router_static` | Static Route Templates |
| `sdwan-overlay` / `overlay` | `_sdwan_overlay` | SD-WAN Overlay Templates *(new in 7.6)* |
| `fap` / `fortiap` / `wifi` | `_fap_setting` | Wireless Controller Templates |

**NOT covered by this tool** (use dedicated tools):
- System Template → `system-template-create` (endpoint: `/pm/devprof/adom/{adom}`)
- CLI Template → `cli-template-create` (endpoint: `/pm/config/adom/{adom}/obj/cli/template`)
- CLI Template Group → `cli-template-group-create` (endpoint: `/pm/config/adom/{adom}/obj/cli/template-group`)
- SD-WAN Template (classic) → `sdwan-template-create` (endpoint: `/pm/wanprof/adom/{adom}`)
- Certificate Template → generic `object-create` at `/pm/config/adom/{adom}/obj/certificate/template`

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | Yes | — | Target ADOM |
| `name` | string | Yes | — | Template name (unique per stype+adom) |
| `stype` | string | Yes | — | Friendly name (`ipsec`, `bgp`, …) or raw code (`_ipsec`, `router_bgp`, …) |
| `description` | string | No | `""` | Free-text description |
| `revision_note` | string | No | — | If set, appends a revision note via `/pm/config/adom/{adom}/_objrev/template/{stype}/{name}` |
| `overwrite` | boolean | No | `false` | If true and exists, **delete-and-recreate** (destructive — no in-place shell update) |
| `dry_run` | boolean | No | `false` | Return the payload without POSTing |

## Interpreting Results

**Created:**
```json
{
  "success": true,
  "action": "created",
  "name": "sdk-ipsec-tpl-test",
  "adom": "BOR_Customer_1",
  "stype": "ipsec",
  "stype_resolved": "_ipsec",
  "oid": 6507,
  "endpoint_used": "/pm/template/_ipsec/adom/BOR_Customer_1",
  "revision_added": true
}
```

**Already exists** (overwrite=false):
```json
{
  "success": false,
  "action": "already-exists",
  "name": "sdk-ipsec-tpl-test",
  "oid": 6507,
  "error": "Template 'sdk-ipsec-tpl-test' (stype='_ipsec') already exists in ADOM 'BOR_Customer_1' (oid=6507). Set overwrite=true to delete-and-recreate."
}
```

**Dry-run:**
```json
{
  "success": true,
  "action": "dry-run",
  "stype_resolved": "_ipsec",
  "endpoint_used": "/pm/template/_ipsec/adom/BOR_Customer_1",
  "payload_sent": {
    "url": "/pm/template/_ipsec/adom/BOR_Customer_1",
    "method": "add",
    "data": {
      "name": "…",
      "type": "template",
      "template setting": {"stype": "_ipsec", "widgets": ["_ipsec"], "option": null, "description": "…"}
    }
  }
}
```

## Example — full Branch OnRamp spoke template stack

```python
# 1. System Template (dedicated tool — devprof)
system_template_create({"fmg_host": "184.73.7.106", "adom": "BOR_Customer_1",
                        "name": "BOR-SYSTEM", "description": "hostname/DNS/NTP/syslog"})

# 2. CLI Templates for anything Jinja-driven (LAN interfaces, admin, etc.)
cli_template_create({"fmg_host": "184.73.7.106", "adom": "BOR_Customer_1",
                     "name": "BOR-LAN-INTF", "script": "config system interface\n  edit \"lan\"\n    …\nend\n"})

# 3. IPsec Tunnel Template (THIS tool)
provisioning_template_create({"fmg_host": "184.73.7.106", "adom": "BOR_Customer_1",
                              "name": "BOR-IPSEC", "stype": "ipsec",
                              "revision_note": "Branch OnRamp IPsec base"})

# 4. BGP Template (THIS tool)
provisioning_template_create({"fmg_host": "184.73.7.106", "adom": "BOR_Customer_1",
                              "name": "BOR-BGP", "stype": "bgp"})

# 5. Static Route Template (THIS tool)
provisioning_template_create({"fmg_host": "184.73.7.106", "adom": "BOR_Customer_1",
                              "name": "BOR-STATIC", "stype": "static-route"})

# 6. SDWAN Template shell (dedicated tool — wanprof)
sdwan_template_create({"fmg_host": "184.73.7.106", "adom": "BOR_Customer_1",
                       "name": "BOR-SDWAN", "status": "enable"})

# 7. CLI Template Group bundle (dedicated tool)
cli_template_group_create({"fmg_host": "184.73.7.106", "adom": "BOR_Customer_1",
                           "name": "BOR-CLI-GROUP",
                           "members": ["BOR-LAN-INTF"]})

# 8. Model Device with everything attached inline via blueprint
model_device_create({"fmg_host": "184.73.7.106", "adom": "BOR_Customer_1",
                     "name": "spoke-01", "sn": "FGT50GTK…", "platform": "FortiGate-50G",
                     "templates": ["BOR-CLI-GROUP"],
                     "meta_variables": {"SITE_ID": "1", "LAN_SUBNET": "10.1.0.0/24"}})
```

## Content Population (NOT covered by this tool)

This tool creates the **shell only**. Populating BGP neighbors, IPsec phase1/2, static routes, etc. happens via a follow-up per-stype `set` call with a stype-specific endpoint and payload:

| stype | Content-population endpoint | Payload shape |
|---|---|---|
| `_ipsec` | `set /pm/config/adom/{adom}/template/_ipsec/{name}/action-list/` | `data: [{action: "conf-ipsec-template", value: {vpn ipsec phase1-interface: {…}, vpn ipsec phase2-interface: […], system interface: {…}}, seq: 1}]` |
| `router_bgp` | `set /pm/config/adom/{adom}/template/router_bgp/{name}/router/bgp` | `data: {as, router-id, redistribute, neighbor: [{ip, remote-as, …}], …}` (direct BGP config) |
| `_router_static` | `set /pm/config/adom/{adom}/template/_router_static/{name}/router/static` | `data: [{seq-num, dst, gateway, device, …}]` |
| `_sdwan_overlay` | (varies — capture GUI curl to confirm) | — |
| `_fap_setting` | (varies — capture GUI curl to confirm) | — |

These are best handled by dedicated `-content-set` tools per stype, OR by generic `object-create` / `object-update`.

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG add error: {'code': -6, 'message': 'Invalid url'}` | The stype is not accepted by this FMG version at the unified endpoint | Confirm stype spelling; note some template families use their own dedicated URLs (see the "NOT covered by this tool" section above) |
| `FMG add error: {'code': -22, ...}` | Template with that name already exists (survived our pre-check) | Set `overwrite: true` — will delete + recreate |
| `already-exists` (action) | Template exists; not overwriting | Choose a new name OR set `overwrite: true` |
| `Overwrite requested but delete failed: FMG {...}` | Existing template couldn't be deleted (in use? locked?) | Check device/group bindings first; may need to unbind before delete |
| `FMG add error: {'code': -3, 'message': 'Object does not exist'}` | ADOM doesn't exist | Verify ADOM name with `adom-list` |

## Pairs With

- `metadata-create` — declare `$(VAR)` names before any template references them
- `object-list` — verify creation via `/pm/template/adom/{adom}` catalog
- `object-delete` — cleanup (via generic delete on `/pm/template/{stype}/adom/{adom}/{name}`)
- `template-bind-to-device` — post-create binding via `scope-member` (see the tool's own caveats)
- `model-device-create` — attaches templates through the device blueprint at create time (v2)
- `system-template-create`, `cli-template-create`, `cli-template-group-create`, `sdwan-template-create` — the legacy-family siblings
