#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager SD-WAN History

Fetch SLA or interface telemetry from FMG's Real-Time Monitor (RTM) store.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)

_METRIC_CONFIG = {
    "sla": {
        "path": "sd-wan-sla-log",
        "keys": [["name"], ["interface"]],
    },
    "interface": {
        "path": "sd-wan-intf-log",
        "keys": [["interface"]],
    },
}


def _summarize_sla(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not samples:
        return {"sample_count": 0}
    latencies = [s["value"].get("latency") for s in samples
                 if isinstance(s.get("value"), dict) and s["value"].get("latency") is not None]
    jitters = [s["value"].get("jitter") for s in samples
               if isinstance(s.get("value"), dict) and s["value"].get("jitter") is not None]
    ploss = [s["value"].get("packetloss") for s in samples
             if isinstance(s.get("value"), dict) and s["value"].get("packetloss") is not None]
    links_up = sum(1 for s in samples
                   if isinstance(s.get("value"), dict) and s["value"].get("link") == "up")
    return {
        "sample_count": len(samples),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "max_latency_ms": round(max(latencies), 3) if latencies else None,
        "avg_jitter_ms": round(sum(jitters) / len(jitters), 3) if jitters else None,
        "max_jitter_ms": round(max(jitters), 3) if jitters else None,
        "avg_packetloss_pct": round(sum(ploss) / len(ploss), 3) if ploss else None,
        "max_packetloss_pct": round(max(ploss), 3) if ploss else None,
        "link_up_pct": round(links_up / len(samples), 3),
    }


def _summarize_interface(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not samples:
        return {"sample_count": 0}

    def vals(key: str) -> List[float]:
        return [s["value"].get(key) for s in samples
                if isinstance(s.get("value"), dict) and s["value"].get(key) is not None]

    rx_bw = vals("rx_bandwidth")
    tx_bw = vals("tx_bandwidth")
    bi_bw = vals("bi_bandwidth")
    rx_bytes_values = vals("rx_bytes")
    tx_bytes_values = vals("tx_bytes")
    return {
        "sample_count": len(samples),
        "avg_rx_bandwidth_bps": int(sum(rx_bw) / len(rx_bw)) if rx_bw else None,
        "max_rx_bandwidth_bps": int(max(rx_bw)) if rx_bw else None,
        "avg_tx_bandwidth_bps": int(sum(tx_bw) / len(tx_bw)) if tx_bw else None,
        "max_tx_bandwidth_bps": int(max(tx_bw)) if tx_bw else None,
        "avg_bi_bandwidth_bps": int(sum(bi_bw) / len(bi_bw)) if bi_bw else None,
        "total_rx_bytes_delta": (rx_bytes_values[-1] - rx_bytes_values[0]) if len(rx_bytes_values) >= 2 else None,
        "total_tx_bytes_delta": (tx_bytes_values[-1] - tx_bytes_values[0]) if len(tx_bytes_values) >= 2 else None,
    }


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    device = params.get("device")
    if not device:
        return {"success": False, "error": "Missing required parameter: device"}
    metric = (params.get("metric") or "").lower()
    if metric not in _METRIC_CONFIG:
        return {"success": False, "error": f"Invalid metric {metric!r}. Use: sla | interface"}

    now = int(time.time())
    end_tm = int(params.get("end_tm") or now)
    start_tm = params.get("start_tm")
    if start_tm is None:
        window = int(params.get("time_window_sec", 3600))
        start_tm = end_tm - window
    else:
        start_tm = int(start_tm)

    interface_filter = set(params.get("interfaces") or [])
    max_samples = int(params.get("max_samples_per_interface", 200))

    cfg = _METRIC_CONFIG[metric]
    url = f"/rtm/global/rhistory/monitor/{cfg['path']}/device/{device}"

    try:
        client = FortiManagerClient(host=fmg_host)
        if client.auth_method == "session" and not client.session:
            client.login()

        payload: Dict[str, Any] = {
            "id": client._next_id(),
            "method": "get",
            "params": [{
                "url": url,
                "filter": {
                    "key": cfg["keys"],
                    "timestamp": [["start", "==", start_tm], ["end", "==", end_tm]],
                },
            }],
        }
        if client.session:
            payload["session"] = client.session

        resp = client._request(payload)
        result = resp.get("result", [{}])[0]
        status = result.get("status") or {}
        if status.get("code") != 0:
            return {"success": False, "device": device, "metric": metric,
                    "error": f"FMG {status}"}

        raw = result.get("data") or []
        summarize = _summarize_sla if metric == "sla" else _summarize_interface

        interfaces: List[Dict[str, Any]] = []
        for entry in raw:
            iface_name = entry.get("interface") or ""
            if interface_filter and iface_name not in interface_filter:
                continue
            samples = entry.get("log") or []
            capped = samples[-max_samples:]
            interfaces.append({
                "name": iface_name,
                "sla_name": entry.get("name") or None,
                "sample_count": len(samples),
                "samples": capped,
                "summary": summarize(samples),
            })

        out: Dict[str, Any] = {
            "success": True,
            "device": device,
            "metric": metric,
            "window": {
                "start": start_tm,
                "end": end_tm,
                "duration_sec": end_tm - start_tm,
            },
            "entry_count": len(interfaces),
            "interfaces": interfaces,
        }
        if not interfaces:
            window_sec = end_tm - start_tm
            if window_sec < 300:
                out["note"] = (
                    f"No RTM samples in this narrow {window_sec}s window. "
                    "FMG RTM writes per-minute buckets — try a wider window "
                    "(e.g. time_window_sec=900 for 15 minutes) before concluding "
                    "RTM is not populated. If wider windows also return empty, "
                    "SD-WAN Monitoring History may not be enabled: "
                    "'config system admin setting / set sdwan-monitor-history enable'. "
                    "For live current state, use fortimanager-device-monitor-proxy "
                    "with /api/v2/monitor/virtual-wan/health-check."
                )
            else:
                out["note"] = (
                    f"No RTM data in a {window_sec}s window. SD-WAN Monitoring "
                    "History is likely not enabled on FMG. Enable via: "
                    "'config system admin setting / set sdwan-monitor-history enable', "
                    "then wait 5-15min. For live current state right now, use "
                    "fortimanager-device-monitor-proxy with "
                    "/api/v2/monitor/virtual-wan/health-check."
                )
        return out

    except Exception as e:
        logger.exception("sdwan-history failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    device = sys.argv[2] if len(sys.argv) > 2 else "howard-sdwan-spoke-1"
    metric = sys.argv[3] if len(sys.argv) > 3 else "sla"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host, "device": device, "metric": metric,
        "time_window_sec": 86400 * 7,  # 7d window for lab (RTM may be sparse)
    })), indent=2))
