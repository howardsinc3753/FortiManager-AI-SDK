#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager System Template Create

Create or update a FortiManager Device Profile / System Template (devprof) —
the container that binds hostname, DNS, NTP, admin, syslog and SNMP settings
to a managed device.

FMG 7.x exposes device profiles at one of two base paths depending on release:
  1. /pm/config/adom/{adom}/devprof           (collection, preferred on 7.4/7.6)
  2. /pm/devprof/adom/{adom}                  (older/alternate layout)

We try (1) first. If FMG answers with -3 (URL not found) or -6 (invalid URL),
we retry against (2) and stick with whichever worked.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)

# FMG return codes that indicate "URL doesn't exist at this path"; we swap layouts.
_URL_NOT_FOUND_CODES = {-3, -6}


def _status(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the FMG status envelope from a JSON-RPC response."""
    return (resp.get("result", [{}])[0] or {}).get("status") or {}


def _resolve_base(client: FortiManagerClient, adom: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Return (collection_url, named_prefix, probe_error).

    Prefer /pm/config/adom/{adom}/devprof. If that path is rejected as
    unknown, fall back to /pm/devprof/adom/{adom}. If both fail, surface
    the first error so the caller can report it verbatim.
    """
    primary = f"/pm/config/adom/{adom}/devprof"
    alternate = f"/pm/devprof/adom/{adom}"

    for base in (primary, alternate):
        probe = client.get(base, fields=["name"])
        st = _status(probe)
        if st.get("code") == 0:
            return base, base, None
        if st.get("code") not in _URL_NOT_FOUND_CODES:
            # Real error (permission, ADOM missing, etc). Fail fast with it.
            return base, base, st
    return primary, primary, _status(client.get(primary, fields=["name"]))


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    name = params.get("name")
    if not name:
        return {"success": False, "error": "Missing required parameter: name"}

    adom = params.get("adom", "root")
    description = params.get("description", "") or ""
    overwrite = bool(params.get("overwrite", False))

    # FMG devprof creates require an explicit type discriminator ("devprof").
    # Without it the collection URL returns code -10 "data invalid for selected url".
    data: Dict[str, Any] = {"name": name, "type": "devprof"}
    if description:
        data["description"] = description

    try:
        client = FortiManagerClient(host=fmg_host)

        # Pick the devprof base URL layout FMG actually accepts on this release.
        collection_url, _named_prefix, probe_err = _resolve_base(client, adom)
        if probe_err:
            return {
                "success": False,
                "name": name,
                "adom": adom,
                "endpoint_used": collection_url,
                "error": f"FMG {probe_err}",
            }
        named_url = f"{collection_url}/{name}"

        # Existence check on the named URL
        existing = client.get(named_url, fields=["name"])
        exists = _status(existing).get("code") == 0

        if exists and not overwrite:
            return {
                "success": False,
                "action": "noop",
                "name": name,
                "adom": adom,
                "endpoint_used": collection_url,
                "error": (
                    f"System template {name!r} already exists in ADOM {adom!r}. "
                    "Set overwrite=true to update."
                ),
            }

        if exists:
            resp = client.call("update", named_url, data=data)
            action = "updated"
        else:
            resp = client.call("add", collection_url, data=data)
            action = "created"

        status = _status(resp)
        if status.get("code") != 0:
            return {
                "success": False,
                "action": action,
                "name": name,
                "adom": adom,
                "endpoint_used": collection_url,
                "error": f"FMG {status}",
            }

        return {
            "success": True,
            "action": action,
            "name": name,
            "adom": adom,
            "endpoint_used": collection_url,
        }

    except Exception as e:
        logger.exception("system-template-create failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "184.73.7.106"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host,
        "adom": "BOR_Customer_1",
        "name": "sdk-sys-tpl-test",
        "description": "FortiManager AI SDK smoke test — system template",
        "overwrite": True,
    })), indent=2))
