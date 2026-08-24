# FortiManager SD-WAN Template Create — Skills

## How to Call

Use this tool when:
- Standing up a new tenant/branch design that needs an FMG 7.6 SD-WAN Template (WAN Profile) before binding devices via a Model Device
- Bulk MSSP spoke rollout — one call per spoke, driven from a metadata variable set (30G / 50G / 120G / VM all bind to the same template shape)
- Composing full SD-WAN payloads (zones + members + health-checks + services + neighbors) in a single template object
- Idempotent onboarding — set `overwrite: true` so replays delete the stale template and rebuild it clean

**Example prompts:**
- "Create an SD-WAN template `bor-spoke-tpl` in ADOM `BOR_Customer_1` with a HUB zone (ADVPN on), a WAN zone, and a Public SLA health-check"
- "Add an SD-WAN template `hub-tpl` in ADOM `HUB_Prod` with two HUB1 overlay members at seq 500/501 sourced from `$(LOOPBACK_IP)`"
- "Make sure the `sdk-sdwan-tpl-test` template exists in `BOR_Customer_1` — update it if it's already there"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FortiManager hostname or IP |
| `adom` | string | No | `root` | Target ADOM |
| `name` | string | Yes | — | SD-WAN template name (unique within ADOM) |
| `status` | string | No | `enable` | `enable` / `disable` — pushed onto the SDWAN body when non-default |
| `zone` | array | No | — | Zone definitions (`name`, `advpn_select`, `advpn_health_check`, ...) |
| `members` | array | No | — | Member definitions (`seq_num`, `interface`, `zone`, `source`, ...) |
| `health_check` | array | No | — | Health-check definitions (`name`, `server`, `members`, `sla`, ...). Maps to FMG `health-check` |
| `service` | array | No | — | Service rule definitions (`id`, `name`, `dst`, `src`, `priority_members`, ...) |
| `neighbor` | array | No | — | BGP-on-Lo neighbor definitions (`ip`, `member`, `health_check`, ...) |
| `description` | string | No | `""` | Free-text description shown in the FMG WAN Template list |
| `overwrite` | boolean | No | `false` | If the template already exists and `overwrite=true`, delete-and-recreate it in place instead of failing |

**Field-naming note.** Callers use Python-friendly snake_case in every
nested dict (`seq_num`, `advpn_select`, `health_check`, `priority_members`,
`advpn_health_check`). The tool recursively converts snake_case dict keys
to the dash-case keys FMG expects (`seq-num`, `advpn-select`,
`health-check`, `priority-members`, `advpn-health-check`). Values are
never rewritten — object names like `HUB_Health` and metadata variables
like `$(HUB1_LO)` pass through intact.

## Interpreting Results

### Created (real smoke-test output against 184.73.7.106, ADOM `BOR_Customer_1`)

```json
{
  "success": true,
  "action": "created",
  "name": "sdk-sdwan-tpl-test",
  "adom": "BOR_Customer_1",
  "zone_count": 2,
  "member_count": 0,
  "health_check_count": 1,
  "service_count": 0,
  "neighbor_count": 0
}
```

### Updated (same command re-run with `overwrite=true`)

```json
{
  "success": true,
  "action": "updated",
  "name": "sdk-sdwan-tpl-test",
  "adom": "BOR_Customer_1",
  "zone_count": 2,
  "member_count": 0,
  "health_check_count": 1,
  "service_count": 0,
  "neighbor_count": 0
}
```

### Already exists (overwrite=false)

```json
{
  "success": false,
  "action": "noop",
  "name": "sdk-sdwan-tpl-test",
  "adom": "BOR_Customer_1",
  "error": "SDWAN template 'sdk-sdwan-tpl-test' already exists in ADOM 'BOR_Customer_1'. Set overwrite=true to update."
}
```

### Partial child failure

If the wanprof shell is created but one or more nested children are rejected
by FMG (bad enum, missing required inner field, name collision inside the
child list), the tool reports `success: false` and lists which children
failed while keeping the ones that succeeded:

```json
{
  "success": false,
  "action": "created",
  "name": "bor-spoke-tpl",
  "adom": "BOR_Customer_1",
  "zone_count": 2,
  "member_count": 1,
  "health_check_count": 0,
  "service_count": 0,
  "neighbor_count": 0,
  "error": "Shell created, but 1 child add(s) failed. First failure: {'child': 'health-check', 'name': 'Bad_HC', 'status': {'code': -10, 'message': 'The data is invalid for selected url'}}",
  "child_errors": [
    {"child": "health-check", "name": "Bad_HC", "status": {"code": -10, "message": "..."}}
  ]
}
```

**Field meanings:**
- `action` — `created` (new template), `updated` (existed + overwrite → delete-and-recreate), `noop` (existed + no overwrite)
- `*_count` — count of caller-supplied children that FMG actually accepted.
  Zero means the caller omitted the array; a new wanprof always ships with a
  reserved `virtual-wan-link` zone and a `Default_AWS` health-check that are
  NOT counted here (they live on the shell regardless of what you send).
- `child_errors` — present only on partial failure. Each entry names the
  child list, the identifying key of the item that was rejected, and the
  raw FMG status envelope.

## Example

**User:** "Create an SD-WAN template `bor-spoke-tpl` in `BOR_Customer_1` on 184.73.7.106.
Zones: `SDWAN-HUB` (ADVPN on) and `SDWAN-WAN`. One HUB member at seq 500 on interface
`HUB1-VPN1` sourced from `$(LOOPBACK_IP)`; wan at seq 2. Health-check `Public_SLA`
against 8.8.8.8 / 4.2.2.2 tied to seq 2. Update if it already exists."

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-sdwan-template-create/1.0.0",
    parameters={
        "fmg_host": "184.73.7.106",
        "adom": "BOR_Customer_1",
        "name": "bor-spoke-tpl",
        "status": "enable",
        "zone": [
            {"name": "SDWAN-HUB", "advpn_select": "enable"},
            {"name": "SDWAN-WAN"},
        ],
        "members": [
            {"seq_num": 500, "interface": "HUB1-VPN1", "zone": "SDWAN-HUB", "source": "$(LOOPBACK_IP)"},
            {"seq_num": 2, "interface": "wan", "zone": "SDWAN-WAN"},
        ],
        "health_check": [
            {"name": "Public_SLA", "server": ["8.8.8.8", "4.2.2.2"], "members": [2]},
        ],
        "overwrite": True,
    },
)
```

## Endpoint Layout

FMG 7.6 splits an SD-WAN Template across two URL trees. The tool hides
both from callers, but they matter when debugging with `object-list`:

| Concern | URL | Method used |
|---|---|---|
| Shell (create / list / delete) | `/pm/wanprof/adom/{adom}` | `add`, `get`, `delete` |
| Shell (named) | `/pm/wanprof/adom/{adom}/{name}` | `get`, `delete` |
| SDWAN body (status, description) | `/pm/config/adom/{adom}/wanprof/{name}/system/sdwan` | `update` |
| Zone / member / health-check / service / neighbor child lists | `.../system/sdwan/{child}` | `add` per item |

A whole-body `set` on the SDWAN URL is deliberately avoided — it wipes the
reserved `virtual-wan-link` zone and fails with `runtime error 83`.

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `Missing required parameter: name` | `name` not supplied | Provide a template name |
| `Invalid status 'X'. Use: enable \| disable` | Bad status value | Use `enable` or `disable` |
| `SDWAN template 'X' already exists in ADOM 'Y'. Set overwrite=true to update.` | Non-idempotent collision | Re-run with `overwrite: true` (or pick a new name) |
| `FMG shell-add failed: {'code': -2, ...}` | Race — name grabbed by another writer between our probe and our add | Retry, or re-run with `overwrite: true` |
| `FMG delete-before-recreate failed: {...}` | Overwrite path couldn't drop the old shell (locked by an in-flight install, ADOM workspace not saved) | Save the ADOM workspace, wait for pending installs, retry |
| `Shell created, but N child add(s) failed` | Wanprof exists but one or more child items were rejected | Inspect `child_errors[*].status` — usually `-10` (bad payload shape) or `-2` (name collision within a child list) |
| `FMG {'code': -3, ...}` | ADOM does not exist | Verify ADOM via `fortimanager-adom-list` |
| `FMG {'code': -11, ...}` | Admin profile lacks `rpc-permit` for `system sdwan` scope | On FMG: `config system admin profile / edit <profile> / set rpc-permit read-write` |
| `No credentials found for <host>` | Host missing from YAML | Add entry under `devices:` in `~/.config/mcp/fortimanager_credentials.yaml` |

## Pairs With

- `fortimanager-adom-list` — confirm the ADOM exists first
- `fortimanager-cli-template-create` / `fortimanager-system-template-create` — sister first-class templates in the SD-WAN build sequence
- `fortimanager-model-device-create` — bind this template plus its siblings onto a model device for ZTP
- `fortimanager-object-list` — inspect the child lists directly at `/pm/config/adom/{adom}/wanprof/{name}/system/sdwan/*` when debugging
- `fortimanager-device-settings-install` — push the composed template stack out to managed devices
