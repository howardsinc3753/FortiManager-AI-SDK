# Playbook: Tenant SD-WAN Onboarding (FMG-Native, Model-Device-Based)

## Goal

End-to-end onboarding of a new MSSP tenant — create their ADOM, build a reusable SD-WAN Template, declare tenant-wide variables, place model devices (hubs + spokes) in FMG DVM, override per-site variables, push BGP-on-Loopback config, and stage install so that when the physical FortiGate phones home via FGFM, it pulls the full configuration automatically.

**Policy package authoring is DEFERRED to a separate playbook** — this one focuses on SDWAN hub/spoke standup via FMG Device Manager.

## Architecture

```
ADOM: Customer_101
 │
 ├── metadata variables (defaults)
 │     SITE_ID, LOOPBACK_IP, HUB1_LO, HUB2_LO, LAN_SUBNET,
 │     BGP_AS, TAG_RESOLVE_MODE=merge
 │
 ├── SDWAN Template      /pm/config/adom/Customer_101/obj/system/sdwan/
 │     ├── zone: SDWAN-HUB (advpn-select=1)
 │     ├── members: HUB1-VPN1 (seq=100), HUB2-VPN2 (seq=101), wan (seq=2)
 │     ├── health-check: HUB_Health (probes $(HUB1_LO)), Public_SLA (8.8.8.8)
 │     ├── service: default/voice/bulk steering rules
 │     └── neighbor: hub loopback w/ BGP + HUB_Health
 │
 └── Model Devices (placeholders until real HW arrives)
       ├── hub-01   (FortiGate-201F, SITE_ID=99, LOOPBACK_IP=10.200.1.1, Lo-HC=10.200.99.1)
       └── spoke-N  (FortiGate-60F,   SITE_ID=5,  LOOPBACK_IP=172.16.0.5, etc.)
             │
             └── per-device BGP config (NOT in devprof; direct at device-scope):
                   /pm/config/device/{name}/vdom/root/router/bgp
                     set tag-resolve-mode merge
                     set router-id $(LOOPBACK_IP)
                     route-maps: H1_TAG=1, H2_TAG=2, LAN_TAG=100, LAN_OUT(match-tag 100)
                   /pm/config/device/{name}/vdom/root/router/route-map/*
```

## When to Run

- Net-new MSSP customer onboarding
- Extending an existing customer with additional spokes (re-run Phase 5+ only)

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `fmg_host` | Yes | — | FortiManager IP/hostname |
| `adom` | Yes | — | New ADOM name (e.g. `Customer_101`) |
| `hub_loopback_primary` | Yes | — | Hub's primary BGP loopback (e.g. `10.200.1.1`) |
| `hub_loopback_hc` | No | `10.200.99.1` | Hub's health-check responder loopback |
| `bgp_as` | No | `65000` | iBGP AS number |
| `tag_resolve_mode` | No | `merge` | `disable` / `preferred` / `merge` / `merge-all` |
| `devices` | Yes | — | List of devices: `[{name, sn, platform, role: hub\|spoke, site_id, loopback_ip}]` |
| `dry_run` | No | `false` | Preview all operations without apply |

## Procedure

### Phase 0 — Preflight + ADOM Bootstrap

```python
# Check ADOM existence
adoms = adom-list({"fmg_host": fmg_host})
exists = any(a["name"] == adom for a in adoms["adoms"])

if not exists:
    object-create({
        "url": "/dvmdb/adom",
        "data": {
            "name": adom,
            "os_ver": 7, "mr": 6,
            "restricted_prds": ["fos"],
            "mig_mr": 6, "mig_os_ver": 7
        }
    })
```

### Phase 1 — Tenant Variables

```python
tenant_vars = [
    ("LOOPBACK_IP",      "172.16.0.0"),
    ("HUB1_LO",          hub_loopback_primary),
    ("HUB2_LO",          "10.200.1.2"),     # override per tenant if dual-hub
    ("HUB_LO_HC",        hub_loopback_hc),
    ("LAN_SUBNET",       "10.0.0.0/24"),
    ("BGP_AS",           str(bgp_as)),
    ("TAG_RESOLVE_MODE", tag_resolve_mode),
    ("SITE_ID",          "0"),
]
for name, default in tenant_vars:
    metadata-create({"fmg_host": fmg_host, "adom": adom,
                     "name": name, "default_value": default})
```

### Phase 2 — SDWAN Template

URL base: `/pm/config/adom/{adom}/obj/system/sdwan/`

**Zone**:
```python
object-create({
    "url": f"/pm/config/adom/{adom}/obj/system/sdwan/zone",
    "data": {"name": "SDWAN-HUB", "advpn-select": 1,
             "advpn-health-check": ["HUB_Health"],
             "service-sla-tie-break": 1,
             "minimum-sla-meet-members": 1}
})
```

**Members** (overlays use `$(LOOPBACK_IP)` — FMG substitutes at install):
```python
# HUB1 overlay
object-create({"url": f"/pm/config/adom/{adom}/obj/system/sdwan/members",
    "data": {"seq-num": 100, "interface": ["HUB1-VPN1"],
             "source": "$(LOOPBACK_IP)", "zone": ["SDWAN-HUB"],
             "priority-in-sla": 10, "priority-out-sla": 20, "status": 1}})
# HUB2 overlay  
object-create({"url": f"/pm/config/adom/{adom}/obj/system/sdwan/members",
    "data": {"seq-num": 101, "interface": ["HUB2-VPN2"],
             "source": "$(LOOPBACK_IP)", "zone": ["SDWAN-HUB"],
             "priority-in-sla": 10, "priority-out-sla": 20, "status": 1}})
# wan direct breakout
object-create({"url": f"/pm/config/adom/{adom}/obj/system/sdwan/members",
    "data": {"seq-num": 2, "interface": ["wan"],
             "zone": ["SDWAN-HUB"], "status": 1}})
```

**Health-checks**:
```python
object-create({"url": f"/pm/config/adom/{adom}/obj/system/sdwan/health-check",
    "data": {"name": "HUB_Health", "server": ["$(HUB_LO_HC)"],
             "members": ["100", "101"], "protocol": 1,
             "interval": 500, "probe-timeout": 500, "failtime": 5, "recoverytime": 5,
             "embed-measured-health": 1,
             "sla": [{"id": 1, "latency-threshold": 200,
                      "jitter-threshold": 50, "packetloss-threshold": 5}]}})

object-create({"url": f"/pm/config/adom/{adom}/obj/system/sdwan/health-check",
    "data": {"name": "Public_SLA", "server": ["8.8.8.8", "4.2.2.2"],
             "members": ["2"], "protocol": 1,
             "interval": 500, "probe-timeout": 500,
             "sla": [{"id": 1, "latency-threshold": 5,
                      "jitter-threshold": 5, "packetloss-threshold": 0}]}})
```

**Services** (steering rules — minimal set):
```python
# Default: internet traffic follows hub unless SLA violated
object-create({"url": f"/pm/config/adom/{adom}/obj/system/sdwan/service",
    "data": {"name": "DEFAULT", "id": 1, "mode": 3,
             "health-check": ["Public_SLA"],
             "priority-members": ["100", "101", "2"],
             "dst": ["all"], "src": ["all"]}})
```

**Neighbor** (ADVPN):
```python
object-create({"url": f"/pm/config/adom/{adom}/obj/system/sdwan/neighbor",
    "data": {"ip": ["$(HUB1_LO)"],
             "member": ["100", "101"],
             "health-check": ["HUB_Health"],
             "minimum-sla-meet-members": 1,
             "mode": 1, "role": 3}})
```

### Phase 3 — Model Devices (per device in input list)

For each `device` entry in `devices`:

```python
# Create model device
r = fortimanager-model-device-create({
    "fmg_host": fmg_host, "adom": adom,
    "name": device["name"], "sn": device["sn"],
    "platform": device["platform"],
    "description": f"Model device for site {device['site_id']} ({device['role']})"
})

# Per-device variable overrides
metadata-set-device({
    "fmg_host": fmg_host, "adom": adom, "name": "SITE_ID",
    "mappings": [{"device": device["name"], "vdom": "global",
                  "value": str(device["site_id"])}]
})
metadata-set-device({
    "fmg_host": fmg_host, "adom": adom, "name": "LOOPBACK_IP",
    "mappings": [{"device": device["name"], "vdom": "global",
                  "value": device["loopback_ip"]}]
})
```

### Phase 4 — Per-Device BGP-on-Loopback Config

Devprof can't hold BGP/route-map — must configure at device-scope for each device. This is done against `/pm/config/device/{name}/vdom/root/router/*`.

Per corpus Jinja (release/7.6/dynamic-bgp-on-lo/03-Edge-Routing.j2):

**Route-maps** (H1_TAG, H2_TAG, LAN_TAG, LAN_OUT):
```python
for rm_name, tag in [("H1_TAG", 1), ("H2_TAG", 2), ("LAN_TAG", 100)]:
    object-create({
        "url": f"/pm/config/device/{dev_name}/vdom/root/router/route-map",
        "data": {"name": rm_name,
                 "rule": [{"id": 1, "set-tag": tag}]}
    })
# LAN_OUT uses match-tag for selective re-export
object-create({
    "url": f"/pm/config/device/{dev_name}/vdom/root/router/route-map",
    "data": {"name": "LAN_OUT",
             "rule": [{"id": 1, "match-tag": 100}]}
})
```

**BGP** (global + neighbors):
```python
# Global BGP setup with tag-resolve-mode
object-update({
    "url": f"/pm/config/device/{dev_name}/vdom/root/router/bgp",
    "data": {
        "as": int(bgp_as),
        "router-id": "$(LOOPBACK_IP)",
        "keepalive-timer": 15, "holdtime-timer": 45,
        "ibgp-multipath": "enable",
        "recursive-next-hop": "enable",
        "tag-resolve-mode": tag_resolve_mode,   # merge
        "graceful-restart": "enable"
    }
})

# Hub neighbor(s) with per-hub route-map-in for tag stickiness
object-create({
    "url": f"/pm/config/device/{dev_name}/vdom/root/router/bgp/neighbor",
    "data": {
        "ip": "$(HUB1_LO)",
        "remote-as": int(bgp_as),
        "interface": "Lo", "update-source": "Lo",
        "route-map-in": "H1_TAG",
        "soft-reconfiguration": "enable",
        "capability-graceful-restart": "enable"
    }
})
object-create({
    "url": f"/pm/config/device/{dev_name}/vdom/root/router/bgp/neighbor",
    "data": {"ip": "$(HUB2_LO)", "remote-as": int(bgp_as),
             "interface": "Lo", "update-source": "Lo",
             "route-map-in": "H2_TAG",
             "soft-reconfiguration": "enable"}
})

# Network advertisement for LAN with LAN_TAG
object-create({
    "url": f"/pm/config/device/{dev_name}/vdom/root/router/bgp/network",
    "data": {"id": 110, "prefix": "$(LAN_SUBNET)",
             "route-map": "LAN_TAG"}
})
```

**Loopback interface** (spoke identity):
```python
object-create({
    "url": f"/pm/config/device/{dev_name}/global/system/interface",
    "data": {"name": "Lo", "type": "loopback",
             "ip": "$(LOOPBACK_IP) 255.255.255.255",
             "allowaccess": "ping"}
})
```

### Phase 5 — Assign SDWAN Template to Devices

```python
# Using exec /securityconsole/assign/objs
body = {
    "method": "exec",
    "params": [{
        "url": "/securityconsole/assign/objs",
        "data": {
            "adom": adom,
            "scope": [{"name": dev["name"], "vdom": "root"} for dev in devices],
            "target": [{"name": dev["name"], "vdom": "root"} for dev in devices],
            "flags": ["none"]
        }
    }]
}
```

(Exact category number for SDWAN template TBD — probe next; fallback: assignment happens automatically when the ADOM-scope SDWAN template is pushed via `device-settings-install`.)

### Phase 6 — Stage Install

```python
device-settings-install({
    "fmg_host": fmg_host, "adom": adom,
    "scope": [{"name": d["name"], "vdom": "root"} for d in devices],
    "wait": True,
    "dev_rev_comments": f"Tenant {adom} onboarding — staged pre-phone-home"
})
```

Install to model devices stages the config on FMG side. When the real FortiGate phones home via FGFM with the matching serial, FMG delivers the config.

### Phase 7 — Verify (runs when real device online)

```python
for dev in devices:
    audit = run_playbook("sdwan-config-audit", {
        "fmg_host": fmg_host, "adom": adom, "device": dev["name"]
    })
    health = run_playbook("sdwan-health-check", {
        "fmg_host": fmg_host, "adom": adom, "device": dev["name"]
    })
```

## Output

```json
{
  "success": true,
  "adom": "Customer_101",
  "adom_created": true,
  "template_objects_created": {"zones": 1, "members": 3, "health_checks": 2, "services": 1, "neighbors": 1},
  "model_devices": [
    {"name": "spoke-05", "oid": 190, "site_id": 5, "loopback": "172.16.0.5"},
    {"name": "spoke-06", "oid": 191, "site_id": 6, "loopback": "172.16.0.6"}
  ],
  "install_task_id": 95,
  "audit_results": [
    {"device": "spoke-05", "grade": "B"}
  ]
}
```

## Dry-Run Mode

When `dry_run: true`:
- Skip all `object-create` / `object-update` / `model-device-create` / `device-settings-install` calls
- Emit a preview document showing every operation + payload
- Useful for customer review before applying

## Failure Modes

| Symptom | Action |
|---|---|
| ADOM already exists | Skip Phase 0, continue to Phase 1 (idempotent). Fail if templates already exist there. |
| Model device create fails with `-20084` | VM platform — switch to HW platform or apply FortiFlex entitlement |
| Phase 4 BGP config fails | Check loopback interface exists first (Phase 4's own sub-step) |
| device-settings-install task num_err > 0 | Inspect `task-status` lines for per-device failure reason |
| Verify audit Grade < B | Don't roll back — surface findings to human |

## Tools Used

Existing: `adom-list`, `object-create`, `object-update`, `object-list`, `metadata-create`, `metadata-set-device`, `device-settings-install`, `task-status`

New: `fortimanager-model-device-create` (this session)

Playbooks called: `sdwan-config-audit`, `sdwan-health-check`

## Deferred

- **Policy package authoring** — separate playbook
- **Category number for `/securityconsole/assign/objs`** — may require probe
- **CLI template (`/pm/devprof`)** — not used here; devprof is for FAZ/syslog, not BGP
- **FortiZTP integration** — out of scope

## Related

- `playbooks/sdwan-config-audit.md` — run post-install
- `playbooks/sdwan-health-check.md` — live + historical verification
- `playbooks/sdwan-spoke-onboard.md` — per-device direct (not template-based) onboarding
