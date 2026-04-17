# FortiManager Policy Package Install — Skills

## How to Call

Use this tool when:
- New or modified policies exist in FMG that need to be pushed to managed FortiGates
- End of an automation workflow: create addresses → create policies → **install** (this tool)
- Partner AI is closing out a change-management ticket
- Bulk rollout of a rulebase template across tenants

**Example prompts:**
- "Install the `howard-sdwan-spoke-1` package to its device"
- "Push the `production` package to all spokes listed in scope"
- "Deploy the policy changes and tell me if it worked"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | ADOM name |
| `package` | string | Yes | — | Policy package name |
| `scope` | array | Yes | — | `[{name, vdom}]` — targets to install to |
| `flags` | array | No | `["none"]` | FMG install flags (`preview`, `install_chkpt`, etc.) |
| `dev_rev_comments` | string | No | `"Installed via FortiManager AI SDK"` | Revision note |
| `wait` | boolean | No | `true` | Poll until install task terminal |
| `poll_interval_sec` | number | No | `3` | Seconds between polls |
| `max_wait_sec` | integer | No | `300` | Timeout |

## Interpreting Results

```json
{
  "success": true,
  "task_id": 42,
  "adom": "root",
  "package": "howard-sdwan-spoke-1",
  "state": "done",
  "percent": 100,
  "num_err": 0,
  "num_done": 2,
  "num_lines": 2,
  "waited_sec": 12.4,
  "timed_out": false,
  "lines": [
    {
      "name": "howard-sdwan-spoke-1",
      "vdom": "root",
      "ip": "10.250.250.1",
      "state": "done",
      "percent": 100,
      "detail": "install and save finished status=OK",
      "err": 0
    },
    {
      "name": "howard-sdwan-spoke-1(root)[copy]",
      "vdom": "root",
      "state": "done",
      "percent": 100,
      "detail": "Installation to real device done",
      "err": 0
    }
  ]
}
```

**Field meanings:**
- Install typically generates **2 sub-lines per device**: one for the install-and-save step, one for the copy-to-device step.
- `success: true` only when all sub-tasks reached terminal state, `num_err == 0`, and no timeout.
- `tot_percent: 200` at completion with 2 sublines = expected (`num_lines * 100`).

## Example

**User:** "Push the howard-sdwan-spoke-1 package"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-policy-package-install/1.0.0",
    parameters={
        "fmg_host": "192.168.215.17",
        "adom": "root",
        "package": "howard-sdwan-spoke-1",
        "scope": [{"name": "howard-sdwan-spoke-1", "vdom": "root"}],
        "dev_rev_comments": "SDK smoke test install"
    }
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG exec error: {'code': -11, ...}` | No permission | User needs `rpc-permit read-write` and profile with install perms |
| `FMG exec error: {'code': -3, ...}` | Package or device not in ADOM | Verify via `fortimanager-policy-package-list` and `fortimanager-device-list` |
| `num_err > 0` with `state=error` | Install failed on a device | Read `lines[].detail` for per-device reason (often "device offline" or config conflict) |
| `timed_out: true` | Task still running after `max_wait_sec` | Increase `max_wait_sec` or set `wait=false` and poll via `fortimanager-task-status` |

## Pairs With

- `fortimanager-policy-create` — author policies before install
- `fortimanager-policy-list` — verify rulebase contents
- `fortimanager-task-status` — re-poll if `wait=false`
- `fortimanager-device-settings-install` — push device-scope changes separately
