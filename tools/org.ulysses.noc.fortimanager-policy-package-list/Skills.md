# FortiManager Policy Package List — Skills

## How to Call

Use this tool when:
- User wants to see what policy packages exist in a tenant/ADOM
- You need the package name before listing individual policies or installing a package
- Auditing which ADOMs have which firewall package layouts
- Confirming NAT mode (central-nat) or NGFW mode settings on a package

**Example prompts:**
- "List policy packages in the root ADOM"
- "Which packages are in tenant ADOM_A_76?"
- "Show me all folders and packages under FortiFirewall ADOM"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | Administrative Domain |
| `name_like` | string | No | — | Case-insensitive substring match on package name |
| `include_folders` | boolean | No | `true` | Include `type: folder` entries (nested containers) |

## Interpreting Results

```json
{
  "success": true,
  "count": 1,
  "packages": [
    {
      "name": "default",
      "type": "pkg",
      "oid": 5970,
      "obj_version": 1,
      "central_nat": 0,
      "ngfw_mode": 0,
      "consolidated_firewall_mode": 0,
      "implicit_log": 0
    }
  ]
}
```

**Field meanings:**
- `type`: `pkg` = actual package, `folder` = container holding nested packages
- `central_nat`: 0 = interface-based NAT (legacy), 1 = central NAT table
- `ngfw_mode`: 0 = profile-based, 1 = policy-based
- `consolidated_firewall_mode`: 1 = IPv4/IPv6 policies consolidated into single table
- `implicit_log`: 1 = implicit deny policy logs denied traffic

## Example

**User:** "What policy packages does ADOM_A_76 have?"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-policy-package-list/1.0.0",
    parameters={"fmg_host": "192.168.215.17", "adom": "ADOM_A_76"}
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG {'code': -11, ...}` | rpc-permit disabled for pm/pkg | `config system admin profile / edit <name> / set rpc-permit read-write` |
| `FMG {'code': -3, ...}` | ADOM does not exist | Check with `fortimanager-adom-list` |
| `FMG {'code': -6, ...}` | Invalid URL | Special chars in ADOM name — URL-encode |
| `No credentials found for <host>` | Missing entry in YAML | Add to `~/.config/mcp/fortimanager_credentials.yaml` |
