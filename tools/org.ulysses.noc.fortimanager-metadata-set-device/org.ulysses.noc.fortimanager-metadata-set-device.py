#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Metadata Set Device

Assign per-device values to an FMG variable via dynamic_mapping sub-path.

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


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    name = params.get("name")
    mappings = params.get("mappings") or []
    if not name:
        return {"success": False, "error": "Missing required parameter: name"}
    if not isinstance(mappings, list) or not mappings:
        return {"success": False, "error": "Missing required parameter: mappings (non-empty array)"}

    adom = params.get("adom", "root")
    dynamic_url = f"/pm/config/adom/{adom}/obj/fmg/variable/{name}/dynamic_mapping"

    try:
        client = FortiManagerClient(host=fmg_host)

        results = []
        applied = 0
        for idx, mp in enumerate(mappings):
            if not isinstance(mp, dict):
                results.append({"success": False, "error": f"mapping[{idx}] not a dict"})
                continue
            device = mp.get("device")
            value = mp.get("value")
            vdom = mp.get("vdom") or "global"
            if not device:
                results.append({"success": False, "error": f"mapping[{idx}] missing device"})
                continue
            if value is None:
                results.append({"success": False, "device": device, "vdom": vdom,
                                "error": "missing value"})
                continue
            value_str = str(value)

            named_url = f"{dynamic_url}/{device}/{vdom}"
            # Check existing
            probe = client.get(named_url, fields=["value"])
            exists = (probe.get("result", [{}])[0].get("status") or {}).get("code") == 0

            entry_data = {
                "_scope": [{"name": device, "vdom": vdom}],
                "value": value_str,
            }

            if exists:
                resp = client.call("update", named_url, data={"value": value_str})
            else:
                resp = client.call("add", dynamic_url, data=entry_data)

            status = resp.get("result", [{}])[0].get("status") or {}
            ok = status.get("code") == 0
            results.append({
                "device": device, "vdom": vdom, "value": value_str,
                "success": ok,
                "error": None if ok else f"FMG {status}",
            })
            if ok:
                applied += 1

        return {
            "success": applied == len(mappings),
            "name": name,
            "adom": adom,
            "applied_count": applied,
            "results": results,
        }

    except Exception as e:
        logger.exception("metadata-set-device failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host, "adom": "root", "name": "SDK_LAN_SUBNET",
        "mappings": [
            {"device": "howard-sdwan-spoke-1", "vdom": "global", "value": "10.250.250.0/24"},
        ],
    })), indent=2))
