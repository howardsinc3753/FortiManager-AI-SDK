# FortiManager Device Settings Install — Skills

## How to Call

Use this tool when:
- Device-scoped config (interface, DNS, SNMP, system-global, static routes) changed and needs to be pushed to the device
- No policy changes are pending — policy-package-install would be overkill
- Partner AI just modified `pm/config/device/<dev>/global/...` and needs the device to reflect it

**Example prompts:**
- "Push device settings for howard-sdwan-spoke-1"
- "Install device settings on spoke-01 and spoke-02, wait for completion"
- "Apply the DNS change I just pushed to FMG"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | ADOM name |
| `scope` | array | Yes | — | `[{name, vdom}]` — targets to install to |
| `flags` | array | No | `["none"]` | FMG install flags |
| `dev_rev_comments` | string | No | `"Device settings installed via FortiManager AI SDK"` | Revision note |
| `wait` | boolean | No | `true` | Poll until terminal |
| `poll_interval_sec` | number | No | `3` | |
| `max_wait_sec` | integer | No | `300` | |

## Interpreting Results

```json
{
  "success": true,
  "task_id": 17,
  "adom": "root",
  "state": "done",
  "percent": 100,
  "num_err": 0,
  "num_done": 1,
  "num_lines": 1,
  "waited_sec": 8.4,
  "timed_out": false,
  "lines": [
    {
      "name": "howard-sdwan-spoke-1",
      "ip": "",
      "state": "done",
      "percent": 100,
      "detail": "install and save finished status=OK",
      "err": 0
    }
  ]
}
```

## Example

**User:** "Push device settings to howard-sdwan-spoke-1"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-device-settings-install/1.0.0",
    parameters={
        "fmg_host": "192.168.215.17",
        "scope": [{"name": "howard-sdwan-spoke-1", "vdom": "root"}]
    }
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG exec error: {'code': -11, ...}` | No perms | Elevate admin profile |
| `num_err > 0` | At least one device failed | Read `lines[].detail` — often device offline or FGFM disconnect |
| `timed_out: true` | Still running | Bump `max_wait_sec` or poll with `fortimanager-task-status` |

## Pairs With

- `fortimanager-policy-package-install` — if BOTH device and policy changes are pending, use that instead (it pushes device-settings too)
- `fortimanager-task-status` — re-poll if `wait=false`
- `fortimanager-device-list` — verify `conn_status=1` (up) before pushing
