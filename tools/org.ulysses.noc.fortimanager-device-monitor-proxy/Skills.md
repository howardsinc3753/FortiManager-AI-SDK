# FortiManager Device Monitor Proxy — Skills

## How to Call

Use this tool when:
- Need real-time FortiGate state (sessions, interfaces, routing, policy stats, CPU/memory) but don't have direct credentials on the device
- MSSP partner wants to check tenant health across many FortiGates using only FMG access
- Querying a FortiOS REST monitor endpoint the FMG-native API doesn't expose directly
- Building a multi-device dashboard — one proxy call with multiple `targets` fans out in a single round-trip

**This is the single highest-leverage tool in the SDK.** FortiManager broker unlocks every `/api/v2/monitor/*` endpoint on every managed device without per-device auth.

**Example prompts:**
- "Show me the interface status on howard-sdwan-spoke-1"
- "Get policy hit counts across all FortiGates in ADOM root"
- "Check the session count on the spoke right now"
- "Pull live BGP neighbor state from all SD-WAN spokes"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | (metadata only; targets are absolute paths) |
| `resource` | string | Yes | — | FortiGate REST path (must start `/api/v2/`) |
| `action` | string | No | `get` | `get` / `post` / `put` / `delete` |
| `targets` | array | Yes | — | FMG target path(s), e.g. `['/adom/root/device/<name>']` or `['/adom/root/group/All_FortiGate']` |
| `payload` | object | cond. | — | Body for POST/PUT |
| `timeout_sec` | integer | No | `30` | Hint to FMG for per-target timeout |

## Common Resources (FortiGate /api/v2/monitor)

| Resource | What it returns |
|---|---|
| `/api/v2/monitor/system/status` | Platform, version, serial, uptime |
| `/api/v2/monitor/system/interface` | Interface names, IPs, link state, speed |
| `/api/v2/monitor/system/available-interfaces` | Interfaces with IPv4 addresses (compact) |
| `/api/v2/monitor/system/resource/usage` | CPU, memory, sessions, conserve mode |
| `/api/v2/monitor/system/ha-checksums` | HA cluster checksum info |
| `/api/v2/monitor/firewall/session` | Session table |
| `/api/v2/monitor/firewall/policy` | Per-policy byte/packet counters |
| `/api/v2/monitor/router/ipv4` | Active routing table |
| `/api/v2/monitor/router/bgp/neighbors` | BGP neighbor states |
| `/api/v2/monitor/router/ospf/neighbors` | OSPF neighbor states |
| `/api/v2/monitor/vpn/ipsec` | IPsec tunnel status |
| `/api/v2/monitor/virtual-wan/health-check` | SD-WAN SLA health-check state |

## Target Path Forms

```
/adom/{adom}/device/{device-name}          # single device
/adom/{adom}/group/{device-group-name}     # all devices in a group
/adom/{adom}/device/{device-name}/vdom/{vdom}   # specific VDOM
```

## Interpreting Results

```json
{
  "success": true,
  "resource": "/api/v2/monitor/system/interface",
  "target_count": 1,
  "success_count": 1,
  "results": [
    {
      "target": "howard-sdwan-spoke-1",
      "success": true,
      "http_status": null,
      "response": {
        "serial": "FWF50...",
        "version": "v7.6.5",
        "status": "success",
        "results": [...interface details...]
      },
      "error": null
    }
  ]
}
```

## Example

**User:** "Show live interface status on howard-sdwan-spoke-1"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-device-monitor-proxy/1.0.0",
    parameters={
        "fmg_host": "192.168.215.17",
        "resource": "/api/v2/monitor/system/interface",
        "targets": ["/adom/root/device/howard-sdwan-spoke-1"]
    }
)
```

## Error Handling

| Symptom | Meaning | Fix |
|---|---|---|
| `results[].success=false, error="device-not-reachable"` | FMG can't reach the FortiGate | Check `fortimanager-device-list` — conn_status should be 1 |
| `results[].success=false, http_status=403` | Forbidden on FortiGate side | FortiGate profile blocks the endpoint |
| `FMG proxy error: {'code': -11, ...}` | FMG user lacks `sys/proxy/json` perm | Needs full `Super_User` profile + rpc-permit read-write |
| `Missing required parameter: resource` | Forgot the `/api/v2/...` path | Provide full REST path |

## Pairs With

- `fortimanager-device-list` — validate conn_status before proxying
- Any future wrapper tools that target a specific endpoint (e.g. `fortimanager-device-resource-usage`) can be built on top of this tool
