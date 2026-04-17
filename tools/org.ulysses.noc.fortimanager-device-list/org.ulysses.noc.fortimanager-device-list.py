#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Device List

List managed FortiGate devices in an ADOM.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)

# FMG conn_status: 0=unknown, 1=up, 2=down
_CONN_LABEL = {0: "unknown", 1: "up", 2: "down"}


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}

    adom = params.get("adom", "root")
    name_like = (params.get("name_like") or "").lower()
    platform_like = (params.get("platform_like") or "").lower()
    only_down = bool(params.get("only_down", False))

    try:
        client = FortiManagerClient(host=fmg_host)
        resp = client.get(
            f"/dvmdb/adom/{adom}/device",
            fields=[
                "name", "hostname", "ip", "platform_str", "os_ver", "mr",
                "patch", "build", "ha_mode", "conn_status", "conf_status",
                "mgt_vdom", "desc",
            ],
        )
        result = resp.get("result", [{}])[0]
        status = result.get("status", {})
        if status.get("code") != 0:
            return {"success": False, "error": f"FMG {status}"}

        raw = result.get("data") or []
        devices = []
        for d in raw:
            conn = d.get("conn_status", 0)
            if only_down and conn == 1:
                continue
            if name_like and name_like not in (d.get("name") or "").lower():
                continue
            if platform_like and platform_like not in (d.get("platform_str") or "").lower():
                continue
            devices.append({
                "name": d.get("name"),
                "hostname": d.get("hostname"),
                "ip": d.get("ip"),
                "platform": d.get("platform_str"),
                "os_version": f'{d.get("os_ver")}.{d.get("mr")}.{d.get("patch")}',
                "build": d.get("build"),
                "ha_mode": d.get("ha_mode"),
                "conn_status": conn,
                "conn_status_label": _CONN_LABEL.get(conn, str(conn)),
                "conf_status": d.get("conf_status"),
                "mgt_vdom": d.get("mgt_vdom"),
                "description": d.get("desc") or "",
            })

        return {"success": True, "count": len(devices), "devices": devices}

    except Exception as e:
        logger.exception("device-list failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    adom = sys.argv[2] if len(sys.argv) > 2 else "root"
    print(json.dumps(asyncio.run(execute({"fmg_host": host, "adom": adom})), indent=2))
