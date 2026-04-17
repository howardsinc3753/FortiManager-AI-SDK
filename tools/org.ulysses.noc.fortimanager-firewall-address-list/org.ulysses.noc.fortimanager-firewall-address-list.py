#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Firewall Address List

List firewall address objects in an ADOM.

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

_TYPE_INT_TO_LABEL = {
    0: "ipmask",
    1: "iprange",
    2: "fqdn",
    3: "wildcard",
    6: "wildcard-fqdn",
    7: "geography",
    10: "mac",
    15: "dynamic",
}
_TYPE_LABEL_TO_INT = {v: k for k, v in _TYPE_INT_TO_LABEL.items()}


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    adom = params.get("adom", "root")
    name_like = (params.get("name_like") or "").lower()
    type_filter = (params.get("type_filter") or "any").lower()
    offset = int(params.get("offset", 0))
    limit = int(params.get("limit", 200))

    if type_filter != "any" and type_filter not in _TYPE_LABEL_TO_INT:
        return {"success": False, "error": f"Invalid type_filter: {type_filter!r}"}

    try:
        client = FortiManagerClient(host=fmg_host)
        resp = client.get(
            f"/pm/config/adom/{adom}/obj/firewall/address",
            fields=[
                "name", "type", "subnet", "start-ip", "end-ip", "fqdn",
                "associated-interface", "color", "comment", "uuid",
            ],
            range=[offset, limit],
        )
        result = resp.get("result", [{}])[0]
        status = result.get("status", {})
        if status.get("code") != 0:
            return {"success": False, "error": f"FMG {status}"}

        raw = result.get("data") or []
        target_type = _TYPE_LABEL_TO_INT.get(type_filter) if type_filter != "any" else None

        addresses = []
        for a in raw:
            atype = a.get("type")
            if target_type is not None and atype != target_type:
                continue
            if name_like and name_like not in (a.get("name") or "").lower():
                continue
            addresses.append({
                "name": a.get("name"),
                "type": atype,
                "type_label": _TYPE_INT_TO_LABEL.get(atype, str(atype)),
                "subnet": a.get("subnet") or [],
                "start_ip": a.get("start-ip") or "",
                "end_ip": a.get("end-ip") or "",
                "fqdn": a.get("fqdn") or "",
                "associated_interface": a.get("associated-interface") or [],
                "color": a.get("color") or 0,
                "comment": a.get("comment") or "",
                "uuid": a.get("uuid") or "",
            })

        return {"success": True, "count": len(addresses), "adom": adom, "addresses": addresses}

    except Exception as e:
        logger.exception("firewall-address-list failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    adom = sys.argv[2] if len(sys.argv) > 2 else "root"
    print(json.dumps(asyncio.run(execute({"fmg_host": host, "adom": adom})), indent=2))
