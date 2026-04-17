# FortiManager Task Status — Skills

## How to Call

Use this tool when:
- You have a task ID from a prior exec call (script run, policy install, device add) and want to check progress or final result
- You want to block/wait until a long-running FMG operation completes
- Debugging why a prior operation failed — the `line[]` array shows per-device errors
- Orchestrating multi-step agentic workflows where one step's task must finish before the next starts

**Example prompts:**
- "Check the status of task 452 on fmg-lab"
- "Wait for task 2066 to finish and tell me if it succeeded"
- "Show me the per-device results for task 457"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `task_id` | integer | Yes | — | Task ID (returned by exec calls) |
| `wait` | boolean | No | `false` | If true, poll until task hits terminal state |
| `poll_interval_sec` | number | No | `2` | Seconds between polls when `wait=true` |
| `max_wait_sec` | integer | No | `120` | Max seconds to wait; returns `timed_out: true` after |
| `include_lines` | boolean | No | `true` | Include per-device subtask results |
| `include_history` | boolean | No | `false` | Include full progress-event history |

## Interpreting Results

```json
{
  "success": true,
  "task_id": 4,
  "state": "done",
  "state_is_terminal": true,
  "percent": 100,
  "num_lines": 1,
  "num_done": 1,
  "num_err": 0,
  "num_warn": 0,
  "title": "Run Script",
  "src": "device manager",
  "user": "admin",
  "start_tm": 1768511703,
  "end_tm": 1768511710,
  "elapsed_sec": 7,
  "waited_sec": 0,
  "timed_out": false,
  "lines": [
    {
      "name": "howard-sdwan-spoke-1",
      "vdom": "root",
      "ip": "10.250.250.1",
      "state": "done",
      "percent": 100,
      "detail": "Running script(test-001) on DB success",
      "err": 0
    }
  ]
}
```

**Field meanings:**
- `success`: `true` only when state is terminal, `num_err == 0`, and not timed out
- `state`: `pending | running | done | error | cancelled | aborted | warning | waiting | ready`
- `state_is_terminal`: `true` for `done/error/cancelled/aborted/warning` — stop polling
- `num_err`: per-subtask error count; 0 = all subtasks succeeded
- `lines[]`: one entry per device+vdom the task targeted; `detail` is human-readable outcome
- `waited_sec`: how long this tool call actually blocked (0 when `wait=false`)

## Example

**User:** "Wait for task 452 on FMG to finish and show me the result"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-task-status/1.0.0",
    parameters={
        "fmg_host": "192.168.215.17",
        "task_id": 452,
        "wait": true,
        "max_wait_sec": 60
    }
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG {'code': -3, ...}` | Task ID does not exist | Task history is capped at 10,000 most recent; ID may have rolled off |
| `FMG {'code': -11, ...}` | rpc-permit disabled for /task | `config system admin profile / edit <name> / set rpc-permit read-write` |
| `timed_out: true` in response (success=false) | Polling exceeded `max_wait_sec` | Increase `max_wait_sec` or check task manually |
| `task_id must be an integer` | Caller passed string/null | Pass as int — use the value from exec response directly |
