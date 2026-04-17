#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Policy Create

Create a firewall policy in a policy package. Uses `add` on the collection URL
so FMG auto-assigns the policyid.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)

_ACTION_MAP = {"deny": 0, "accept": 1, "ipsec": 2, "ssl-vpn": 3}
_STATUS_MAP = {"disable": 0, "enable": 1}
_NAT_MAP = {"disable": 0, "enable": 1}
_LOGTRAFFIC_MAP = {"disable": 0, "utm": 2, "all": 3}


def _require_list(params: Dict[str, Any], key: str) -> List[str] | None:
    val = params.get(key)
    if not val or not isinstance(val, list):
        return None
    return [str(v) for v in val]


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    package = params.get("package")
    if not package:
        return {"success": False, "error": "Missing required parameter: package"}

    for req in ("srcintf", "dstintf", "srcaddr", "dstaddr", "service"):
        if not _require_list(params, req):
            return {"success": False, "error": f"Missing or empty required parameter: {req} (must be non-empty array)"}

    adom = params.get("adom", "root")
    name = params.get("name") or ""
    action = (params.get("action") or "accept").lower()
    status = (params.get("status") or "enable").lower()
    nat = (params.get("nat") or "disable").lower()
    logtraffic = (params.get("logtraffic") or "utm").lower()
    schedule = params.get("schedule") or ["always"]
    comments = params.get("comments") or ""

    for label, mapping, val in (
        ("action", _ACTION_MAP, action),
        ("status", _STATUS_MAP, status),
        ("nat", _NAT_MAP, nat),
        ("logtraffic", _LOGTRAFFIC_MAP, logtraffic),
    ):
        if val not in mapping:
            return {"success": False, "error": f"Invalid {label}: {val!r}"}

    data: Dict[str, Any] = {
        "srcintf": params["srcintf"],
        "dstintf": params["dstintf"],
        "srcaddr": params["srcaddr"],
        "dstaddr": params["dstaddr"],
        "service": params["service"],
        "schedule": schedule if isinstance(schedule, list) else [schedule],
        "action": _ACTION_MAP[action],
        "status": _STATUS_MAP[status],
        "nat": _NAT_MAP[nat],
        "logtraffic": _LOGTRAFFIC_MAP[logtraffic],
    }
    if name:
        data["name"] = name
    if comments:
        data["comments"] = comments

    url = f"/pm/config/adom/{adom}/pkg/{package}/firewall/policy"

    try:
        client = FortiManagerClient(host=fmg_host)
        resp = client.call("add", url, data=data)
        result = resp.get("result", [{}])[0]
        fmg_status = result.get("status") or {}
        if fmg_status.get("code") != 0:
            return {
                "success": False, "action": "created",
                "adom": adom, "package": package,
                "error": f"FMG {fmg_status}",
            }

        returned = result.get("data") or {}
        # FMG returns the created object's id in data on success
        if isinstance(returned, list) and returned:
            returned = returned[0]
        policyid = returned.get("policyid") if isinstance(returned, dict) else None

        return {
            "success": True,
            "action": "created",
            "policyid": policyid,
            "name": name,
            "adom": adom,
            "package": package,
        }

    except Exception as e:
        logger.exception("policy-create failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    pkg = sys.argv[2] if len(sys.argv) > 2 else "howard-sdwan-spoke-1"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host, "adom": "root", "package": pkg,
        "name": "sdk-test-policy",
        "srcintf": ["any"], "dstintf": ["any"],
        "srcaddr": ["sdk-addr-test"], "dstaddr": ["all"],
        "service": ["ALL"], "schedule": ["always"],
        "action": "accept", "status": "enable", "nat": "enable",
        "comments": "Created by SDK smoke test",
    })), indent=2))
