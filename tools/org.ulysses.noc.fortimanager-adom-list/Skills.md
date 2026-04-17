# FortiManager ADOM List — Skills

## How to Call

Use this tool when:
- User asks "what tenants/ADOMs does FortiManager have?"
- You need the tenant scope before listing devices, packages, or policies
- MSSP workflows that iterate over multiple customers
- Inventory/audit starting point

**Example prompts:**
- "List all ADOMs on my FortiManager"
- "Which tenants are managed on fmg-lab?"
- "Show me the root ADOM details"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP (credentials resolved from YAML) |
| `filter_state` | integer | No | — | 1 = normal/enabled, 2 = unknown |
| `name_like` | string | No | — | Case-insensitive substring match on ADOM name |

## Interpreting Results

```json
{
  "success": true,
  "count": 21,
  "adoms": [
    {"name": "root", "os_ver": "7", "mr": 6, "state": 1, "device_count": 1},
    {"name": "FortiWeb", "os_ver": "7", "mr": 6, "state": 1, "device_count": 0}
  ]
}
```

**Field meanings:**
- `os_ver` + `mr` = FortiOS major + minor (e.g. `7.6`)
- `state` = 1 means normal, 2 means unknown/degraded
- `device_count` = number of managed devices in this ADOM
- ADOMs with `device_count=0` are often product-template placeholders (FortiAuthenticator, FortiSandbox, etc.)

## Example

**User:** "List tenants on FortiManager 192.168.215.17"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-adom-list/1.0.0",
    parameters={"fmg_host": "192.168.215.17"}
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG {'code': -11, ...}` | rpc-permit disabled on admin profile | `config system admin profile / edit <profile> / set rpc-permit read-write` |
| `FMG {'code': -10, ...}` | Invalid/expired session or bad token | Verify `api_token` in fortimanager_credentials.yaml |
| `No credentials found for <host>` | Host missing from YAML | Add entry under `devices:` in `~/.config/mcp/fortimanager_credentials.yaml` |
| `FMG HTTP 401` | Token header rejected | Token may be revoked; regenerate from FMG GUI |
