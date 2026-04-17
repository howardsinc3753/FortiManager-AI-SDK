#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Metadata Get Device

List all metadata variables with the values a specific device will see.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    device = params.get("device")
    if not device:
        return {"success": False, "error": "Missing required parameter: device"}
    adom = params.get("adom", "root")
    vdom = params.get("vdom", "global")
    include_all = bool(params.get("include_default_only", True))

    try:
        client = FortiManagerClient(host=fmg_host)

        # Fetch all variables with dynamic_mapping inlined.
        # We pull the whole table and filter client-side for clarity.
        resp = client.get(
            f"/pm/config/adom/{adom}/obj/fmg/variable",
            fields=["name", "value", "description"],
        )
        result = resp.get("result", [{}])[0]
        status = result.get("status") or {}
        if status.get("code") != 0:
            return {"success": False, "error": f"FMG {status}"}
        variables: List[Dict[str, Any]] = result.get("data") or []

        # For each variable, fetch its mappings (sub-path)
        out: List[Dict[str, Any]] = []
        for var in variables:
            name = var.get("name")
            default_value = var.get("value")
            mapped_value: Optional[str] = None

            mapping_resp = client.get(
                f"/pm/config/adom/{adom}/obj/fmg/variable/{name}/dynamic_mapping"
            )
            mapping_data = mapping_resp.get("result", [{}])[0].get("data") or []
            for entry in mapping_data:
                scope = entry.get("_scope") or []
                for s in scope:
                    if s.get("name") == device and s.get("vdom") == vdom:
                        mapped_value = entry.get("value")
                        break
                if mapped_value is not None:
                    break

            if mapped_value is None and not include_all:
                continue

            effective = mapped_value if mapped_value is not None else default_value
            out.append({
                "name": name,
                "default_value": default_value,
                "mapped_value": mapped_value,
                "effective_value": effective,
                "is_overridden": mapped_value is not None,
            })

        return {
            "success": True,
            "device": device,
            "vdom": vdom,
            "adom": adom,
            "variable_count": len(out),
            "variables": out,
        }

    except Exception as e:
        logger.exception("metadata-get-device failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host, "adom": "root",
        "device": "howard-sdwan-spoke-1", "vdom": "global",
    })), indent=2))
