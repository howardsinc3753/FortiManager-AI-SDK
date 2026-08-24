# FortiManager Template Bind To Device — Skills

## How to Call

Use this tool when:
- Attaching a provisioning template (system / CLI group / SDWAN) to a
  managed device or model device
- Onboarding a new spoke/branch that needs the tenant SD-WAN + CLI baseline
- Adding a device to an existing template without disturbing other members
- Pre-flighting a bind (use `dry_run: true`) before an install-config run

**Example prompts:**
- "Bind SDWAN template `bor-tenant1-tpl` to device `spoke-nyc-01` in ADOM `BOR_Customer_1`"
- "Attach system template `sdk-sys-tpl-test` to model device `branch-42`"
- "Dry-run adding `spoke-test-01` to the CLI template group `mssp-baseline`"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP (credentials resolved from YAML) |
| `adom` | string | No | `root` | Target ADOM |
| `template_type` | string | Yes | — | `system` / `cli-group` / `sdwan` |
| `template_name` | string | Yes | — | Existing template name |
| `device` | string | Yes | — | Device name (must exist in ADOM, real or model) |
| `vdom` | string | No | `root` | VDOM name to bind |
| `dry_run` | boolean | No | `false` | If true, no write is performed |

## Interpreting Results

### Bound (successful write)
```json
{
  "success": true,
  "action": "bound",
  "template_type": "sdwan",
  "template_name": "bor-tenant1-tpl",
  "adom": "BOR_Customer_1",
  "device": "spoke-nyc-01",
  "vdom": "root",
  "scope_members_after": 3,
  "endpoint_used": "/pm/config/adom/BOR_Customer_1/obj/system/sdwan/bor-tenant1-tpl"
}
```

### Already bound (idempotent no-op)
```json
{
  "success": true,
  "action": "already-bound",
  "template_type": "sdwan",
  "template_name": "bor-tenant1-tpl",
  "adom": "BOR_Customer_1",
  "device": "spoke-nyc-01",
  "vdom": "root",
  "scope_members_after": 3,
  "endpoint_used": "/pm/config/adom/BOR_Customer_1/obj/system/sdwan/bor-tenant1-tpl"
}
```

### Dry run (happy path — smoke against `sdk-sys-tpl-test` in `BOR_Customer_1`)
```json
{
  "success": true,
  "action": "dry-run",
  "template_type": "system",
  "template_name": "sdk-sys-tpl-test",
  "adom": "BOR_Customer_1",
  "would_bind_device": "spoke-test-01",
  "would_bind_vdom": "root",
  "existing_scope_members": [],
  "new_scope_members": [
    {"name": "spoke-test-01", "vdom": "root"}
  ],
  "endpoint_used": "/pm/config/adom/BOR_Customer_1/devprof/sdk-sys-tpl-test"
}
```

### Dry run (template missing — smoke against `sdk-sdwan-tpl-test`)
```json
{
  "success": false,
  "template_type": "sdwan",
  "template_name": "sdk-sdwan-tpl-test",
  "adom": "BOR_Customer_1",
  "error": "Template 'sdk-sdwan-tpl-test' (type=sdwan) not found in ADOM 'BOR_Customer_1'"
}
```

The dry-run path emits `existing_scope_members` and `new_scope_members` so
callers can diff before executing the real bind. The not-found variant is
returned when the sibling create-agent hasn't landed the template yet —
proves the discovery path fails cleanly with a caller-actionable message.

**Field meanings:**
- `action` = `bound` (write happened) | `already-bound` (idempotent skip) | `dry-run`
- `scope_members_after` = length of the merged `scope-member` array after the write
- `endpoint_used` = the URL FMG actually accepted (system templates fall
  back from `/pm/config/adom/.../devprof` to `/pm/devprof/adom/...` when needed)

## Example

**User:** "Bind the SDWAN template `bor-tenant1-tpl` to `spoke-nyc-01`."

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-template-bind-to-device/1.0.0",
    parameters={
        "fmg_host": "184.73.7.106",
        "adom": "BOR_Customer_1",
        "template_type": "sdwan",
        "template_name": "bor-tenant1-tpl",
        "device": "spoke-nyc-01",
        "vdom": "root",
    },
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `Template 'X' (type=Y) not found in ADOM 'Z'` | Template does not exist at any candidate URL for that type in the ADOM | Create it first (e.g. `fortimanager-system-template-create`) or verify `template_type` |
| `FMG {'code': -11, ...}` | `rpc-permit` disabled on admin profile | `config system admin profile / edit <profile> / set rpc-permit read-write` |
| `FMG {'code': -3, ...}` | ADOM or object path not found | Verify ADOM via `fortimanager-adom-list` and template via its `-list` tool |
| `FMG {'code': -6, ...}` | Invalid URL for FMG release | Automatic fallback covers system templates; other types have a single canonical path |
| `Invalid template_type ...` | Enum outside `system` / `cli-group` / `sdwan` | Correct the caller |
| `Missing required parameter: ...` | fmg_host / template_name / device omitted | Supply the parameter |

## Pairs With

- `fortimanager-system-template-create` — create the template before binding
- `fortimanager-cli-template-create` — same for CLI template groups
- `fortimanager-model-device-create` — create the model device before binding
- `fortimanager-device-settings-install` — after binding, push the merged config to the device
