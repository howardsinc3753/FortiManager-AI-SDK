#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Metadata Create

Create an FMG metadata variable at /pm/config/adom/{adom}/obj/fmg/variable.

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
    default_value = params.get("default_value")
    if not name:
        return {"success": False, "error": "Missing required parameter: name"}
    if default_value is None:
        return {"success": False, "error": "Missing required parameter: default_value"}

    adom = params.get("adom", "root")
    description = params.get("description", "") or ""
    overwrite = bool(params.get("overwrite", False))

    # FMG requires value to be a string — enforce
    value = str(default_value)

    data = {"name": name, "value": value}
    if description:
        data["description"] = description

    collection_url = f"/pm/config/adom/{adom}/obj/fmg/variable"
    named_url = f"{collection_url}/{name}"

    try:
        client = FortiManagerClient(host=fmg_host)

        # Existence pre-check
        probe = client.get(named_url, fields=["name"])
        exists = (probe.get("result", [{}])[0].get("status") or {}).get("code") == 0

        if exists and not overwrite:
            return {
                "success": False,
                "action": "noop",
                "name": name,
                "adom": adom,
                "error": f"Metadata {name!r} already exists in ADOM {adom!r}. Set overwrite=true to update.",
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
                "name": name,
                "adom": adom,
                "error": f"FMG {status}",
            }

        return {"success": True, "action": action, "name": name, "adom": adom}

    except Exception as e:
        logger.exception("metadata-create failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host, "adom": "root",
        "name": "SDK_LAN_SUBNET",
        "default_value": "10.0.0.0/24",
        "description": "Per-site LAN subnet (SDK smoke test)",
        "overwrite": True,
    })), indent=2))
