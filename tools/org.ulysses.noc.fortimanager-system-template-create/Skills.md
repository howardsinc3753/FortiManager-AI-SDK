# FortiManager System Template Create — Skills

## How to Call

Use this tool when:
- Standing up a new tenant / ADOM and you need a system template (device profile) before binding devices to it
- Building a fresh SD-WAN branch design — the system template is the first template family the sequence requires
- Provisioning managed FortiGates that share common DNS / NTP / admin / syslog / SNMP settings
- Idempotent onboarding automation — set `overwrite: true` to make repeated runs safe

**Example prompts:**
- "Create a system template called `bor-branch-std` in ADOM `BOR_Customer_1`"
- "Add a device profile named `dmz-hosts` under the root ADOM"
- "Make sure the `sdk-sys-tpl-test` system template exists in `BOR_Customer_1` — update it if it's already there"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FortiManager hostname or IP |
| `adom` | string | No | `root` | Target ADOM |
| `name` | string | Yes | — | System template name (unique within ADOM) |
| `description` | string | No | `""` | Free-text description |
| `overwrite` | boolean | No | `false` | If the template already exists and `overwrite=true`, `update` it in place instead of failing |

## Interpreting Results

### Created (real smoke-test output against 184.73.7.106, ADOM `BOR_Customer_1`)

```json
{
  "success": true,
  "action": "created",
  "name": "sdk-sys-tpl-test",
  "adom": "BOR_Customer_1",
  "endpoint_used": "/pm/devprof/adom/BOR_Customer_1"
}
```

### Updated (same command re-run with `overwrite=true`)

```json
{
  "success": true,
  "action": "updated",
  "name": "sdk-sys-tpl-test",
  "adom": "BOR_Customer_1",
  "endpoint_used": "/pm/devprof/adom/BOR_Customer_1"
}
```

### Already exists (overwrite=false)

```json
{
  "success": false,
  "action": "noop",
  "name": "sdk-sys-tpl-test",
  "adom": "BOR_Customer_1",
  "endpoint_used": "/pm/devprof/adom/BOR_Customer_1",
  "error": "System template 'sdk-sys-tpl-test' already exists in ADOM 'BOR_Customer_1'. Set overwrite=true to update."
}
```

**Field meanings:**
- `action` — `created` (new template), `updated` (existed + overwrite), `noop` (existed + no overwrite)
- `endpoint_used` — the devprof URL layout FMG actually accepted. The tool tries
  `/pm/config/adom/{adom}/devprof` first; FMG 7.4 / 7.6 (validated against 184.73.7.106)
  rejects that path with code -3 "Object does not exist" and the tool falls back to
  `/pm/devprof/adom/{adom}`. Downstream tools (child templates: DNS, NTP, admin,
  syslog, SNMP) should key off this so they hit the matching family.

**Important payload note:** FMG requires an explicit `type: "devprof"` discriminator
in the create payload. Omitting it returns code -10 "data invalid for selected url".
The tool sets this automatically; callers only need to supply `name` (and optionally
`description`).

## Example

**User:** "Create a system template called `bor-branch-std` in the `BOR_Customer_1` ADOM on 184.73.7.106, and update it if it's already there."

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-system-template-create/1.0.0",
    parameters={
        "fmg_host": "184.73.7.106",
        "adom": "BOR_Customer_1",
        "name": "bor-branch-std",
        "description": "Standard BOR branch device profile",
        "overwrite": True,
    },
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `Missing required parameter: name` | `name` not supplied | Provide a template name |
| `System template 'X' already exists in ADOM 'Y'. Set overwrite=true to update.` | Non-idempotent collision | Re-run with `overwrite: true` (or pick a new name) |
| `FMG {'code': -3, ...}` | ADOM does not exist (both URL layouts refused) | Verify ADOM via `fortimanager-adom-list` |
| `FMG {'code': -11, ...}` | Admin profile lacks `rpc-permit` for `system template` scope | On FMG: `config system admin profile / edit <profile> / set rpc-permit read-write` |
| `FMG {'code': -22, ...}` | Server-side "already exists" race even after our check | Use `overwrite: true` |
| `No credentials found for <host>` | Host missing from YAML | Add entry under `devices:` in `~/.config/mcp/fortimanager_credentials.yaml` |

## Pairs With

- `fortimanager-adom-list` — confirm the ADOM exists first
- Downstream system-template child tools (DNS / NTP / admin / syslog / SNMP setters) — bind their config into the template this tool creates
- `fortimanager-device-settings-install` — push the template's bindings out to managed devices
