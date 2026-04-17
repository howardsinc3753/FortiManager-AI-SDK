#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Policy Package List

List firewall policy packages in an ADOM.

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

    adom = params.get("adom", "root")
    name_like = (params.get("name_like") or "").lower()
    include_folders = params.get("include_folders", True)

    try:
        client = FortiManagerClient(host=fmg_host)
        resp = client.get(f"/pm/pkg/adom/{adom}")
        result = resp.get("result", [{}])[0]
        status = result.get("status", {})
        if status.get("code") != 0:
            return {"success": False, "error": f"FMG {status}"}

        raw = result.get("data") or []
        packages = []
        for p in raw:
            ptype = p.get("type") or ""
            if not include_folders and ptype == "folder":
                continue
            if name_like and name_like not in (p.get("name") or "").lower():
                continue
            settings = p.get("package settings") or {}
            packages.append({
                "name": p.get("name"),
                "type": ptype,
                "oid": p.get("oid"),
                "obj_version": p.get("obj ver"),
                "central_nat": settings.get("central-nat"),
                "ngfw_mode": settings.get("ngfw-mode"),
                "consolidated_firewall_mode": settings.get("consolidated-firewall-mode"),
                "implicit_log": settings.get("fwpolicy-implicit-log"),
            })

        return {"success": True, "count": len(packages), "packages": packages}

    except Exception as e:
        logger.exception("policy-package-list failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    adom = sys.argv[2] if len(sys.argv) > 2 else "root"
    print(json.dumps(asyncio.run(execute({"fmg_host": host, "adom": adom})), indent=2))
