#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager ADOM List

List all Administrative Domains (ADOMs) on a FortiManager.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
import os
from pathlib import Path
from typing import Any, Dict, Optional

# Allow running either as a certified tool (self-contained) or from the SDK dir
_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}

    filter_state = params.get("filter_state")
    name_like = (params.get("name_like") or "").lower()

    try:
        client = FortiManagerClient(host=fmg_host)
        resp = client.get(
            "/dvmdb/adom",
            fields=["name", "os_ver", "mr", "state", "_dev_count"],
        )
        result = resp.get("result", [{}])[0]
        status = result.get("status", {})
        if status.get("code") != 0:
            return {"success": False, "error": f"FMG {status}"}

        adoms = result.get("data") or []
        if filter_state is not None:
            adoms = [a for a in adoms if a.get("state") == filter_state]
        if name_like:
            adoms = [a for a in adoms if name_like in (a.get("name") or "").lower()]

        normalized = [
            {
                "name": a.get("name"),
                "os_ver": str(a.get("os_ver")),
                "mr": a.get("mr"),
                "state": a.get("state"),
                "device_count": a.get("_dev_count", 0),
            }
            for a in adoms
        ]
        return {"success": True, "count": len(normalized), "adoms": normalized}

    except Exception as e:
        logger.exception("adom-list failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    print(json.dumps(asyncio.run(execute({"fmg_host": host})), indent=2))
