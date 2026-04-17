#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Device Monitor Proxy

Forward a FortiGate /api/v2/monitor/* (or cmdb) call through FMG's
/sys/proxy/json to one or more devices/groups.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {"get", "post", "put", "delete"}


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    resource = params.get("resource")
    if not resource:
        return {"success": False, "error": "Missing required parameter: resource"}
    if not resource.startswith("/"):
        resource = "/" + resource
    targets = params.get("targets") or []
    if not targets or not isinstance(targets, list):
        return {"success": False, "error": "Missing required parameter: targets (non-empty array)"}

    action = (params.get("action") or "get").lower()
    if action not in _VALID_ACTIONS:
        return {"success": False, "error": f"Invalid action: {action!r}. Use: {sorted(_VALID_ACTIONS)}"}
    payload = params.get("payload")
    timeout = int(params.get("timeout_sec", 30))

    body: Dict[str, Any] = {
        "action": action,
        "resource": resource,
        "target": list(targets),
        "timeout": timeout,
    }
    if payload is not None and action in {"post", "put"}:
        body["payload"] = payload

    try:
        client = FortiManagerClient(host=fmg_host)
        resp = client.exec("/sys/proxy/json", data=body)
        result = resp.get("result", [{}])[0]
        outer_status = result.get("status") or {}
        if outer_status.get("code") != 0:
            return {
                "success": False, "resource": resource,
                "error": f"FMG proxy error: {outer_status}",
            }

        per_target = result.get("data") or []
        if not isinstance(per_target, list):
            per_target = [per_target]

        normalized: List[Dict[str, Any]] = []
        success_count = 0
        for entry in per_target:
            target_name = entry.get("target") or "unknown"
            status = entry.get("status") or {}
            response = entry.get("response") or {}
            ok = status.get("code") == 0 and (response.get("status") == "success" or not response)
            http_status = response.get("http_status") if isinstance(response, dict) else None
            err_msg = None
            if not ok:
                err_msg = status.get("message") or response.get("status") or "unknown error"
            normalized.append({
                "target": target_name,
                "success": bool(ok),
                "http_status": http_status,
                "response": response,
                "error": err_msg,
            })
            if ok:
                success_count += 1

        return {
            "success": len(normalized) > 0 and success_count == len(normalized),
            "resource": resource,
            "target_count": len(normalized),
            "success_count": success_count,
            "results": normalized,
        }

    except Exception as e:
        logger.exception("device-monitor-proxy failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    resource = sys.argv[2] if len(sys.argv) > 2 else "/api/v2/monitor/system/interface"
    target = sys.argv[3] if len(sys.argv) > 3 else "/adom/root/device/howard-sdwan-spoke-1"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host, "adom": "root",
        "resource": resource, "action": "get",
        "targets": [target],
    })), indent=2)[:4000])
