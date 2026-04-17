#!/usr/bin/env python3
from __future__ import annotations
"""
{{NAME}}

TODO: one-sentence purpose.

Author: {{ORG}}
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

    adom = params.get("adom", "root")

    try:
        client = FortiManagerClient(host=fmg_host)

        # TODO: replace with your actual JSON-RPC call
        resp = client.get(f"/dvmdb/adom/{adom}/device", fields=["name", "ip"])

        result = resp.get("result", [{}])[0]
        status = result.get("status", {})
        if status.get("code") != 0:
            return {"success": False, "error": f"FMG {status}"}

        data = result.get("data") or []
        return {"success": True, "count": len(data), "data": data}

    except Exception as e:
        logger.exception("tool failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    print(json.dumps(asyncio.run(execute({"fmg_host": host})), indent=2))
