#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Script Create

Create or update a FortiManager CLI/TCL script.

URL: pm/config/adom/{adom}/obj/fmg/script (GUI-verified path).
NOTE: The legacy /dvmdb/adom/{adom}/script path returns -6 "Invalid url" on
writes for API users. The pm/config/.../obj/fmg/script path is the canonical
one used by FMG's own UI.

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

_TARGET_TO_INT = {"device_database": 0, "remote_device": 1, "adom_database": 2}
_TYPE_TO_INT = {"cli": 1, "tcl": 2, "cligrp": 5}


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    name = params.get("name")
    content = params.get("content")
    if not name:
        return {"success": False, "error": "Missing required parameter: name"}
    if not content:
        return {"success": False, "error": "Missing required parameter: content"}

    adom = params.get("adom", "root")
    target_str = params.get("target", "remote_device")
    type_str = params.get("type", "cli")
    desc = params.get("desc", "") or ""
    overwrite = bool(params.get("overwrite", False))

    if target_str not in _TARGET_TO_INT:
        return {"success": False, "error": f"Invalid target: {target_str!r}"}
    if type_str not in _TYPE_TO_INT:
        return {"success": False, "error": f"Invalid type: {type_str!r}"}

    data = {
        "name": name,
        "content": content,
        "target": _TARGET_TO_INT[target_str],
        "type": _TYPE_TO_INT[type_str],
        "desc": desc,
    }
    collection_url = f"pm/config/adom/{adom}/obj/fmg/script"
    named_url = f"{collection_url}/{name}"

    try:
        client = FortiManagerClient(host=fmg_host)

        # Check existence
        existing_resp = client.get(named_url, fields=["name"])
        existing_status = existing_resp.get("result", [{}])[0].get("status") or {}
        exists = existing_status.get("code") == 0

        if exists and not overwrite:
            return {
                "success": False,
                "action": "noop",
                "error": f"Script {name!r} already exists in ADOM {adom!r}. Set overwrite=true to replace.",
            }

        if exists:
            resp = client.call("update", named_url, data=data)
            action = "updated"
        else:
            resp = client.call("add", collection_url, data=data)
            action = "created"

        status = resp.get("result", [{}])[0].get("status") or {}
        if status.get("code") != 0:
            return {
                "success": False,
                "action": action,
                "error": f"FMG {status}",
            }

        return {
            "success": True,
            "action": action,
            "canonical_id": f"{adom}/{name}",
            "script": {
                "name": name,
                "adom": adom,
                "target": target_str,
                "type": type_str,
            },
        }

    except Exception as e:
        logger.exception("script-create failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    name = sys.argv[2] if len(sys.argv) > 2 else "sdk-cli-test"
    content = sys.argv[3] if len(sys.argv) > 3 else "get system status"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host, "adom": "root", "name": name,
        "content": content, "overwrite": True,
    })), indent=2))
