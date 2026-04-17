# FortiManager Object Create — Skills

## How to Call

Use this tool when:
- Creating ANY FortiManager object — address, VIP, address group, service, schedule, etc.
- No dedicated per-type tool exists (this is the universal primitive)
- Idempotent flows — pair with `overwrite: true` to upsert

**Meta-workflow:** `object-schema` → `field-datasrc` → `object-create`.

**Example prompts:**
- "Create a VIP that maps 203.0.113.10 to 10.1.1.5 on port 443"
- "Add an address group `internal-servers` in root ADOM"
- "Create a custom service for Grafana on TCP port 3000"
- "Add a wildcard FQDN `*.internal.corp`"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `url` | string | Yes | — | Collection URL (not named-entity URL) |
| `data` | object | Yes | — | Object body. Include `name` for named tables. |
| `overwrite` | boolean | No | `false` | Upsert if exists |
| `as_list` | boolean | No | `false` | Wrap `data` in a list (rare FMG tables need this) |

## Examples

**VIP:**
```python
{
  "url": "/pm/config/adom/root/obj/firewall/vip",
  "data": {
    "name": "web-vip",
    "extintf": ["any"],
    "extip": ["203.0.113.10"],
    "mappedip": ["10.1.1.5"],
    "portforward": "enable",
    "protocol": "tcp",
    "extport": "443",
    "mappedport": "443",
    "status": "enable"
  }
}
```

**Address group:**
```python
{
  "url": "/pm/config/adom/root/obj/firewall/addrgrp",
  "data": {
    "name": "internal-servers",
    "member": ["web-01", "db-01"],
    "comment": "Internal server hosts"
  }
}
```

**Custom service:**
```python
{
  "url": "/pm/config/adom/root/obj/firewall/service/custom",
  "data": {
    "name": "Grafana",
    "protocol": "TCP/UDP/SCTP",
    "tcp-portrange": ["3000"]
  }
}
```

**Wildcard FQDN:**
```python
{
  "url": "/pm/config/adom/root/obj/firewall/wildcard-fqdn/custom",
  "data": {
    "name": "internal-corp",
    "wildcard-fqdn": "*.internal.corp"
  }
}
```

## Interpreting Results

```json
{"success": true, "action": "created", "url": "/pm/.../obj/firewall/vip", "name": "web-vip"}
```
- `action`: `created` (new) or `updated` (existed + overwrite=true)

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `already exists ... Set overwrite=true` | Pre-check found duplicate | Pass `overwrite: true` or pick a new name |
| `FMG {'code': -10, ...}` | Data invalid for URL | Check via `object-schema`; try `as_list: true` for rare tables |
| `FMG {'code': -6, ...}` | Invalid URL or permission denied | Verify URL syntax + rpc-permit read-write |
| `FMG {'code': -22, ...}` | Existence collision FMG detected (even past our pre-check) | Retry with `overwrite: true` |

## Pairs With

- `fortimanager-object-schema` — discover fields before calling
- `fortimanager-field-datasrc` — discover valid values for datasrc fields
- `fortimanager-object-update` — modify existing objects without recreating
- `fortimanager-object-delete` — remove objects
- `fortimanager-object-member-update` — manage group memberships separately
