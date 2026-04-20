# FortiManager Model Device Create — Skills

## How to Call

Use this tool when:
- Staging a new FortiGate in FMG BEFORE the physical device arrives (MSSP pre-build flow)
- Placeholder device for SDWAN Template + System Template assignment, so install happens automatically when the real device phones home via FGFM
- Zero-touch-like workflow via FMG alone (no FortiZTP dependency)

**Example prompts:**
- "Create a model device for site 5 — platform FortiGate-60F, serial FGT60FTK12345678"
- "Pre-stage a spoke for customer Acme in ADOM Customer_101"
- "Add a placeholder FortiGate-201F with serial FGT201F..."

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | Yes | — | ADOM to register device in |
| `name` | string | Yes | — | Device name (mkey for later ops) |
| `sn` | string | Yes | — | Serial number (synthetic OK for staging) |
| `platform` | string | Yes | — | HW preferred — `FortiGate-60F`, `FortiGate-201F`, `FortiWiFi-50G-5G` etc. |
| `os_type` | integer | No | `0` | 0 = FortiOS |
| `os_ver` | integer | No | `7` | Major version |
| `mr` | integer | No | `6` | Minor version (6 for 7.6.x) |
| `adm_usr` | string | No | `admin` | Admin username |
| `description` | string | No | "" | Free-form |
| `mgmt_mode` | integer | No | `3` | 3 = FGFM |
| `blueprint` | string | No | — | Name of devprof/blueprint to pre-apply |
| `extra_commands` | array | No | — | List of follow-on JSON-RPC ops |
| `wait` | boolean | No | `true` | Poll task until terminal |
| `max_wait_sec` | integer | No | `60` | |

## Known Gotchas

- **VM platforms often blocked**: `FortiGate-VM64-KVM` returns `code: -20084 'VM device is not allowed'` unless FortiFlex entitlement is applied. Use HW platforms for staging.
- **Delete uses different endpoint**: `exec /dvm/cmd/del/device` (not `delete /dvmdb/...`) — generic `object-delete` returns `code -9` on DVM devices.

## Interpreting Results

```json
{
  "success": true,
  "name": "spoke-05",
  "adom": "Customer_101",
  "task_id": 91,
  "state": "done",
  "device_oid": 190
}
```

`device_oid` confirms the device is now in DVM.

## Example

```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-model-device-create/1.0.0",
    parameters={
        "fmg_host": "192.168.215.17",
        "adom": "Customer_101",
        "name": "spoke-05",
        "sn": "FGT60FTK99000005",
        "platform": "FortiGate-60F",
        "description": "Model device for site 5, SDWAN spoke"
    }
)
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `FMG exec error: {'code': -20084, ...}` | VM platform blocked by license | Use HW platform or apply FortiFlex entitlement |
| `FMG exec error: {'code': -3, ...}` | ADOM doesn't exist | Create ADOM first |
| `Device not in DVM after create` | Task completed but DVM didn't populate | Check FMG logs |

## Pairs With

- `metadata-set-device` — populate per-device variables after create
- `device-settings-install` — push templated config to the model device
- `object-list` — verify device appears in `/dvmdb/adom/{adom}/device`
