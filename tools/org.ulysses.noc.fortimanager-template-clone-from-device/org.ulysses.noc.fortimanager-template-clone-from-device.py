#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Template Clone From Device

Clone live device config from DVMDB into named human-facing FMG provisioning
templates via the JSON-RPC "clone" method.

Pattern (per FMG GUI observation):
    method: clone
    url:    pm/config/device/{device}/vdom/{vdom}/{source_path}   (source: DVMDB)
    data:   {"new url": pm/config/adom/{adom}/template/{stype}/{target_name}}   (dest)

Confirmed working on FMG 7.6.7 for these stypes:
  - router_bgp        (source: router/bgp)
  - _router_static    (source: router/static)
  - _ipsec            (source: vpn/ipsec/phase1-interface OR phase2-interface)

Known gap on 7.6.7:
  - SDWAN (source: system/sdwan) requires shell-first wanprof creation before
    clone will land — target /pm/wanprof/adom/{adom} rejected with -1/-503.
    Not yet wrapped in a preset — use `source_path` + custom `stype` if you
    figure out the right target format.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)

# Friendly-name presets: preset -> (source_path, stype)
# source_path is appended to /pm/config/device/{dev}/vdom/{vdom}/
# stype selects /pm/template/{stype}/adom/{adom}/{name} as the target
_PRESETS: Dict[str, Dict[str, str]] = {
    "bgp":            {"source_path": "router/bgp",                    "stype": "router_bgp"},
    "static-route":   {"source_path": "router/static",                 "stype": "_router_static"},
    "static":         {"source_path": "router/static",                 "stype": "_router_static"},
    "ipsec-phase1":   {"source_path": "vpn/ipsec/phase1-interface",    "stype": "_ipsec"},
    "ipsec":          {"source_path": "vpn/ipsec/phase1-interface",    "stype": "_ipsec"},  # alias
    "ipsec-phase2":   {"source_path": "vpn/ipsec/phase2-interface",    "stype": "_ipsec"},
}


def _resolve_clone(entry: Dict[str, Any], device: str, vdom: str, adom: str) -> tuple[str, str, str, str]:
    """Resolve a clone entry into (source_url, target_url, effective_preset, effective_stype)."""
    preset = entry.get("preset")
    target_name = entry.get("target_name")
    if not target_name:
        raise ValueError("target_name is required for every clone entry")

    if preset:
        if preset not in _PRESETS:
            raise ValueError(f"Unknown preset {preset!r}. Known: {sorted(_PRESETS.keys())}")
        source_path = _PRESETS[preset]["source_path"]
        stype = _PRESETS[preset]["stype"]
    else:
        source_path = entry.get("source_path")
        stype = entry.get("stype")
        if not (source_path and stype):
            raise ValueError("Either preset OR both source_path+stype must be provided")

    source_url = f"pm/config/device/{device}/vdom/{vdom}/{source_path.lstrip('/')}"
    target_url = f"pm/config/adom/{adom}/template/{stype}/{target_name}"
    return source_url, target_url, preset or "custom", stype


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    for req in ("adom", "device", "clones"):
        if not params.get(req):
            return {"success": False, "error": f"Missing required parameter: {req}"}

    adom = params["adom"]
    device = params["device"]
    vdom = params.get("vdom", "root")
    clones = list(params["clones"] or [])
    overwrite = bool(params.get("overwrite", False))
    stop_on_error = bool(params.get("stop_on_error", False))

    if not clones:
        return {"success": False, "error": "clones list is empty"}

    try:
        client = FortiManagerClient(host=fmg_host)
    except Exception as e:
        return {"success": False, "error": f"Client init failed: {type(e).__name__}: {e}"}

    results: List[Dict[str, Any]] = []
    any_fail = False
    any_ok = False

    for idx, entry in enumerate(clones):
        result: Dict[str, Any] = {"preset": entry.get("preset") or "custom"}
        try:
            source_url, target_url, effective_preset, stype = _resolve_clone(entry, device, vdom, adom)
            result["source_url"] = source_url
            result["target_url"] = target_url
            result["preset"] = effective_preset
            result["stype"] = stype

            # Overwrite handling: delete existing target first
            if overwrite:
                target_name = entry["target_name"]
                del_r = client.call("delete", f"/pm/template/{stype}/adom/{adom}/{target_name}")
                # Ignore delete errors (target may not exist) — we care about the clone below

            # Fire the clone
            r = client.call("clone", source_url, data={"new url": target_url})
            status = r.get("result", [{}])[0].get("status") or {}
            code = status.get("code")
            msg = status.get("message") or ""

            # FMG sometimes returns non-zero codes but the clone still landed
            # (observed: IPsec phase2 returns -10000 "invalid value" but object appears).
            # Verify by GET on the target.
            verify_url = f"/pm/template/{stype}/adom/{adom}/{entry['target_name']}"
            verify_r = client.get(verify_url, fields=["name", "oid"])
            verify_data = verify_r.get("result", [{}])[0].get("data") or {}
            landed = bool(verify_data.get("oid"))

            result["code"] = code
            result["message"] = msg[:200]
            if landed:
                result["status"] = "cloned"
                result["oid"] = verify_data.get("oid")
                any_ok = True
            else:
                result["status"] = "failed"
                any_fail = True

        except Exception as e:
            result["status"] = "error"
            result["message"] = f"{type(e).__name__}: {e}"
            any_fail = True

        results.append(result)
        if any_fail and stop_on_error:
            break

    action = "cloned" if (any_ok and not any_fail) else ("partial" if any_ok else "failed")
    return {
        "success": (action == "cloned"),
        "action": action,
        "adom": adom,
        "device": device,
        "results": results,
    }


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "fmg.example.com"
    dev = sys.argv[2] if len(sys.argv) > 2 else "spoke-1"
    # Smoke: clone BGP + Static + IPsec (P1+P2) from spoke-1 into BOR_Customer_1 human templates
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host,
        "adom": "BOR_Customer_1",
        "device": dev,
        "vdom": "root",
        "clones": [
            {"preset": "bgp",          "target_name": f"HUMAN-{dev}-BGP"},
            {"preset": "static-route", "target_name": f"HUMAN-{dev}-STATIC"},
            {"preset": "ipsec-phase1", "target_name": f"HUMAN-{dev}-IPSEC-P1"},
            {"preset": "ipsec-phase2", "target_name": f"HUMAN-{dev}-IPSEC-P2"},
        ],
        "overwrite": True,
    })), indent=2))
