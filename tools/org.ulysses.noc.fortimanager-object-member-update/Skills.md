# FortiManager Object Member Update — Skills

## How to Call

Use this tool when:
- Modifying the member list of a group-type object (address group, VIP group, service group, internet-service group)
- Need atomic add / remove / clear without accidentally wiping other members
- Replaces using `object-update` on the whole group (which can trigger FMG's table-wipe gotcha)

**Example prompts:**
- "Add `web-01` to the `internal-servers` address group"
- "Remove `old-host` from `dmz-servers`"
- "Clear all members from address group `staging-hosts`"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `url` | string | Yes | — | URL ending in `/member` sub-path |
| `mode` | string | Yes | — | `add` / `remove` / `clear` |
| `members` | array | cond. | — | Member names (required for add/remove) |

## Examples

**Add members to address group:**
```python
{
  "url": "/pm/config/adom/root/obj/firewall/addrgrp/internal-servers/member",
  "mode": "add",
  "members": ["web-01", "db-01"]
}
```

**Remove a member:**
```python
{
  "url": "/pm/config/adom/root/obj/firewall/addrgrp/internal-servers/member",
  "mode": "remove",
  "members": ["old-host"]
}
```

**Clear all members:**
```python
{
  "url": "/pm/config/adom/root/obj/firewall/addrgrp/staging-hosts/member",
  "mode": "clear"
}
```

**Add members to service group:**
```python
{
  "url": "/pm/config/adom/root/obj/firewall/service/group/web-stack/member",
  "mode": "add",
  "members": ["HTTP", "HTTPS"]
}
```

## Interpreting Results

```json
{
  "success": true,
  "action": "add",
  "url": "/pm/config/adom/root/obj/firewall/addrgrp/internal-servers/member",
  "members_affected": ["web-01", "db-01"]
}
```

## Why This Tool Exists

FMG tables behave unusually on `set`: a `set` on the parent group with a new member list will REPLACE all members. This tool always uses `add` / `delete` / `unset` on the `/member` sub-path, which modifies incrementally without touching other members.

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `mode=add requires non-empty members` | Missing members array | Supply at least one name |
| `url must end with /member sub-path` | Wrong URL | Append `/member` to the group object URL |
| `FMG {'code': -3, ...}` (on remove) | Member not in group | Already removed; safe to ignore |
| `FMG {'code': -22, ...}` (on add) | Member already in group | Already there; idempotent |
| `FMG {'code': -6, ...}` | Invalid URL | Verify group exists + has /member sub |

## Pairs With

- `fortimanager-object-create` — create the group itself before adding members
- `fortimanager-field-datasrc` — see what can be added as a member
- `fortimanager-object-delete` — remove the whole group when done
