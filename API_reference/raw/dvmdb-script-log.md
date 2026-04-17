# /dvmdb/adom/{adom}/script/log/* — Script Output Retrieval

**Source:** https://how-to-fortimanager-api.readthedocs.io/en/latest/012_cli_script_management.html

After `/dvmdb/script/execute` returns a task ID, use these endpoints to fetch the actual **script output** (the `config / set / end` CLI that ran + any results).

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /dvmdb/adom/{adom}/script/log/latest` | Latest output for a package-scoped run |
| `GET /dvmdb/adom/{adom}/script/log/latest/device/{device}` | Latest output for a specific device |
| `GET /dvmdb/adom/{adom}/script/log/summary` | Execution history (package scope), returns list of `{log_id, script_name, exec_time, seq}` |
| `GET /dvmdb/adom/{adom}/script/log/summary/device/{device}` | Execution history for specific device |
| `GET /dvmdb/adom/{adom}/script/log/output/logid/{log_id}` | Output for a specific package-scoped log_id |
| `GET /dvmdb/adom/{adom}/script/log/output/device/{device}/logid/{log_id}` | Output for a specific device log_id |

## log_id ↔ task_id Relationship

**Critical convention** (from FNDN Q&A, answered by Jean-Pierre Forcioli):

```
If script executed against DB (policy package):
  log_id = str(task_id) + "1"        e.g. task 452 → log_id 4521

If script executed against remote device:
  log_id = str(task_id) + "0"        e.g. task 457 → log_id 4570
```

This means you can compute the log_id directly from the task_id returned by `/dvmdb/script/execute` without needing a summary lookup.

## Response: script/log/latest or log/output

```json
{
  "data": {
    "content": "\n\nStarting log (Run on database)\n\n config firewall policy\n edit \"2\"\n set _scope \"demo_device1\"-\"root\"\n next\n end\nRunning script(test-001) on DB success\n",
    "exec_time": "Wed Apr 15 13:48:07 2020",
    "log_id": 41,
    "script_name": "test-001"
  },
  "status": {"code": 0, "message": "OK"}
}
```

## Response: script/log/summary

```json
{
  "data": [
    {"exec_time": "Wed Apr 15 13:48:07 2020", "log_id": 41, "script_name": "test-001", "seq": 1},
    {"exec_time": "Wed Apr 15 13:44:50 2020", "log_id": 31, "script_name": "50_config.firewall.policy-54-adomdb", "seq": 2}
  ]
}
```

## Known Caveat

From community Q&A (Olivier Schenk, May 2020):
> *"Is there a way to determine if the script has finished? On `/dvmdb/adom/{ADOM}/script/log/output/device/{DEVICE}/logid/{LOGID}` status is always equal to 0. I don't see another API endpoint which returns such information."*

→ **Use `/task/task/{taskid}` to determine completion/success. Use `/dvmdb/adom/.../script/log/...` only for the textual output content.**
