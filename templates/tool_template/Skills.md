# {{NAME}} — Skills

## How to Call

Use this tool when:
- <trigger condition 1>
- <trigger condition 2>
- <trigger condition 3>

**Example prompts:**
- "<example user request 1>"
- "<example user request 2>"
- "<example user request 3>"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP (credentials resolved from YAML) |
| `adom` | string | No | `root` | Administrative Domain |

## Interpreting Results

```json
{
  "success": true,
  "count": 1,
  "data": [
    {"name": "device-1", "ip": "10.1.1.1"}
  ]
}
```

**Field meanings:**
- `count`: Number of items returned
- `data`: Array of <describe items>

## Example

**User:** "<example user request>"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="{{CANONICAL_ID}}",
    parameters={"fmg_host": "192.168.215.17", "adom": "root"}
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG {'code': -11, ...}` | rpc-permit disabled on admin profile | `config system admin profile / edit <name> / set rpc-permit read-write` |
| `FMG {'code': -3, ...}` | Object does not exist | Verify the resource name/path |
| `No credentials found for <host>` | Missing entry in YAML | Add to `~/.config/mcp/fortimanager_credentials.yaml` |
