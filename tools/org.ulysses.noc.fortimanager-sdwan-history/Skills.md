# FortiManager SD-WAN History — Skills

## How to Call

Use this tool when:
- Partner needs **historical** SD-WAN trend data (last hour, last day, last week)
- SLA violation audits — "did we breach the latency threshold on port1 overnight?"
- Bandwidth trending — "how much traffic crossed HUB1-VPN1 yesterday?"
- Flap detection — "did any interfaces bounce in the last 4 hours?"
- Sizing / capacity planning

For **live current state**, use `fortimanager-device-monitor-proxy` with
`/api/v2/monitor/virtual-wan/health-check` instead — this tool is for trend.

**Example prompts:**
- "Show the SLA trend for howard-sdwan-spoke-1 for the last hour"
- "How much traffic crossed HUB1-VPN1 today?"
- "Did port1 have any packet loss in the last 24 hours?"

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `device` | string | Yes | — | Managed device name |
| `metric` | string | Yes | — | `sla` or `interface` |
| `time_window_sec` | integer | No | `3600` | Last N seconds (ignored if `start_tm` set) |
| `start_tm` | integer | No | — | Explicit unix start (optional) |
| `end_tm` | integer | No | now | Explicit unix end (optional) |
| `interfaces` | array | No | — | Filter to specific interface names |
| `max_samples_per_interface` | integer | No | `200` | Trim raw time-series to this cap |

## Metric Modes

### `sla` — SLA Monitor History
Returns jitter, latency, packet loss, and link state over time. One entry per (SLA monitor, interface) pair.

### `interface` — Interface Bandwidth History
Returns rx/tx bandwidth (bps) and cumulative byte counters over time. One entry per interface.

## Interpreting Results

### SLA output
```json
{
  "success": true,
  "device": "spoke-01",
  "metric": "sla",
  "window": {"start": 1707250119, "end": 1707253719, "duration_sec": 3600},
  "entry_count": 2,
  "interfaces": [
    {
      "name": "port1",
      "sla_name": "HUB_Health",
      "sample_count": 60,
      "samples": [
        {"timestamp": 1707250158, "value": {"jitter": 0.19, "latency": 6.0, "link": "up", "packetloss": 0.0}},
        ...
      ],
      "summary": {
        "sample_count": 60,
        "avg_latency_ms": 8.3, "max_latency_ms": 12.1,
        "avg_jitter_ms": 0.4,  "max_jitter_ms": 1.2,
        "avg_packetloss_pct": 0.0, "max_packetloss_pct": 0.0,
        "link_up_pct": 1.0
      }
    }
  ]
}
```

### Interface output summary
```json
"summary": {
  "sample_count": 60,
  "avg_rx_bandwidth_bps": 659,
  "max_rx_bandwidth_bps": 1200,
  "avg_tx_bandwidth_bps": 659,
  "avg_bi_bandwidth_bps": 1318,
  "total_rx_bytes_delta": 52300,
  "total_tx_bytes_delta": 51800
}
```

## Example

```python
execute_certified_tool(
    canonical_id="org.ulysses.noc.fortimanager-sdwan-history/1.0.0",
    parameters={
        "fmg_host": "192.168.215.17",
        "device": "howard-sdwan-spoke-1",
        "metric": "sla",
        "time_window_sec": 3600,
        "interfaces": ["port1", "HUB1-VPN1"]
    }
)
```

## When You Get Empty Data

`entry_count: 0` with a `note` field returned = **FMG isn't populating its SD-WAN RTM database yet**.

**Fix — enable SD-WAN Monitoring History on FMG:**
> https://docs.fortinet.com/document/fortimanager/7.6.6/administration-guide/302510/enabling-sd-wan-monitoring-history

Typical CLI (verify exact syntax per doc):
```
config system sql
  set device-sdwan enable
end
```

Then wait 5–15 min for FMG to poll + store data.

**Don't block on this for live state** — use `fortimanager-device-monitor-proxy` with `/api/v2/monitor/virtual-wan/health-check` for real-time SD-WAN data even when RTM is empty.

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `entry_count: 0` + `note` returned | RTM not populated for this device | Enable SD-WAN history per docs link above |
| `FMG {'code': -11, ...}` | No permission | Admin profile needs rpc-permit read-write |
| `FMG {'code': -3, ...}` | Device not found or not managed | Verify with `fortimanager-device-list` |
| `Invalid metric` | Bad `metric` param | Use `sla` or `interface` |

## Pairs With

- `fortimanager-device-monitor-proxy` — live state via `/api/v2/monitor/virtual-wan/health-check`
- `fortimanager-device-list` — find candidate SD-WAN devices first
- `fortimanager-object-list` on `.../system/virtual-wan-link` — config inspection
