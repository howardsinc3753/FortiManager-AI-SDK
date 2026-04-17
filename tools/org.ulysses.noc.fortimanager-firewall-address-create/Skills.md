# FortiManager Firewall Address Create — Skills

## How to Call

Use this tool when:
- Authoring policies that need a new host/subnet/FQDN object
- Scripted onboarding creates tenant-specific address objects
- Partner AI is building addresses before creating a policy
- Idempotent automation (use `overwrite: true`)

**Example prompts:**
- "Add a host address `web-01` for 10.1.1.5 in the root ADOM"
- "Create an IP range address `dhcp-pool` from 10.5.0.10 to 10.5.0.200"
- "Add an FQDN object `updates.example.com`"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | ADOM name |
| `name` | string | Yes | — | Object name |
| `type` | string | Yes | — | `ipmask` / `iprange` / `fqdn` |
| `subnet` | string | cond. | — | Required if `type=ipmask`. CIDR or `ip mask` |
| `start_ip` | string | cond. | — | Required if `type=iprange` |
| `end_ip` | string | cond. | — | Required if `type=iprange` |
| `fqdn` | string | cond. | — | Required if `type=fqdn` |
| `associated_interface` | array | No | — | Restrict to specific interface(s) |
| `comment` | string | No | "" | Description (max 255) |
| `color` | integer | No | 0 | Icon color 1-32 |
| `overwrite` | boolean | No | `false` | Update if exists |

## Interpreting Results

### Created
```json
{"success": true, "action": "created", "name": "web-01", "adom": "root", "type": "ipmask"}
```

### Updated (overwrite=true)
```json
{"success": true, "action": "updated", "name": "web-01", "adom": "root", "type": "ipmask"}
```

### Already exists (overwrite=false)
```json
{"success": false, "action": "noop", "error": "Address 'web-01' already exists in ADOM 'root'. Set overwrite=true to update."}
```

## Examples

**ipmask (host):**
```python
{"name": "web-01", "type": "ipmask", "subnet": "10.1.1.5/32"}
```

**ipmask (subnet):**
```python
{"name": "dmz-net", "type": "ipmask", "subnet": "10.10.0.0/24"}
```

**iprange:**
```python
{"name": "dhcp-pool", "type": "iprange", "start_ip": "10.5.0.10", "end_ip": "10.5.0.200"}
```

**fqdn:**
```python
{"name": "ms-update", "type": "fqdn", "fqdn": "update.microsoft.com"}
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `type=ipmask requires 'subnet'` | Missing required arg | Provide CIDR or ip+mask |
| `Invalid subnet: ...` | Malformed CIDR | Use `10.1.1.0/24` format |
| `end_ip must be >= start_ip` | IP range reversed | Swap values |
| `FMG {'code': -22, ...}` | Already exists (FMG-level collision even after our check) | Use `overwrite: true` |
| `FMG {'code': -10, ...}` | Data invalid for selected URL | Check type-specific required fields |
| `FMG {'code': -3, ...}` | ADOM not found | Verify via `fortimanager-adom-list` |

## Pairs With

- `fortimanager-firewall-address-list` — check what exists before creating
- `fortimanager-policy-create` — reference the new address in rule srcaddr/dstaddr
