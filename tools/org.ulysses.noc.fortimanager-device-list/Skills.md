# FortiManager Device List — Skills

## How to Call

Use this tool when:
- User asks to see all FortiGates managed by a specific FortiManager
- Fleet inventory is needed before deeper per-device work
- Triaging which devices are offline or out-of-sync
- MSSP wants to filter devices by model or hostname across tenants

**Example prompts:**
- "Show me all FortiGates in the root ADOM"
- "Which devices are down on fmg-lab?"
- "List all 60F devices in tenant ADOM_A_76"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | Administrative Domain |
| `name_like` | string | No | — | Case-insensitive substring match on device name |
| `platform_like` | string | No | — | Case-insensitive substring match on platform (e.g. "60F") |
| `only_down` | boolean | No | `false` | Return only devices whose `conn_status != 1` |

## Interpreting Results

```json
{
  "success": true,
  "count": 1,
  "devices": [
    {
      "name": "howard-sdwan-spoke-1",
      "hostname": "howard-sdwan-spoke-1",
      "ip": "10.250.250.1",
      "platform": "FortiWiFi-50G-5G",
      "os_version": "7.6.5",
      "build": 3651,
      "ha_mode": 0,
      "conn_status": 2,
      "conn_status_label": "down",
      "conf_status": 1,
      "mgt_vdom": "root",
      "description": ""
    }
  ]
}
```

**Field meanings:**
- `conn_status`: 0=unknown, 1=up, 2=down — `conn_status_label` gives the string form
- `conf_status`: 1 = synced, other values indicate modified/out-of-sync
- `ha_mode`: 0 = standalone, non-zero = HA cluster member
- `os_version`: concatenated `os_ver.mr.patch`
- `mgt_vdom`: management VDOM on the device

## Example

**User:** "Show me all FortiGates in tenant root that are currently offline"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-device-list/1.0.0",
    parameters={"fmg_host": "192.168.215.17", "adom": "root", "only_down": true}
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG {'code': -11, ...}` | rpc-permit disabled on admin profile for dvmdb | `config system admin profile / edit <name> / set rpc-permit read-write` |
| `FMG {'code': -3, ...}` | ADOM does not exist | Check spelling; use `fortimanager-adom-list` to enumerate |
| `FMG {'code': -6, ...}` | Invalid URL | Usually means the ADOM name has special characters; URL-encode |
| `No credentials found for <host>` | Missing entry in YAML | Add to `~/.config/mcp/fortimanager_credentials.yaml` |
