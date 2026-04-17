# FortiManager Policy List — Skills

## How to Call

Use this tool when:
- User wants to enumerate firewall rules in a specific policy package
- Auditing for shadowed, misnamed, or overly permissive rules
- Preparing a rulebase review before a package install or merge
- Filtering to show only deny rules, disabled rules, or rules matching a name

**Example prompts:**
- "List firewall policies in the default package of ADOM root"
- "Show me all deny rules in the production package"
- "Are there any disabled rules in tenant ADOM_A_76 / default?"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | Administrative Domain |
| `package` | string | Yes | — | Policy package name (enumerate with `fortimanager-policy-package-list`) |
| `name_like` | string | No | — | Case-insensitive substring match on policy name |
| `action_filter` | string | No | `any` | One of `accept`, `deny`, `any` |
| `only_enabled` | boolean | No | `false` | Return only policies with `status=1` |
| `offset` | integer | No | `0` | Pagination offset |
| `limit` | integer | No | `100` | Max policies to return |

## Interpreting Results

```json
{
  "success": true,
  "count": 2,
  "package": "default",
  "policies": [
    {
      "policyid": 1,
      "name": "Allow-Internal-Out",
      "srcintf": ["any"],
      "dstintf": ["any"],
      "srcaddr": ["all"],
      "dstaddr": ["all"],
      "service": ["ALL"],
      "schedule": ["always"],
      "action": 1,
      "action_label": "accept",
      "status": 1,
      "nat": 1,
      "uuid": "xxxx-xxxx",
      "comments": ""
    }
  ]
}
```

**Field meanings:**
- `action`: 0=deny, 1=accept, 2=ipsec, 3=ssl-vpn (`action_label` gives string form)
- `status`: 1=enabled, 0=disabled
- `nat`: 1=NAT enabled on policy, 0=no NAT
- Interface / address / service / schedule fields are arrays of object names (FMG references objects by name, not value)

## Example

**User:** "Show me all deny rules in the default package of root ADOM"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-policy-list/1.0.0",
    parameters={
        "fmg_host": "192.168.215.17",
        "adom": "root",
        "package": "default",
        "action_filter": "deny"
    }
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG {'code': -11, ...}` | rpc-permit disabled for pm/config | `config system admin profile / edit <name> / set rpc-permit read-write` |
| `FMG {'code': -3, ...}` | ADOM or package does not exist | Run `fortimanager-policy-package-list` to confirm package name |
| `FMG {'code': -6, ...}` | Invalid URL | Special chars in ADOM/package — URL-encode |
| `Missing required parameter: package` | No package specified | Pass package name; get it from `fortimanager-policy-package-list` |
