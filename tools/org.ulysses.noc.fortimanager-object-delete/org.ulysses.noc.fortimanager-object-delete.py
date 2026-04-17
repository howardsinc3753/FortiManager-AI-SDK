#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Object Delete

Generic delete for any FMG object via method=delete on a named-entity URL.

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
    url = params.get("url")
    if not url:
        return {"success": False, "error": "Missing required parameter: url"}
    idempotent = bool(params.get("idempotent", True))

    try:
        client = FortiManagerClient(host=fmg_host)

        if idempotent:
            probe = client.get(url, fields=["name"])
            code = (probe.get("result", [{}])[0].get("status") or {}).get("code")
            if code == -3:
                return {"success": True, "action": "noop", "url": url}

        resp = client.call("delete", url)
        status = resp.get("result", [{}])[0].get("status") or {}
        if status.get("code") != 0:
            return {"success": False, "url": url, "error": f"FMG {status}"}
        return {"success": True, "action": "deleted", "url": url}

    except Exception as e:
        logger.exception("object-delete failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    # Default smoke: delete the wildcard-fqdn we created earlier
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host,
        "url": "/pm/config/adom/root/obj/firewall/wildcard-fqdn/custom/sdk-wildcard-test",
    })), indent=2))
