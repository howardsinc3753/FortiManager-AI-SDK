# FortiManager Policy Create — Skills

## How to Call

Use this tool when:
- Authoring new firewall rules in a tenant policy package
- Partner AI workflow "allow web-01 to reach the internet" — creates the policy
- Automating onboarding that installs a rulebase from a template
- Before install: create all policies, then call `fortimanager-policy-package-install`

**Example prompts:**
- "Create an accept policy named `allow-web` from internal to any, service HTTPS"
- "Add a deny rule blocking the range `dhcp-pool` in package `howard-sdwan-spoke-1`"
- "Insert a policy allowing DNS from LAN-subnet to DNS-servers with logtraffic all"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | ADOM name |
| `package` | string | Yes | — | Policy package name |
| `name` | string | No | — | Policy name |
| `srcintf` | array | Yes | — | Source interface(s), e.g. `["port1"]` or `["any"]` |
| `dstintf` | array | Yes | — | Destination interface(s) |
| `srcaddr` | array | Yes | — | Source address object name(s) |
| `dstaddr` | array | Yes | — | Destination address object name(s) |
| `service` | array | Yes | — | Service object name(s), e.g. `["HTTPS"]` or `["ALL"]` |
| `schedule` | array | No | `["always"]` | Schedule object name(s) |
| `action` | string | No | `accept` | `accept` / `deny` / `ipsec` / `ssl-vpn` |
| `status` | string | No | `enable` | `enable` / `disable` |
| `nat` | string | No | `disable` | `enable` / `disable` |
| `logtraffic` | string | No | `utm` | `disable` / `utm` / `all` |
| `comments` | string | No | "" | Policy description |

## Interpreting Results

```json
{
  "success": true,
  "action": "created",
  "policyid": 1,
  "name": "allow-web",
  "adom": "root",
  "package": "howard-sdwan-spoke-1"
}
```

**Notes:**
- FMG auto-assigns `policyid`. To specify one, use `fortimanager-policy-update` (future tool).
- Object references are by **name**, not by object ID. All referenced addresses/services/interfaces must exist — validate via `fortimanager-firewall-address-list` first.
- The policy is added to the end of the package; use `fortimanager-policy-move` (future) to reorder.

## Example

**User:** "Allow web-01 to reach any destination over HTTPS"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-policy-create/1.0.0",
    parameters={
        "fmg_host": "192.168.215.17",
        "adom": "root",
        "package": "howard-sdwan-spoke-1",
        "name": "allow-web-01",
        "srcintf": ["any"],
        "dstintf": ["any"],
        "srcaddr": ["web-01"],
        "dstaddr": ["all"],
        "service": ["HTTPS"],
        "action": "accept",
        "nat": "enable"
    }
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `Missing or empty required parameter: X` | Required array empty | Required arrays must have at least 1 entry |
| `FMG {'code': -10, ...}` | Invalid data for URL | Usually means a referenced address/service/interface name doesn't exist |
| `FMG {'code': -3, ...}` | Package or ADOM missing | Verify with `fortimanager-policy-package-list` |
| `FMG {'code': -22, ...}` | Duplicate or conflict | Choose a different name |

## Pairs With

- `fortimanager-firewall-address-list` — discover valid address names
- `fortimanager-firewall-address-create` — create missing addresses first
- `fortimanager-policy-list` — verify the new policy appears
- `fortimanager-policy-package-install` — push rulebase to device after creating
