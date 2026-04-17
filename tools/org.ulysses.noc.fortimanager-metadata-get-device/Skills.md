# FortiManager Metadata Get Device — Skills

## How to Call

Use this tool when:
- Auditing what variable values a specific device will see at install time
- Debugging template substitution ("why did LAN_SUBNET come out as X?")
- Confirming a per-device override was applied correctly
- Comparing two devices' variable sets side-by-side

**Example prompts:**
- "What values will howard-sdwan-spoke-1 see for all variables?"
- "Show me the overridden variables for branch-01"
- "Does the device have LAN_SUBNET set?"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | ADOM |
| `device` | string | Yes | — | Managed device name |
| `vdom` | string | No | `global` | `global` for device scope, or a VDOM name |
| `include_default_only` | boolean | No | `true` | Include vars without per-device overrides (show default) |

## Interpreting Results

```json
{
  "success": true,
  "device": "howard-sdwan-spoke-1",
  "vdom": "global",
  "adom": "root",
  "variable_count": 3,
  "variables": [
    {
      "name": "SDK_LAN_SUBNET",
      "default_value": "192.168.1.0/24",
      "mapped_value": "172.16.0.0/24",
      "effective_value": "172.16.0.0/24",
      "is_overridden": true
    },
    {
      "name": "HOSTNAME_PREFIX",
      "default_value": "branch",
      "mapped_value": null,
      "effective_value": "branch",
      "is_overridden": false
    }
  ]
}
```

**Field meanings:**
- `default_value`: the variable's ADOM-wide default
- `mapped_value`: the per-device override (null if none set)
- `effective_value`: what the device ACTUALLY sees at install time (mapped ?? default)
- `is_overridden`: `true` when device has a specific mapping

## Example

**User:** "What variables will the spoke see when I install the package?"

**Tool call:**
```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-metadata-get-device/1.0.0",
    parameters={
        "fmg_host": "192.168.215.17",
        "device": "howard-sdwan-spoke-1",
        "vdom": "global"
    }
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `success: true` but empty `variables[]` | ADOM has no variables defined yet | Use `metadata-create` to add some |
| `FMG {'code': -6, ...}` | Invalid URL | Check ADOM spelling |

## Pairs With

- `fortimanager-metadata-create` — defines the variables this tool reports on
- `fortimanager-metadata-set-device` — source of `mapped_value`
- `fortimanager-policy-package-install` — uses these effective values at install
