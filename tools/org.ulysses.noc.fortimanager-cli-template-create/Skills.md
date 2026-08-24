# FortiManager CLI Template Create — Skills

## How to Call

Use this tool when:
- Authoring a FortiOS CLI template that Model Devices will pull during ZTP (BGP, IPsec, static route, interface configs)
- Uploading a Jinja2 template that renders per-device using FMG metadata variables
- Standing up per-platform templates (FortiGate 30G / 50G / 120G / VM) from a partner's `.j2` library
- Any workflow that needs multi-line CLI stored verbatim under `/pm/config/adom/{adom}/obj/cli/template`

**Example prompts:**
- "Load this BGP CLI script as a template called bgp-underlay in the BOR_Customer_1 ADOM"
- "Create a Jinja2 CLI template ipsec-branch from the file branch.j2 in ADOM Acme"
- "Update the interface-baseline template with a new script body and set overwrite=true"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname or IP |
| `adom` | string | No | `root` | Target ADOM |
| `name` | string | Yes | — | CLI template name (unique within ADOM) |
| `script` | string | Yes | — | Multi-line CLI or Jinja body. `$(VAR)` metadata syntax preserved verbatim |
| `type` | string | No | `cli` | `cli` (int 0) or `jinja` (int 1) — mapped internally |
| `description` | string | No | `""` | Free text shown in FMG GUI |
| `overwrite` | boolean | No | `false` | Update if template already exists |

## Interpreting Results

### Success (live smoke against `184.73.7.106`, ADOM `BOR_Customer_1`)
```json
{
  "success": true,
  "action": "created",
  "name": "sdk-cli-tpl-test",
  "adom": "BOR_Customer_1",
  "type": "cli",
  "script_lines": 4,
  "type_encoding": "int"
}
```

### Success (idempotent replay with `overwrite=true`)
```json
{
  "success": true,
  "action": "updated",
  "name": "sdk-cli-tpl-test",
  "adom": "BOR_Customer_1",
  "type": "cli",
  "script_lines": 4,
  "type_encoding": "int"
}
```

### Already exists (`overwrite=false`)
```json
{
  "success": false,
  "action": "noop",
  "name": "sdk-cli-tpl-test",
  "adom": "BOR_Customer_1",
  "type": "cli",
  "error": "CLI template 'sdk-cli-tpl-test' already exists in ADOM 'BOR_Customer_1'. Set overwrite=true to update."
}
```

**Field meanings:**
- `action` — `created`, `updated`, or `noop`
- `script_lines` — line count of the stored body (sanity check for multi-line uploads)
- `type_encoding` — `int` if FMG accepted `0/1` (documented path), `string` if the fallback (`"cli"`/`"jinja"`) had to be used

## Example

**User:** "Upload this BGP underlay CLI as a template called bgp-underlay-v1 in ADOM BOR_Customer_1"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-cli-template-create/1.0.0",
    parameters={
        "fmg_host": "184.73.7.106",
        "adom": "BOR_Customer_1",
        "name": "bgp-underlay-v1",
        "script": (
            "config router bgp\n"
            "    set as $(BGP_AS)\n"
            "    set router-id $(BGP_ROUTER_ID)\n"
            "    config neighbor\n"
            "        edit \"$(BGP_PEER_IP)\"\n"
            "            set remote-as $(BGP_PEER_AS)\n"
            "        next\n"
            "    end\n"
            "end\n"
        ),
        "type": "cli",
        "description": "BOR BGP underlay — variables from FMG metadata",
        "overwrite": True,
    }
)
```

**Jinja variant:**
```python
{
    "fmg_host": "184.73.7.106",
    "adom": "Acme",
    "name": "ipsec-branch",
    "script": open("branch.j2").read(),
    "type": "jinja",
    "overwrite": True,
}
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `Missing required parameter: script` | No template body supplied | Pass a non-empty CLI/Jinja string |
| `Invalid type 'foo'. Use: cli \| jinja` | Type outside allowed set | Set `type: "cli"` or `type: "jinja"` |
| `CLI template 'X' already exists ... Set overwrite=true to update.` | Idempotency guard tripped | Retry with `overwrite: true` |
| `FMG {'code': -3, ...}` | ADOM not found | Verify via `fortimanager-adom-list` |
| `FMG {'code': -6, ...}` | Invalid URL — cli/template path unsupported on this FMG build | Confirm FMG 7.6+ and that CLI Templates are enabled |
| `FMG {'code': -10, ...}` | Data invalid — often the `type` field shape | Tool auto-retries with string enum; if still failing, verify script body syntax |
| `FMG {'code': -11, ...}` | rpc-permit disabled on admin profile | `config system admin profile / edit <profile> / set rpc-permit read-write` |
| `FMG {'code': -9001, ...}  parse cli template fail: variable 'X' not exist` | Body references an FMG metadata variable that isn't defined for the ADOM/device | Create the metadata var first via `fortimanager-metadata-create`, or remove/rename the `$(X)` reference |

## Pairs With

- `fortimanager-adom-list` — confirm target ADOM before writing
- `fortimanager-model-device-create` — attach the template to a Model Device via CLI template group
- `fortimanager-policy-package-install` — after templates + policies are staged, push to the device
