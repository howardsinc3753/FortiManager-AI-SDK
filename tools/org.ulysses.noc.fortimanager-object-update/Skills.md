# FortiManager Object Update — Skills

## How to Call

Use this tool when:
- An existing object needs a field changed (comment, color, status, subnet, etc.)
- Partial edits — only fields in `data` are modified, everything else preserved
- Clearing an attribute back to default (use `unset_attrs`)

**Example prompts:**
- "Change the comment on address `web-01` to 'Production'"
- "Disable the VIP `web-vip`"
- "Update policy 7 to deny instead of accept"
- "Clear the description field on address group `internal-servers`"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `url` | string | Yes | — | Named-entity URL (ending in the object name or ID) |
| `data` | object | Yes | — | Fields to change |
| `unset_attrs` | array | No | — | Attribute names to clear back to default |

## Examples

**Change address comment:**
```python
{
  "url": "/pm/config/adom/root/obj/firewall/address/web-01",
  "data": {"comment": "Production web server"}
}
```

**Disable a VIP:**
```python
{
  "url": "/pm/config/adom/root/obj/firewall/vip/web-vip",
  "data": {"status": "disable"}
}
```

**Flip policy action + add log:**
```python
{
  "url": "/pm/config/adom/root/pkg/howard-sdwan-spoke-1/firewall/policy/7",
  "data": {"action": "deny", "logtraffic": "all"}
}
```

**Clear an attribute (back to default):**
```python
{
  "url": "/pm/config/device/branch-01/global/system/interface/dmz",
  "unset_attrs": ["ip"]
}
```

## Interpreting Results

```json
{"success": true, "url": "/pm/config/adom/root/obj/firewall/address/web-01"}
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG {'code': -3, ...}` | Entity doesn't exist | Verify name, use list tool first |
| `FMG {'code': -10, ...}` | Invalid data | Check field names with `object-schema` |
| `FMG {'code': -6, ...}` | Invalid URL | Check URL; names with `/` need escaping (manual `\\/`) |
| `FMG {'code': -11, ...}` | No permission | Admin profile needs rpc-permit read-write |

## Pairs With

- `fortimanager-object-schema` — verify valid fields before updating
- `fortimanager-object-create` — for new objects (use overwrite=true for upsert)
- `fortimanager-object-delete` — if you want to remove instead of modify
