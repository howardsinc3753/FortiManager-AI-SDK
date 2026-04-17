#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Object Member Update

Atomic add/remove/clear on group-type /member sub-paths.

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
    mode = (params.get("mode") or "").lower()
    if mode not in {"add", "remove", "clear"}:
        return {"success": False, "error": f"Invalid mode {mode!r}. Use: add | remove | clear"}
    members = params.get("members") or []

    if mode in {"add", "remove"} and not members:
        return {"success": False, "error": f"mode={mode} requires non-empty 'members'"}
    if not url.rstrip("/").endswith("/member"):
        return {"success": False, "error": "url must end with /member sub-path"}

    try:
        client = FortiManagerClient(host=fmg_host)

        if mode == "clear":
            # Use FMG 'unset' method to wipe the entire member list atomically
            payload = {
                "id": client._next_id(),
                "method": "unset",
                "params": [{"url": url}],
            }
            if client.auth_method == "session" and not client.session:
                client.login()
            if client.session:
                payload["session"] = client.session
            resp = client._request(payload)
        else:
            # 'add' appends; 'delete' removes by name
            method = "add" if mode == "add" else "delete"
            resp = client.call(method, url, data=list(members))

        status = resp.get("result", [{}])[0].get("status") or {}
        if status.get("code") != 0:
            return {
                "success": False,
                "action": mode,
                "url": url,
                "error": f"FMG {status}",
            }

        return {
            "success": True,
            "action": mode,
            "url": url,
            "members_affected": members if mode in {"add", "remove"} else [],
        }

    except Exception as e:
        logger.exception("object-member-update failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    # Default smoke: add the fqdn to sdk-addrgrp-test
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host,
        "url": "/pm/config/adom/root/obj/firewall/addrgrp/sdk-addrgrp-test/member",
        "mode": "add",
        "members": ["sdk-range-test"],
    })), indent=2))
