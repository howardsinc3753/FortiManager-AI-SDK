#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Object Create

Generic create for ANY FMG object type via method=add.

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


def _escape_name(name: str) -> str:
    """FMG requires `\\/` for slash-in-name entity paths."""
    return name.replace("/", "\\/")


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    url = params.get("url")
    if not url:
        return {"success": False, "error": "Missing required parameter: url"}
    data = params.get("data")
    if data is None:
        return {"success": False, "error": "Missing required parameter: data"}

    overwrite = bool(params.get("overwrite", False))
    as_list = bool(params.get("as_list", False))
    name = data.get("name") if isinstance(data, dict) else None

    try:
        client = FortiManagerClient(host=fmg_host)

        # Pre-check if named entity exists
        exists = False
        if name:
            named_url = f"{url.rstrip('/')}/{_escape_name(name)}"
            probe = client.get(named_url, fields=["name"])
            code = (probe.get("result", [{}])[0].get("status") or {}).get("code")
            exists = code == 0

        if exists and not overwrite:
            return {
                "success": False,
                "action": "noop",
                "url": url,
                "name": name,
                "error": f"Object {name!r} already exists at {url}. Set overwrite=true to replace.",
            }

        payload_data = [data] if as_list else data
        if exists:
            # Use update on named URL to avoid table-wipe
            named_url = f"{url.rstrip('/')}/{_escape_name(name)}"
            resp = client.call("update", named_url, data=data)
            action = "updated"
        else:
            resp = client.call("add", url, data=payload_data)
            action = "created"

        status = resp.get("result", [{}])[0].get("status") or {}
        if status.get("code") != 0:
            return {
                "success": False,
                "action": action,
                "url": url,
                "name": name,
                "error": f"FMG {status}",
            }

        return {"success": True, "action": action, "url": url, "name": name}

    except Exception as e:
        logger.exception("object-create failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    # Default smoke test: create a VIP using only the generic primitive
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host,
        "url": "/pm/config/adom/root/obj/firewall/vip",
        "data": {
            "name": "sdk-vip-test",
            "extintf": ["any"],
            "extip": ["203.0.113.10"],
            "mappedip": ["10.1.1.5"],
            "portforward": "enable",
            "protocol": "tcp",
            "extport": "443",
            "mappedport": "443",
            "status": "enable",
            "comment": "SDK smoke: VIP via generic object-create",
        },
        "overwrite": True,
    })), indent=2))
