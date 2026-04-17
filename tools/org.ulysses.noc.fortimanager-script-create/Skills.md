# FortiManager Script Create — Skills

## How to Call

Use this tool when:
- A downstream workflow needs a script that does not yet exist on FMG
- Partner AI is authoring automation: "write a script named `daily-check` that runs `get system status` on every device"
- Repair path: script was accidentally deleted and you need to recreate it
- Migration: copying a script from one FMG to another

**Example prompts:**
- "Create a script called `check-interfaces` that runs `show system interface` on remote devices"
- "Make a TCL script `onboarding-baseline` that does basic hardening"
- "Add (or update) the `sdk-smoke-test` script on FMG root ADOM"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | ADOM to create the script in |
| `name` | string | Yes | — | Script name (max 71 chars, unique within ADOM) |
| `content` | string | Yes | — | Script body (CLI commands or TCL) |
| `target` | string | No | `remote_device` | One of `remote_device`, `device_database`, `adom_database` |
| `type` | string | No | `cli` | One of `cli`, `tcl`, `cligrp` |
| `desc` | string | No | "" | Description (max 128 chars) |
| `overwrite` | boolean | No | `false` | If true and script exists, update instead of error |

### Target Semantics

| Target | Behavior |
|---|---|
| `remote_device` | SSH into the live FortiGate and execute (needs device online, conn_status=1) |
| `device_database` | Run against FMG's cached device config (offline-safe) |
| `adom_database` | Run against ADOM-level config objects (for package scope) |

## Interpreting Results

### Created
```json
{
  "success": true,
  "action": "created",
  "canonical_id": "root/sdk-smoke-test",
  "script": {
    "name": "sdk-smoke-test",
    "adom": "root",
    "target": "remote_device",
    "type": "cli"
  }
}
```

### Updated (overwrite=true on existing)
```json
{
  "success": true,
  "action": "updated",
  "canonical_id": "root/sdk-smoke-test",
  "script": { ... }
}
```

### Exists (overwrite=false)
```json
{
  "success": false,
  "action": "noop",
  "error": "Script 'sdk-smoke-test' already exists in ADOM 'root'. Set overwrite=true to replace."
}
```

## Example

**User:** "Create an interface-check script on FMG root ADOM"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-script-create/1.0.0",
    parameters={
        "fmg_host": "192.168.215.17",
        "adom": "root",
        "name": "check-interfaces",
        "content": "show system interface",
        "target": "remote_device",
        "type": "cli",
        "desc": "Dump interface config for audit"
    }
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG {'code': -10, ...}` | Data invalid for the URL — usually extra/wrong field types | Stick to documented fields only; target/type must be valid enum strings |
| `FMG {'code': -6, ...}` | Invalid URL — usually permission denial on writes | User needs `rpc-permit read-write` on their admin profile AND user object |
| `FMG {'code': -11, ...}` | No permission | Same as -6; session user lacks perms |
| `already exists ... Set overwrite=true` | Name collision | Either change `name` or pass `overwrite: true` |
| `FMG login failed: {'code': -11, ...}` | Bad creds or user has rpc-permit=0 | Verify creds in YAML; ensure user has rpc-permit read-write |

## Pairs With

- `fortimanager-script-run` — execute the created script (same name)
- `fortimanager-task-status` — poll the execution task after running
