# FortiManager JSON-RPC — Cross-Cutting Conventions

General JSON-RPC behaviors that apply to ALL endpoints, not any one resource.

**Source:** https://how-to-fortimanager-api.readthedocs.io §1.7–1.10

## Async Tasks

Long operations (install, script exec, device add) return a task ID immediately.
Poll via `/task/task/{taskid}` — see `task-task.md`.

## Multiplexing Requests

The `params` array can hold **multiple** entries to batch operations in a single HTTP round-trip.

### Same method, different URLs
```json
{
  "method": "get",
  "params": [
    {"url": "/dvmdb/device", "fields": ["name"]},
    {"url": "/dvmdb/adom",   "fields": ["name"], "filter": ["restricted_prds","==","fos"]}
  ],
  "session": "..."
}
```
Response's `result[]` matches the order and length of `params[]`.

### Use cases
- Fetch identical resources across multiple ADOMs
- Combine device inventory + ADOM list in one call (reduces round-trips)
- Run a status check across multiple managed FortiGates via `/sys/proxy/json`

## Symbolic vs Numeric Values (`verbose`)

FMG stores many enum values as integers but also accepts human-readable names.

### Write paths (add/update/set)
Both work transparently:
```json
"type": 0         // ipmask as int
"type": "ipmask"  // symbolic — preferred
```

### Read paths (get)
Default returns numeric. Add `verbose: 1` at the **envelope level** (not inside params) to get symbolic:
```json
{
  "id": 1,
  "method": "get",
  "verbose": 1,
  "params": [{"url": "/pm/config/adom/root/obj/firewall/address"}],
  "session": "..."
}
```

**Recommendation for SDK tools**: use `verbose: 1` by default so responses are self-describing.
(Not yet exposed in FortiManagerClient — TODO add as optional flag.)

## Parameter Reference (GET)

| Key | Purpose |
|---|---|
| `url` | resource path (required) |
| `fields` | array of attr names to return; everything else suppressed |
| `filter` | server-side filter: `[["attr","op","value"]]` — ops include `==`, `!=`, `like`, `>`, `<` |
| `range` | pagination `[offset, limit]` |
| `sortings` | `[{"attr": 1}]` — 1 ascending, 2 descending |
| `loadsub` | 0/1 — include sub-objects (default 1) |
| `option` | `count`, `syntax`, `object member`, `scope member`, `no loadsub`, `datasrc`, `get reserved` |
| `expand member` | expand group membership (addr groups, service groups) |

## Unsetting Attributes (since FMG 5.4.1)

```json
{
  "method": "set",
  "params": [{
    "url": "pm/config/device/TEST-FGT/global/system/interface",
    "data": {
      "name": "dmz",
      "unset attrs": ["ip"]
    }
  }]
}
```

Alternative: for some object types, simply omitting an attribute in a `set` call clears it.

## Table Update Gotcha

When using `set` on a table, **missing entries are deleted**. Use `add` / `update` / `delete` for entry-level operations. `set` on `/pm/config/adom/{adom}/obj/firewall/address` with a single entry will wipe all others.

## JSON-RPC Envelope Key

All JSON-RPC calls to FMG include `"jsonrpc": "1.0"` in most examples but the FMG server also accepts requests without it. Our `FortiManagerClient` currently omits it and works fine (confirmed against 7.6.5 lab).
