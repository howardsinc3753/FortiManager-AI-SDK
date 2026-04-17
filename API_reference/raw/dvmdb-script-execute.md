# /dvmdb/script/execute — FortiManager 7.6.6 (FNDN)

**Source:** FNDN Swagger, `Base URL: 192.168.209.54/jsonrpc`
**Companion guide:** https://how-to-fortimanager-api.readthedocs.io/en/latest/012_cli_script_management.html

## Three Variants

Same request/response shape, different URL:

| URL | Scope |
|---|---|
| `POST /dvmdb/script/execute` (exec) | default (current ADOM context) |
| `POST /dvmdb/global/script/execute` (exec) | global scripts |
| `POST /dvmdb/adom/{adom}/script/execute` (exec) | explicit ADOM |

## Request Body (JSON-RPC envelope)

```json
{
  "method": "exec",
  "params": [
    {
      "data": {
        "adom": ["string"],
        "package": ["string"],
        "pblock": ["string"],
        "scope": [
          { "name": "string", "vdom": "string" }
        ],
        "script": "string"
      },
      "url": "/dvmdb/script/execute"
    }
  ],
  "session": "string",
  "id": 1
}
```

### Param reference

| Field | Type | Notes |
|---|---|---|
| `method` | string | always `"exec"` |
| `params[0].data.script` | string | **Script name** (must already exist on FMG) |
| `params[0].data.scope` | array of `{name, vdom}` | **Target device(s) + VDOM** |
| `params[0].data.adom` | array of string | ADOM name(s) — optional datasource reference |
| `params[0].data.package` | array of string | Policy package(s) — used when script targets pkg |
| `params[0].data.pblock` | array of string | Policy block(s) — used when script targets pblock |
| `params[0].url` | string | Must match variant: `/dvmdb/script/execute` or `/dvmdb/adom/{adom}/script/execute` |
| `session` | string | JSON-RPC session token (omit when using Bearer token auth) |
| `id` | int | client-generated request id |

## Response (200)

```json
{
  "method": "exec",
  "result": [
    {
      "data": { "task": ["string"] },
      "status": { "code": 0, "message": "string" },
      "url": "/dvmdb/script/execute"
    }
  ],
  "id": 1
}
```

**Key fields:**
- `result[0].data.task` — array of **task IDs** (as strings). Poll via `/task/task/{taskid}` for progress/results.
- `result[0].status.code` — `0` = accepted. Non-zero = error (see global FMG status codes).

## Usage Pattern (exec + poll + fetch log)

```
1. POST /dvmdb/adom/{adom}/script/execute
     → receive task ID
2. GET  /task/task/{taskid}
     → poll until state == "done" (success if num_err == 0) — see task-task.md
3. GET  /dvmdb/adom/{adom}/script/log/output/[device/<dev>/]logid/<log_id>
     → fetch CLI output text — see dvmdb-script-log.md

log_id derivation from task_id:
   DB/package scope   : log_id = str(task_id) + "1"
   Device scope       : log_id = str(task_id) + "0"
```

## Scope Patterns (from readthedocs §012)

### A. Script against a Policy Package (no scope field)
```json
{
  "method": "exec",
  "params": [{
    "url": "/dvmdb/adom/DEMO/script/execute",
    "data": {
      "adom": "DEMO",
      "package": "default",
      "script": "script-002"
    }
  }],
  "session": "..."
}
```

### B. Script against specific device+vdom
```json
{
  "method": "exec",
  "params": [{
    "url": "/dvmdb/adom/DEMO/script/execute",
    "data": {
      "adom": "DEMO",
      "scope": [{"name": "peer11", "vdom": "root"}],
      "script": "script-003"
    }
  }]
}
```

### C. Script against multiple devices (fan-out)
```json
"scope": [
  {"name": "peer11", "vdom": "root"},
  {"name": "peer12", "vdom": "root"}
]
```
Returns a single task that fans out internally; line[] in `/task/task/{taskid}` shows per-device results.

### D. Script against device group(s)
**Convention:** scope entry with only `name` (no `vdom`) = device group.
```json
"scope": [
  {"name": "apac"},
  {"name": "amer"}
]
```

## Response: Task Field Type Discrepancy

Swagger model declares `data.task` as `[string]` (array of strings), but the live FNDN example returns a single integer:
```json
"data": {"task": 452}
```
**Implementation note:** handle both shapes. Normalize to list of ints:
```python
t = resp["result"][0]["data"].get("task")
task_ids = [t] if isinstance(t, int) else (t or [])
```

## Required Preconditions

- The script (`data.script`) must already exist. Create via `/dvmdb/adom/{adom}/script` (add/set) before calling execute.
- `scope[].name` / `vdom` are FMG datasource refs — they're validated against the managed device registry at execute time.

## Field Type Notes (from Swagger model)

- `adom`, `package`, `pblock`, `scope`, `scope[].name`, `scope[].vdom` — all typed as datasource references (FMG validates them against the ADOM/device/vdom registries at call time).
- `script` is a plain string — the name of a script you've already created via `/dvmdb/script` add/set.
- A single `execute` call with multiple `scope` entries fans out to all targets and returns a task array of matching length.
