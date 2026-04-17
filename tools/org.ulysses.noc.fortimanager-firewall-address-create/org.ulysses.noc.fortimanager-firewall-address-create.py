#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Firewall Address Create

Create or update a firewall address object (ipmask/iprange/fqdn) in an ADOM.

Uses `add` on the collection URL (or `update` on the named URL when overwrite=true)
to avoid the FMG table-wipe behavior that `set` can trigger.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import ipaddress
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)

_TYPE_STR_TO_INT = {"ipmask": 0, "iprange": 1, "fqdn": 2}


def _cidr_to_subnet_list(s: str) -> Optional[List[str]]:
    """Convert '10.1.1.0/24' or '10.1.1.1/32' to ['10.1.1.0', '255.255.255.0'].
    Also accepts 'ip mask' form (space-separated)."""
    s = s.strip()
    try:
        if "/" in s:
            net = ipaddress.ip_network(s, strict=False)
            return [str(net.network_address), str(net.netmask)]
        parts = s.split()
        if len(parts) == 2:
            ipaddress.ip_address(parts[0])
            ipaddress.ip_address(parts[1])
            return parts
    except (ValueError, TypeError):
        return None
    return None


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    name = params.get("name")
    type_str = (params.get("type") or "").lower()
    if not name:
        return {"success": False, "error": "Missing required parameter: name"}
    if type_str not in _TYPE_STR_TO_INT:
        return {"success": False, "error": f"Invalid type {type_str!r}. Use: ipmask | iprange | fqdn"}

    adom = params.get("adom", "root")
    overwrite = bool(params.get("overwrite", False))

    # Build type-specific data
    data: Dict[str, Any] = {"name": name, "type": _TYPE_STR_TO_INT[type_str]}

    if type_str == "ipmask":
        subnet = params.get("subnet")
        if not subnet:
            return {"success": False, "error": "type=ipmask requires 'subnet' (CIDR or ip/mask)"}
        sub = _cidr_to_subnet_list(subnet)
        if not sub:
            return {"success": False, "error": f"Invalid subnet: {subnet!r}"}
        data["subnet"] = sub

    elif type_str == "iprange":
        start = params.get("start_ip")
        end = params.get("end_ip")
        if not (start and end):
            return {"success": False, "error": "type=iprange requires 'start_ip' and 'end_ip'"}
        try:
            if ipaddress.ip_address(end) < ipaddress.ip_address(start):
                return {"success": False, "error": "end_ip must be >= start_ip"}
        except ValueError as e:
            return {"success": False, "error": f"Invalid IP: {e}"}
        data["start-ip"] = start
        data["end-ip"] = end

    elif type_str == "fqdn":
        fqdn = params.get("fqdn")
        if not fqdn:
            return {"success": False, "error": "type=fqdn requires 'fqdn'"}
        data["fqdn"] = fqdn

    # Optional common fields
    if params.get("comment"):
        data["comment"] = params["comment"]
    if params.get("color") is not None:
        data["color"] = int(params["color"])
    if params.get("associated_interface"):
        data["associated-interface"] = list(params["associated_interface"])

    collection_url = f"/pm/config/adom/{adom}/obj/firewall/address"
    named_url = f"{collection_url}/{name}"

    try:
        client = FortiManagerClient(host=fmg_host)

        # Existence check
        existing = client.get(named_url, fields=["name"])
        exists = (existing.get("result", [{}])[0].get("status") or {}).get("code") == 0

        if exists and not overwrite:
            return {
                "success": False,
                "action": "noop",
                "name": name,
                "adom": adom,
                "type": type_str,
                "error": f"Address {name!r} already exists in ADOM {adom!r}. Set overwrite=true to update.",
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
                "type": type_str,
                "error": f"FMG {status}",
            }

        return {
            "success": True,
            "action": action,
            "name": name,
            "adom": adom,
            "type": type_str,
        }

    except Exception as e:
        logger.exception("firewall-address-create failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host, "adom": "root",
        "name": "sdk-addr-test", "type": "ipmask",
        "subnet": "10.99.99.0/24",
        "comment": "FortiManager AI SDK smoke test",
        "overwrite": True,
    })), indent=2))
