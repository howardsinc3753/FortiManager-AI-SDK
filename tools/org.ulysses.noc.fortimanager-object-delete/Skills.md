# FortiManager Object Delete — Skills

## How to Call

Use this tool when:
- Removing any FMG object — address, VIP, policy, service, schedule, etc.
- Cleaning up after a workflow (delete test objects, retire old policies)
- Idempotent cleanup — object may or may not exist (default: no error when already absent)

**Example prompts:**
- "Delete the address `web-01`"
- "Remove policy 7 from package `default`"
- "Clean up the test VIP `sdk-vip-test`"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `url` | string | Yes | — | Named-entity URL |
| `idempotent` | boolean | No | `true` | Return success=true, action=noop when already absent |

## Examples

```python
# Delete an address
{"url": "/pm/config/adom/root/obj/firewall/address/web-01"}

# Delete a policy
{"url": "/pm/config/adom/root/pkg/howard-sdwan-spoke-1/firewall/policy/7"}

# Delete a VIP
{"url": "/pm/config/adom/root/obj/firewall/vip/web-vip"}

# Fail if absent (non-idempotent)
{"url": "/pm/config/adom/root/obj/firewall/address/maybe", "idempotent": false}
```

## Interpreting Results

```json
{"success": true, "action": "deleted", "url": "/pm/config/adom/root/obj/firewall/address/web-01"}
```

| `action` | Meaning |
|---|---|
| `deleted` | Object existed and was removed |
| `noop` | Object was already absent, no action taken (idempotent mode) |

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG {'code': -3, ...}` | Object does not exist (when idempotent=false) | Set `idempotent: true` for cleanup flows |
| `FMG {'code': -11, ...}` | No permission | Admin profile needs rpc-permit read-write |
| `FMG {'code': -6, ...}` | Invalid URL | Verify path + special-character escaping |
| `FMG {'code': -23, ...}` | Object referenced elsewhere | The object is in use (e.g. address referenced by a policy). Delete the referrer first. |

## Pairs With

- `fortimanager-object-create` — inverse operation
- `fortimanager-object-update` — modify instead of remove
- `fortimanager-policy-list` / `firewall-address-list` — find references before deleting
