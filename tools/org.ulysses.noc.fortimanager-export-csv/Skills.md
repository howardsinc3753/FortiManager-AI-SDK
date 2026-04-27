# FortiManager Export CSV — Skills

## How to Call

Use this tool when:
- User asks to "export devices to CSV / Excel"
- Reporting / handover deliverable for a tenant
- Bulk audit needing spreadsheet review
- Migration data extraction (devices, addresses, policies, services)

**FMG has NO native CSV export endpoint** — every "Export" button in the GUI is client-side conversion of JSON. This tool replicates that pattern.

**Example prompts:**
- "Export all devices in Customer_101 ADOM to CSV"
- "Give me a CSV of firewall addresses for tenant"
- "Dump policies in the default package as CSV"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `url` | string | Yes | — | Any FMG list URL |
| `fields` | array | No | — | Limit + order columns. If omitted, dumps all keys. |
| `filter` | array | No | — | Server-side filter passthrough |
| `range` | array | No | `[0, max_rows]` | Pagination |
| `verbose` | integer | No | — | 1 = symbolic enums (recommended for human-readable CSV) |
| `output_path` | string | No | — | Write to file. If omitted, only returns preview. |
| `max_rows` | integer | No | `10000` | Cap |
| `preview_rows` | integer | No | `5` | Preview rows shown in response |

## Device Export Scope (3 modes)

The `url` parameter controls scope. Pick the right one:

| Scope | URL | Returns |
|---|---|---|
| **Fleet-wide** (every FortiGate across every ADOM) | `/dvmdb/device` | All managed devices in one combined list — MSSP-wide inventory |
| **Per-tenant** (one customer / one ADOM) | `/dvmdb/adom/{adom}/device` | Just that ADOM's FortiGates |
| **Single device** | `/dvmdb/adom/{adom}/device/{name}` | One device's full record |

### Per-Tenant Loop Pattern

If the user wants ONE CSV per ADOM (typical MSSP monthly report deliverable):

```python
# 1. List all ADOMs
adoms = adom-list({"fmg_host": fmg})

# 2. Loop and export per-ADOM
for a in adoms["adoms"]:
    export-csv({
        "fmg_host": fmg,
        "url": f"/dvmdb/adom/{a['name']}/device",
        "fields": ["name","ip","platform_str","os_ver","conn_status"],
        "verbose": 1,
        "output_path": f"C:/Reports/{a['name']}_devices.csv"
    })
```

Result: `Customer_101_devices.csv`, `Customer_102_devices.csv`, etc.

## Other Common URLs

| Use case | URL |
|---|---|
| All ADOMs (just metadata, not devices) | `/dvmdb/adom` |
| Firewall addresses | `/pm/config/adom/{adom}/obj/firewall/address` |
| Custom services | `/pm/config/adom/{adom}/obj/firewall/service/custom` |
| Policies in a package | `/pm/config/adom/{adom}/pkg/{pkg}/firewall/policy` |
| Metadata variables | `/pm/config/adom/{adom}/obj/fmg/variable` |

## Interpreting Results

```json
{
  "success": true,
  "url": "/dvmdb/adom/root/device",
  "row_count": 1,
  "columns": ["name","ip","platform_str","os_ver","mr","patch","conn_status","conf_status"],
  "output_path": "C:/exports/devices.csv",
  "bytes_written": 245,
  "csv_preview": "name,ip,platform_str,...\nhoward-sdwan-spoke-1,10.250.250.1,FortiWiFi-50G-5G,..."
}
```

When `output_path` is omitted, `csv_preview` is the only output (good for "show me a sample" requests).

## Examples

**Devices to CSV file:**
```python
{
  "fmg_host": "192.168.215.17",
  "url": "/dvmdb/adom/root/device",
  "fields": ["name", "ip", "platform_str", "os_ver", "conn_status"],
  "verbose": 1,
  "output_path": "C:/Temp/devices.csv"
}
```

**All firewall addresses preview-only:**
```python
{
  "fmg_host": "192.168.215.17",
  "url": "/pm/config/adom/root/obj/firewall/address",
  "fields": ["name", "type", "subnet", "fqdn"],
  "verbose": 1,
  "preview_rows": 10
}
```

## Cell Flattening Rules

- `None` → empty string
- list / tuple → `;`-joined values (e.g. `subnet: ['10.0.0.0','255.0.0.0']` → `10.0.0.0;255.0.0.0`)
- dict → `;`-joined `key=value` pairs

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `URL did not return a list` | URL points to single object, not table | Use a parent collection URL |
| `FMG {'code': -3, ...}` | URL doesn't exist | Verify ADOM/path |
| Write permission denied | output_path not writable | Check folder, fall back to preview-only |
