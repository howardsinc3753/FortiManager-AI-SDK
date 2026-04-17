# FortiManager Script Run — Skills

## How to Call

Use this tool when:
- A pre-existing FMG CLI script needs to run against a device, VDOM, device group, or policy package
- Partner AI is orchestrating a workflow that ends in "apply this CLI change" across managed FortiGates
- You want a one-call "fire + wait + return results" experience rather than chaining exec + poll + log manually
- You need fire-and-forget mode (set `wait: false`) to kick off a long operation and get the task ID back

**Example prompts:**
- "Run the script `health-check` on device fw-01 in ADOM root"
- "Execute `sdwan-snapshot` against both branch-01 and branch-02"
- "Run the deploy script against the policy package `production`"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | ADOM containing the script |
| `script` | string | Yes | — | Name of an already-existing script |
| `scope_type` | string | No | `device` | One of `package` / `device` / `group` |
| `package` | string | cond. | — | Required when `scope_type=package` |
| `scope` | array | cond. | — | Required when `scope_type=device`. List of `{name, vdom}` |
| `groups` | array | cond. | — | Required when `scope_type=group`. List of device group names |
| `wait` | boolean | No | `true` | Poll task until terminal state |
| `poll_interval_sec` | number | No | `2` | Seconds between polls |
| `max_wait_sec` | integer | No | `180` | Max seconds to wait before returning timed_out |
| `fetch_log` | boolean | No | `true` | After task completes, fetch script output text |

### Scope Patterns

| Scope type | Request data shape |
|---|---|
| `package` | `{adom, package: "default", script: "..."}` |
| `device`  | `{adom, scope: [{name: "fw-01", vdom: "root"}], script: "..."}` |
| `group`   | `{adom, scope: [{name: "apac"}, {name: "amer"}], script: "..."}` |

## Interpreting Results

```json
{
  "success": true,
  "task_id": 42,
  "log_id": 420,
  "script": "health-check",
  "adom": "root",
  "state": "done",
  "percent": 100,
  "num_err": 0,
  "num_done": 1,
  "num_lines": 1,
  "waited_sec": 6.4,
  "timed_out": false,
  "lines": [
    {
      "name": "fw-01",
      "vdom": "root",
      "ip": "10.1.1.1",
      "state": "done",
      "percent": 100,
      "detail": "Running script(health-check) on device success",
      "err": 0
    }
  ],
  "log": {
    "content": "\n\nStarting log (Run on remote)\n\n get system status\n end\n",
    "exec_time": "Thu Apr 17 14:03:22 2026",
    "script_name": "health-check",
    "log_id": 420
  }
}
```

**Field meanings:**
- `success`: `true` only when task reached terminal state, `num_err == 0`, and not timed out
- `log_id`: derived as `str(task_id) + "1"` for package scope, `+ "0"` for device/group scope
- `state`: `pending | running | done | error | cancelled | aborted | warning` (see `fortimanager-task-status` for full enum)
- `log.content`: text of the CLI output (empty string if FMG hasn't flushed yet)
- If `wait: false`, `lines` and `log` will be empty — call `fortimanager-task-status` with the `task_id` later

## Example

**User:** "Run the health-check script on branch-01/root and tell me if it worked"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-script-run/1.0.0",
    parameters={
        "fmg_host": "192.168.215.17",
        "adom": "root",
        "script": "health-check",
        "scope_type": "device",
        "scope": [{"name": "branch-01", "vdom": "root"}],
        "wait": true,
        "max_wait_sec": 60
    }
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG exec error: {'code': -3, ...}` | Script does not exist in that ADOM | Create the script first via FMG GUI / API. Use `scope_type=package` requires the package to exist too. |
| `FMG exec error: {'code': -6, ...}` | Invalid URL — usually means ADOM doesn't exist or name has bad chars | Verify ADOM name with `fortimanager-adom-list` |
| `FMG exec error: {'code': -11, ...}` | rpc-permit too restrictive on admin profile | `config system admin profile / edit <name> / set rpc-permit read-write` |
| `scope_type=device requires 'scope'` | Caller forgot `scope` parameter | Provide `scope: [{name, vdom}, ...]` |
| `scope_type=package requires 'package' parameter` | Missing `package` | Provide the package name; get via `fortimanager-policy-package-list` |
| `timed_out: true` (success=false) | Polling exceeded `max_wait_sec` | Increase `max_wait_sec` or set `wait=false` and poll via `fortimanager-task-status` |
| `FMG returned no task ID` | Unexpected — exec succeeded but no task | Retry; check FMG system load |

## Pairs With

- `fortimanager-task-status` — for fire-and-forget (`wait: false`) + later polling
- `fortimanager-policy-package-list` — when scope_type=package, to find valid package names
- `fortimanager-device-list` — to find device names for the `scope` array
