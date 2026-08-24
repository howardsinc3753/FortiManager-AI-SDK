#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Provisioning Template Create — unified for FMG 7.6 Recommended Templates

Creates the SHELL of a provisioning template via the unified endpoint:
    add /pm/template/{stype}/adom/{adom}

with body:
    {
      "name": "<name>",
      "type": "template",
      "template setting": {
        "stype": "<stype>",
        "description": "<free text>",
        "widgets": ["<stype>"],
        "option": null
      }
    }

This one endpoint pattern covers ALL of these template types in FMG 7.6:
  - IPsec Tunnel        (stype = _ipsec)
  - BGP                 (stype = router_bgp)
  - Static Route        (stype = _router_static)
  - SD-WAN Overlay      (stype = _sdwan_overlay)   (new in 7.6)
  - FortiAP settings    (stype = _fap_setting)

Body/content population is a SEPARATE per-stype call to
    set /pm/config/adom/{adom}/template/{stype}/{name}/action-list/
with a data:[{action: "conf-<x>-template", value: {...}, seq: 1}] payload.
That's not covered here — this tool ships the shell only. Follow-up call is
per-stype and typically much larger (see the GUI curl trace for reference).

Templates in the LEGACY families (System/devprof, CLI, CLI Group, SDWAN/wanprof,
Certificate) live at their own dedicated URLs — use their dedicated tools:
  - system-template-create
  - cli-template-create
  - cli-template-group-create
  - sdwan-template-create

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)

# Friendly-name → raw FMG stype code
_STYPE_ALIASES = {
    "ipsec":         "_ipsec",
    "ipsec-tunnel":  "_ipsec",
    "vpn":           "_ipsec",
    "bgp":           "router_bgp",
    "router-bgp":    "router_bgp",
    "static":        "_router_static",
    "static-route":  "_router_static",
    "router-static": "_router_static",
    "sdwan-overlay": "_sdwan_overlay",
    "overlay":       "_sdwan_overlay",
    "fap":           "_fap_setting",
    "fortiap":       "_fap_setting",
    "wifi":          "_fap_setting",
}

# Every stype the unified endpoint accepts (from probing on FMG 7.6.7).
# Additional stypes may exist on other FMG builds — if the caller passes an
# unknown stype we still try, in case the box supports something we don't
# know about yet. Only "-6 Invalid url" tells us for sure it doesn't.
_KNOWN_STYPES = {
    "_ipsec", "router_bgp", "_router_static", "_sdwan_overlay", "_fap_setting",
}


def _resolve_stype(stype_in: str) -> str:
    """Map a friendly name to the raw FMG stype code. Pass through unknown values."""
    s = stype_in.strip().lower()
    if s in _STYPE_ALIASES:
        return _STYPE_ALIASES[s]
    # Already a raw code (starts with _ or looks like router_bgp)
    return stype_in


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    for req in ("adom", "name", "stype"):
        if not params.get(req):
            return {"success": False, "error": f"Missing required parameter: {req}"}

    adom = params["adom"]
    name = params["name"]
    stype_in = params["stype"]
    stype = _resolve_stype(stype_in)
    description = params.get("description", "") or ""
    revision_note = params.get("revision_note")
    overwrite = bool(params.get("overwrite", False))
    dry_run = bool(params.get("dry_run", False))

    endpoint = f"/pm/template/{stype}/adom/{adom}"
    named_url = f"{endpoint}/{name}"

    template_body: Dict[str, Any] = {
        "name": name,
        "type": "template",
        "template setting": {
            "stype": stype,
            "description": description,
            "widgets": [stype],
            "option": None,
        },
    }

    payload_snapshot = {
        "url": endpoint,
        "method": "add",
        "data": template_body,
    }

    # Dry-run bail
    if dry_run:
        return {
            "success": True,
            "action": "dry-run",
            "name": name,
            "adom": adom,
            "stype": stype_in,
            "stype_resolved": stype,
            "endpoint_used": endpoint,
            "payload_sent": payload_snapshot,
        }

    if stype not in _KNOWN_STYPES:
        # Not fatal — try anyway, but flag it
        logger.warning("stype %r not in known set %s — trying anyway", stype, _KNOWN_STYPES)

    try:
        client = FortiManagerClient(host=fmg_host)

        # Existence check via named URL (unified template endpoint supports GET on named)
        probe = client.get(named_url, fields=["name", "oid"])
        probe_status = probe.get("result", [{}])[0].get("status") or {}
        exists = probe_status.get("code") == 0

        if exists and not overwrite:
            existing = probe.get("result", [{}])[0].get("data") or {}
            return {
                "success": False,
                "action": "already-exists",
                "name": name,
                "adom": adom,
                "stype": stype_in,
                "stype_resolved": stype,
                "oid": existing.get("oid"),
                "endpoint_used": endpoint,
                "error": f"Template {name!r} (stype={stype!r}) already exists in ADOM {adom!r} (oid={existing.get('oid')}). Set overwrite=true to delete-and-recreate.",
            }

        action = "created"
        if exists and overwrite:
            # Delete first, then recreate — no PUT/update path for the shell body itself
            del_r = client.call("delete", named_url)
            del_status = del_r.get("result", [{}])[0].get("status") or {}
            if del_status.get("code") != 0:
                return {
                    "success": False,
                    "name": name,
                    "adom": adom,
                    "stype": stype_in,
                    "stype_resolved": stype,
                    "endpoint_used": endpoint,
                    "error": f"Overwrite requested but delete failed: FMG {del_status}",
                }
            action = "recreated"

        # Fire the add
        resp = client.call("add", endpoint, data=template_body)
        status = resp.get("result", [{}])[0].get("status") or {}
        if status.get("code") != 0:
            return {
                "success": False,
                "name": name,
                "adom": adom,
                "stype": stype_in,
                "stype_resolved": stype,
                "endpoint_used": endpoint,
                "error": f"FMG add error: {status}",
                "payload_sent": payload_snapshot,
            }

        # Grab OID by re-reading
        confirm = client.get(named_url, fields=["name", "oid"])
        confirm_data = confirm.get("result", [{}])[0].get("data") or {}
        oid = confirm_data.get("oid")

        # Optional revision note (mirrors the GUI's "make X template" annotation)
        revision_added = False
        if revision_note:
            rev_url = f"/pm/config/adom/{adom}/_objrev/template/{stype}/{name}"
            rev_r = client.call("add", rev_url, data={"revision note": revision_note})
            rev_status = rev_r.get("result", [{}])[0].get("status") or {}
            revision_added = rev_status.get("code") == 0

        return {
            "success": True,
            "action": action,
            "name": name,
            "adom": adom,
            "stype": stype_in,
            "stype_resolved": stype,
            "oid": oid,
            "endpoint_used": endpoint,
            "revision_added": revision_added,
        }

    except Exception as e:
        logger.exception("provisioning-template-create failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}", "payload_sent": payload_snapshot}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "fmg.example.com"
    stype = sys.argv[2] if len(sys.argv) > 2 else "ipsec"
    name = sys.argv[3] if len(sys.argv) > 3 else f"sdk-{stype}-tpl-test"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host,
        "adom": "BOR_Customer_1",
        "name": name,
        "stype": stype,
        "description": f"SDK smoke test — {stype} template shell",
        "revision_note": f"make {stype} template",
        "overwrite": True,
    })), indent=2))
