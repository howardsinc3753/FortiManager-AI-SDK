# FortiManager Firewall Address List — Skills

## How to Call

Use this tool when:
- Enumerating address objects before authoring a policy that references them
- Auditing which addresses exist in a tenant ADOM
- Finding duplicates (similar names / same subnet)
- Preparing a migration report

**Example prompts:**
- "List all firewall addresses in the root ADOM"
- "Show me FQDN addresses in tenant ADOM_A_76"
- "Which addresses start with 'RFC1918' in the root ADOM?"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | ADOM name |
| `name_like` | string | No | — | Case-insensitive substring match on name |
| `type_filter` | string | No | `any` | `any`, `ipmask`, `iprange`, `fqdn`, `geography`, `dynamic` |
| `offset` | integer | No | `0` | Pagination offset |
| `limit` | integer | No | `200` | Max records returned |

## Interpreting Results

```json
{
  "success": true,
  "count": 8,
  "adom": "root",
  "addresses": [
    {
      "name": "RFC1918-10",
      "type": 0,
      "type_label": "ipmask",
      "subnet": ["10.0.0.0", "255.0.0.0"],
      "start_ip": "0.0.0.0",
      "end_ip": "0.0.0.0",
      "fqdn": "",
      "associated_interface": [],
      "color": 0,
      "comment": "",
      "uuid": ""
    }
  ]
}
```

**Type mapping:**
- `0` ipmask, `1` iprange, `2` fqdn, `3` wildcard, `6` wildcard-fqdn, `7` geography, `10` mac, `15` dynamic

**Field meanings:**
- `subnet[0]` is network, `subnet[1]` is netmask
- `start_ip` / `end_ip` populated only for `iprange` type (others show "0.0.0.0")
- `fqdn` populated only for `fqdn` / `wildcard-fqdn` types
- `associated_interface[]` restricts the address to be used on specific interfaces; empty = any

## Example

**User:** "List all FQDN addresses in the root ADOM"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-firewall-address-list/1.0.0",
    parameters={"fmg_host": "192.168.215.17", "adom": "root", "type_filter": "fqdn"}
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG {'code': -3, ...}` | ADOM does not exist | Run `fortimanager-adom-list` to confirm |
| `FMG {'code': -11, ...}` | No permission | User needs `rpc-permit read-write` |
| `Invalid type_filter` | Bad enum value | Use one of the supported labels |

## Pairs With

- `fortimanager-firewall-address-create` — create new addresses
- `fortimanager-policy-list` / `fortimanager-policy-create` — reference these addresses
