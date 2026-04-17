# FortiManager Metadata Set Device — Skills

## How to Call

Use this tool when:
- Assigning per-device override values for an FMG metadata variable
- MSSP device blueprint work — each branch gets its own `LAN_SUBNET`, `BGP_LOOPBACK`, etc.
- Bulk value assignment — map N devices in a single call
- Re-scoping a variable (add new device mappings without losing existing ones)

**Example prompts:**
- "Set LAN_SUBNET to 10.1.0.0/24 for branch-01 and 10.2.0.0/24 for branch-02"
- "Add per-device values for BGP_LOOPBACK across 10 spokes"
- "Override HOSTNAME for the dev_001 device"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | ADOM containing the variable |
| `name` | string | Yes | — | Variable name (must already exist) |
| `mappings` | array | Yes | — | List of `{device, vdom, value}` |

**Mapping object:**
| Field | Required | Default | Description |
|---|---|---|---|
| `device` | Yes | — | Managed device name |
| `vdom` | No | `global` | VDOM scope (or `global` for device-level) |
| `value` | Yes | — | Override value (coerced to string) |

## Example

```python
{
  "fmg_host": "192.168.215.17",
  "adom": "root",
  "name": "LAN_SUBNET",
  "mappings": [
    {"device": "branch-01", "vdom": "root", "value": "10.1.0.0/24"},
    {"device": "branch-02", "vdom": "root", "value": "10.2.0.0/24"},
    {"device": "branch-03", "vdom": "global", "value": "10.3.0.0/24"}
  ]
}
```

## Interpreting Results

```json
{
  "success": true,
  "name": "LAN_SUBNET",
  "adom": "root",
  "applied_count": 3,
  "results": [
    {"device": "branch-01", "vdom": "root", "value": "10.1.0.0/24", "success": true, "error": null},
    ...
  ]
}
```

`success: true` only when ALL mappings applied. Partial success returns `success: false` with `applied_count` lower than `len(mappings)`.

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG {'code': -3, ...}` | Variable or device doesn't exist | Check via `metadata-get-device` / `device-list` |
| `mapping[i] missing device` | Mapping entry malformed | Ensure each mapping has `device` + `value` |
| `FMG {'code': -10, ...}` | Value shape invalid | Values MUST be strings — we coerce but double-check |

## Notes

- Variable values MUST be strings in FMG. The tool auto-stringifies numeric inputs.
- `vdom: "global"` = device-level scope; use a VDOM name (e.g. `"root"`) for VDOM-level.
- Existing mappings for OTHER devices are preserved — this tool only touches listed mappings.

## Pairs With

- `fortimanager-metadata-create` — create the variable before mapping values
- `fortimanager-metadata-get-device` — audit what values a device sees
- `fortimanager-policy-package-install` — install-time is when substitution happens
