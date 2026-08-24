# FortiManager CLI Template Group Create — Skills

## How to Call

Use this tool when:
- Bundling several CLI templates into one ordered set that FMG applies to a device at install time
- Building the SD-WAN provisioning stack (System → Interface → Static → IPsec → BGP → SDWAN)
- Onboarding a new tenant/site where a group of pre-authored CLI templates should ride together
- Updating the composition or ordering of an existing group (`overwrite: true`)

**Example prompts:**
- "Create a CLI template group named `bor-sdwan-build` containing system, interface, static, ipsec, bgp, sdwan in that order"
- "Group these CLI templates into `site-3-provision` on ADOM BOR_Customer_1"
- "Update the `bor-sdwan-build` group to add the sdwan-health template at the end"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP (credentials resolved from YAML) |
| `adom` | string | No | `root` | Target ADOM |
| `name` | string | Yes | — | Group name (unique within ADOM) |
| `members` | array of strings | Yes | — | Ordered list of CLI template names. Order = install execution order; not sorted. |
| `description` | string | No | `""` | Free text shown in FMG GUI |
| `overwrite` | boolean | No | `false` | If true and group exists, update it instead of failing |

**Important:** Callers pass `members: ["tpl1", "tpl2"]` as a plain string list.
The tool transforms this to the FMG-native `member: [{"name": "tpl1"}, {"name": "tpl2"}]`
shape internally. Order is preserved verbatim — do not sort.

## Interpreting Results

### Created (live smoke against FMG 184.73.7.106)
```json
{
  "success": true,
  "action": "created",
  "name": "sdk-cli-grp-test",
  "adom": "BOR_Customer_1",
  "member_count": 1,
  "members": ["sdk-cli-tpl-test"],
  "missing_templates": []
}
```

### Updated (re-run with overwrite=true, live smoke against FMG 184.73.7.106)
```json
{
  "success": true,
  "action": "updated",
  "name": "sdk-cli-grp-test",
  "adom": "BOR_Customer_1",
  "member_count": 1,
  "members": ["sdk-cli-tpl-test"],
  "missing_templates": []
}
```

### Created (all referenced templates already exist)
```json
{
  "success": true,
  "action": "created",
  "name": "bor-sdwan-build",
  "adom": "BOR_Customer_1",
  "member_count": 6,
  "members": ["system", "interface", "static", "ipsec", "bgp", "sdwan"],
  "missing_templates": []
}
```

### Already exists (overwrite=false)
```json
{
  "success": false,
  "action": "noop",
  "name": "bor-sdwan-build",
  "adom": "BOR_Customer_1",
  "member_count": 6,
  "members": ["system", "interface", "static", "ipsec", "bgp", "sdwan"],
  "missing_templates": [],
  "error": "CLI template group 'bor-sdwan-build' already exists in ADOM 'BOR_Customer_1'. Set overwrite=true to update."
}
```

**Field meanings:**
- `action` = `created` | `updated` | `noop`
- `member_count` = number of templates in the group (== `len(members)`)
- `members` = the order FMG will execute them in at install time
- `missing_templates` = advisory only. Members whose backing CLI template
  wasn't found in the ADOM at create time. FMG resolves references at install
  time, so this is a typo-catching helper — not a failure.

## Example

**User:** "Build the SD-WAN provisioning group on FMG 184.73.7.106 in ADOM BOR_Customer_1 with the standard 6 templates in order"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-cli-template-group-create/1.0.0",
    parameters={
        "fmg_host": "184.73.7.106",
        "adom": "BOR_Customer_1",
        "name": "bor-sdwan-build",
        "members": ["system", "interface", "static", "ipsec", "bgp", "sdwan"],
        "description": "Standard BOR SD-WAN provisioning stack",
        "overwrite": True,
    },
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `Missing required parameter: name` | No group name provided | Pass a `name` |
| `'members' must be a non-empty list of CLI template names` | Empty or non-list | Provide at least one template name in `members` |
| `members[i] must be a non-empty string` | Bad element in list | Ensure every entry is a non-blank string |
| `... already exists in ADOM ...` | Group of same name already there | Set `overwrite: true` |
| `FMG {'code': -3, ...}` | ADOM not found | Verify with `fortimanager-adom-list` |
| `FMG {'code': -11, ...}` | rpc-permit disabled on admin profile | `config system admin profile / edit <profile> / set rpc-permit read-write` |
| `FMG {'code': -10, ...}` | Data invalid — malformed member payload | Confirm each `members[i]` is a plain string |

## Pairs With

- `fortimanager-cli-template-create` — build the CLI templates that this group references
- `fortimanager-system-template-create` — the sibling device-profile container
- `fortimanager-model-device-create` — bind the group to a model device for ZTP provisioning
- `fortimanager-device-settings-install` — push the group's contents to the device
