#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Policy List

List firewall policies in a specific policy package.

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

# FMG action encoding: 0=deny, 1=accept, 2=ipsec, 3=ssl-vpn
_ACTION_LABEL = {0: "deny", 1: "accept", 2: "ipsec", 3: "ssl-vpn"}
_ACTION_FILTER_MAP = {"accept": 1, "deny": 0}


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    package = params.get("package")
    if not package:
        return {"success": False, "error": "Missing required parameter: package"}

    adom = params.get("adom", "root")
    name_like = (params.get("name_like") or "").lower()
    action_filter = (params.get("action_filter") or "any").lower()
    only_enabled = bool(params.get("only_enabled", False))
    offset = int(params.get("offset", 0))
    limit = int(params.get("limit", 100))

    try:
        client = FortiManagerClient(host=fmg_host)
        resp = client.get(
            f"/pm/config/adom/{adom}/pkg/{package}/firewall/policy",
            fields=[
                "policyid", "name", "srcintf", "dstintf", "srcaddr", "dstaddr",
                "service", "schedule", "action", "status", "nat", "uuid",
                "comments",
            ],
            range=[offset, limit],
        )
        result = resp.get("result", [{}])[0]
        status = result.get("status", {})
        if status.get("code") != 0:
            return {"success": False, "error": f"FMG {status}"}

        raw = result.get("data") or []
        desired_action = _ACTION_FILTER_MAP.get(action_filter) if action_filter != "any" else None

        policies = []
        for p in raw:
            if only_enabled and p.get("status", 0) != 1:
                continue
            if desired_action is not None and p.get("action") != desired_action:
                continue
            if name_like and name_like not in (p.get("name") or "").lower():
                continue
            action = p.get("action", 0)
            policies.append({
                "policyid": p.get("policyid"),
                "name": p.get("name") or "",
                "srcintf": p.get("srcintf") or [],
                "dstintf": p.get("dstintf") or [],
                "srcaddr": p.get("srcaddr") or [],
                "dstaddr": p.get("dstaddr") or [],
                "service": p.get("service") or [],
                "schedule": p.get("schedule") or [],
                "action": action,
                "action_label": _ACTION_LABEL.get(action, str(action)),
                "status": p.get("status"),
                "nat": p.get("nat"),
                "uuid": p.get("uuid") or "",
                "comments": p.get("comments") or "",
            })

        return {
            "success": True,
            "count": len(policies),
            "package": package,
            "policies": policies,
        }

    except Exception as e:
        logger.exception("policy-list failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    adom = sys.argv[2] if len(sys.argv) > 2 else "root"
    pkg = sys.argv[3] if len(sys.argv) > 3 else "default"
    print(json.dumps(
        asyncio.run(execute({"fmg_host": host, "adom": adom, "package": pkg})),
        indent=2,
    ))
