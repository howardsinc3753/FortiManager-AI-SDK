# /task/task — FortiManager Task Monitoring (FNDN 7.6.6)

**Source:** FNDN Swagger + https://how-to-fortimanager-api.readthedocs.io §1.7

Read-only table of the 10,000 most recent tasks. Used to poll for completion of any async operation (script execute, policy install, device add, etc.).

## Endpoints

| Endpoint | Method | Returns |
|---|---|---|
| `/task/task` | `get` | Paginated task list (10,000 most recent) |
| `/task/task/{taskid}` | `get` | Full task detail with line[] + history[] |
| `/task/task/{taskid}/line` | `get` | Just the lines (per-device subtasks) |
| `/task/task/{taskid}/line/{line}` | `get` | Specific line |
| `/task/task/{taskid}/line/{line}/history` | `get` | Progress events for that line |
| `/task/task/{taskid}/line/{line}/history/{history}` | `get` | Specific history entry |

## Task Object Fields

```json
{
  "id": 2066,
  "adom": 364,
  "title": "Install Device",
  "src": "device manager",             // source module
  "user": "admin",
  "pid": 26153,
  "state": "done",                     // pending | done | error | ... (11 enum values)
  "percent": 100,                      // global task progress (0-100)
  "tot_percent": 200,                  // sum across subtasks (100 x num_lines when all done)
  "num_lines": 2,
  "num_done": 2,
  "num_err": 0,                        // ← 0 means success, non-zero = failure
  "num_warn": 0,
  "start_tm": 1515752024,
  "end_tm": 1515752051,
  "flags": 0,
  "line": [ /* subtasks — see below */ ],
  "history": [ /* progress events */ ]
}
```

## Line (Subtask) Fields

A task breaks into one or more lines (one per targeted device/vdom):

```json
{
  "name": "FG600C-194-77",
  "vdom": "root",                      // or null
  "ip": "192.168.194.77",
  "oid": 366,
  "poid": 0,
  "state": "done",                     // pending | done | error | ...
  "percent": 100,
  "detail": "install and save finished status=OK",
  "err": 0,
  "start_tm": 0,
  "end_tm": 0,
  "history": [ /* progress events */ ]
}
```

## History Entry Fields

```json
{
  "name": "FG600C-194-77",
  "vdom": null,
  "detail": "2018-01-12 02:13:44:start to install dev(FG600C-194-77)",
  "percent": 0,
  "state": 0
}
```

## Polling Pattern

```
1. initial call: get /task/task/{taskid}
2. loop:
     - sleep poll_interval (e.g. 2s)
     - get /task/task/{taskid}
     - stop when:
         response.data.percent == 100   (progress complete)
       OR response.data.state in {"done","error"}
3. success = (num_err == 0)
```

**Completion check priority**: `state` field is authoritative. Use `percent` only for progress display.

## State Enum (11 values)

Not fully documented in dump but includes at minimum:
- `pending` (default initial)
- `running`
- `done` (terminal, success)
- `error` (terminal, failure)

## Task Discovery

`/task/task` with filters lets you search the 10k most recent:
- `fields`: limit attributes returned
- `filter`: `[["title","==","Install Device"]]` etc.
- `range`: `[offset, limit]` pagination
- `sortings`: sort by timestamp, id, etc.

## Example (Full Task Response)

See `API_reference/raw/task-task.md` — full "Install Device" example in the readthedocs companion guide (§1.7), captured above in the Task Object Fields section.
