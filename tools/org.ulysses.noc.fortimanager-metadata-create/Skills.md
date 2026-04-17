# FortiManager Metadata Create — Skills

## How to Call

Use this tool when:
- Defining a variable for use across device templates — e.g. `LAN_SUBNET`, `BGP_LOOPBACK`, `MPLS_IP`
- MSSP workflow: one policy package + per-device variable values = customized deploys
- Blueprint-driven onboarding

**Example prompts:**
- "Create a variable `LAN_SUBNET` with default 10.0.0.0/24"
- "Add metadata `BGP_LOOPBACK` in root ADOM"
- "Define `HOSTNAME_PREFIX` with default 'branch'"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | No | `root` | ADOM |
| `name` | string | Yes | — | Variable name |
| `default_value` | string | Yes | — | Default — **MUST be a string**, even for numeric values |
| `description` | string | No | "" | Human description |
| `overwrite` | boolean | No | `false` | Update if exists |

## Interpreting Results

```json
{"success": true, "action": "created", "name": "LAN_SUBNET", "adom": "root"}
```

## Example

```python
{
  "fmg_host": "192.168.215.17",
  "adom": "root",
  "name": "LAN_SUBNET",
  "default_value": "10.0.0.0/24",
  "description": "Per-site LAN subnet"
}
```

## Notes

- **Value must be a string.** FMG rejects numeric values — always stringify (`"1"` not `1`).
- Variables are referenced in FMG templates/scripts as `$(VARNAME)`.
- Use `fortimanager-metadata-set-device` to override per-device at install time.

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `already exists ... Set overwrite=true` | Name collision | Pass `overwrite: true` or pick different name |
| `FMG {'code': -6, ...}` | Bad URL / permission | Verify admin `rpc-permit read-write` |
| `FMG {'code': -10, ...}` | Invalid data | Ensure `default_value` is a string |

## Pairs With

- `fortimanager-metadata-set-device` — assign per-device values (the reason variables exist)
- `fortimanager-metadata-get-device` — audit values for a specific device
- `fortimanager-policy-package-install` — install time is when substitution happens
