# FortiManager FNDN API Reference

**Source:** https://fndn.fortinet.com (FortiManager 7.6.6)
**Companion:** https://how-to-fortimanager-api.readthedocs.io

## Endpoint Tree

All API calls use a single endpoint: `POST https://<fmg-ip>/jsonrpc`

### dvmdb/* — Device Manager Database
| Path | Purpose |
|---|---|
| `/dvmdb/_meta_fields` | Metadata fields |
| `/dvmdb/_upgrade` | Upgrade info |
| `/dvmdb/adom` | List ADOMs |
| `/dvmdb/adom/{adom}/device` | Devices in ADOM |
| `/dvmdb/device` | All managed devices (global) |
| `/dvmdb/folder` | Device folders |
| `/dvmdb/group` | Device groups |
| `/dvmdb/revision` | Config revisions |
| `/dvmdb/script` | CLI scripts |
| `/dvmdb/script/execute` | Execute script (returns task ID) |
| `/dvmdb/workflow` | Workflow engine |
| `/dvmdb/workspace` | Workspace lock/save/revert |

### pm/config/* — Policy & Object Manager
**System Template** (`pm/config/device`, `pm/config/log`, `pm/config/system`, `pm/devprof`)
**WAN Template** (`pm/config/system`, `pm/wanprof`)
**Policy Package** (`pm/config/firewall`, `pm/config/authentication`, etc., `pm/pblock`, `pm/pkg`, `pm/pkg/schedule`)
**ADOM Level Objects** (`pm/config/adom/{adom}/obj/*` — firewall address/service/vip, ips, antivirus, webfilter, vpn, etc.)
**Device Level Config** (`pm/config/device/{dev}/vdom/{vdom}/*`)

### task/* — Async Tasks
| Path | Purpose |
|---|---|
| `/task/task` | Query task status (used after script-execute, install-package) |

## JSON-RPC Envelope

```json
{
  "id": 1,
  "method": "get|set|add|update|delete|exec|clone|move",
  "params": [{
    "url": "/dvmdb/adom",
    "data": {...},
    "fields": ["name", "uuid"],
    "filter": [["name", "==", "root"]],
    "range": [0, 50],
    "option": ["object member"]
  }],
  "session": "<token-if-session-auth>"
}
```

**Auth variants:**
- Token mode: add header `Authorization: Bearer <token>` — no `session` key in body
- Session mode: POST to `/jsonrpc` with `method=exec url=/sys/login/user` → session token → include as `"session":"..."` in body

## Param Reference

| Key | Type | Use |
|---|---|---|
| `url` | str | Required. Resource path. |
| `data` | dict/list | Body for set/add/update/exec |
| `fields` | list[str] | GET only. Return only named fields. Major payload reduction. |
| `filter` | list | GET only. Server-side filter. E.g. `[["platform_str","==","FGT60F"]]` |
| `range` | list[int,int] | GET only. Pagination `[offset, limit]`. |
| `option` | list[str] | FMG options: `"object member"`, `"scope member"`, `"no loadsub"`, `"syntax"`, `"datasrc"`, `"get reserved"` |

## Status Codes (common)

| Code | Meaning |
|---|---|
| 0 | OK |
| -3 | Object does not exist |
| -6 | Invalid URL |
| -10 | Invalid session |
| -11 | No permission for the resource → check admin profile `rpc-permit` |
| -22 | Object already exists |

## Script Execution Pattern

```
1. exec /dvmdb/script/execute → returns taskid
2. poll /task/task/{taskid}  → watch state until "done"
3. read task.line[] for per-device results
```

## References

- FNDN portal: https://fndn.fortinet.com → FortiAPI → FortiManager
- Unofficial guide: https://how-to-fortimanager-api.readthedocs.io
- Ansible modules (endpoint/param map): https://docs.ansible.com/ansible/latest/collections/fortinet/fortimanager/index.html
