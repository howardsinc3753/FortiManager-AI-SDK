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

SDWAN uses a DIFFERENT mechanism (dedicated import endpoint, not clone method).
Preset `sdwan` internally routes to:
    method: exec
    url:    /pm/config/adom/{adom}/_wanprof/import
    data:   {"template": "<target_name>", "device": {"name": dev, "vdom": vdom},
             "description": "..."}
The target lands at /pm/wanprof/adom/{adom}/<target_name>.
The wanprof named <target_name> must ALREADY EXIST (create with sdwan-template-create
first — the import merges the device's SDWAN into it, matching FMG's GUI flow).

Author: Ulysses Project
Version: 1.1.0
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

# Friendly-name presets:
#   Type "clone" -> uses method=clone on /pm/config/device/{dev}/vdom/{vdom}/{source_path}
#                   target is /pm/template/{stype}/adom/{adom}/{name}
#   Type "wanprof-import" -> uses method=exec on /pm/config/adom/{adom}/_wanprof/import
#                            target is a wanprof named {target_name}
_PRESETS: Dict[str, Dict[str, str]] = {
    "bgp":            {"type": "clone", "source_path": "router/bgp",                    "stype": "router_bgp"},
    "static-route":   {"type": "clone", "source_path": "router/static",                 "stype": "_router_static"},
    "static":         {"type": "clone", "source_path": "router/static",                 "stype": "_router_static"},  # alias
    "ipsec-phase1":   {"type": "clone", "source_path": "vpn/ipsec/phase1-interface",    "stype": "_ipsec"},
    "ipsec":          {"type": "clone", "source_path": "vpn/ipsec/phase1-interface",    "stype": "_ipsec"},  # alias
    "ipsec-phase2":   {"type": "clone", "source_path": "vpn/ipsec/phase2-interface",    "stype": "_ipsec"},
    "sdwan":          {"type": "wanprof-import", "stype": "wanprof"},  # uses dedicated import endpoint
}


def _resolve_clone(entry: Dict[str, Any], device: str, vdom: str, adom: str) -> tuple[str, Dict[str, Any], str, str]:
    """Resolve a clone entry into (op_type, request_spec, effective_preset, effective_stype).

    op_type is "clone" or "wanprof-import".
    request_spec is a dict describing the API call to make:
      - clone: {"method": "clone", "url": source, "data": {"new url": target}, "target_url": target}
      - wanprof-import: {"method": "exec", "url": import_url, "data": {...}, "target_url": verify_url}
    """
    preset = entry.get("preset")
    target_name = entry.get("target_name")
    if not target_name:
        raise ValueError("target_name is required for every clone entry")

    if preset:
        if preset not in _PRESETS:
            raise ValueError(f"Unknown preset {preset!r}. Known: {sorted(_PRESETS.keys())}")
        preset_def = _PRESETS[preset]
        op_type = preset_def["type"]
        stype = preset_def["stype"]
        source_path = preset_def.get("source_path")
    else:
        source_path = entry.get("source_path")
        stype = entry.get("stype")
        op_type = entry.get("op_type", "clone")
        if not (source_path and stype) and op_type == "clone":
            raise ValueError("Either preset OR both source_path+stype must be provided for clone type")

    if op_type == "clone":
        source_url = f"pm/config/device/{device}/vdom/{vdom}/{source_path.lstrip('/')}"
        target_url = f"pm/config/adom/{adom}/template/{stype}/{target_name}"
        spec = {
            "method": "clone",
            "url": source_url,
            "data": {"new url": target_url},
            "target_url": target_url,
            "verify_url": f"/pm/template/{stype}/adom/{adom}/{target_name}",
        }
    elif op_type == "wanprof-import":
        # Uses the dedicated SDWAN import endpoint (per GUI-observed pattern)
        import_url = f"/pm/config/adom/{adom}/_wanprof/import"
        target_url = f"/pm/wanprof/adom/{adom}/{target_name}"
        spec = {
            "method": "exec",
            "url": import_url,
            "data": {
                "template": target_name,
                "device": {"name": device, "vdom": vdom},
                "description": entry.get("description") or f"SDWAN imported from {device}",
            },
            "target_url": target_url,
            "verify_url": f"/pm/wanprof/adom/{adom}/{target_name}",
        }
    else:
        raise ValueError(f"Unknown op_type {op_type!r}")

    return op_type, spec, preset or "custom", stype


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
            op_type, spec, effective_preset, stype = _resolve_clone(entry, device, vdom, adom)
            result["op_type"] = op_type
            result["source_url"] = spec.get("url")
            result["target_url"] = spec["target_url"]
            result["preset"] = effective_preset
            result["stype"] = stype

            target_name = entry["target_name"]

            # Overwrite handling: delete existing target first
            if overwrite:
                if op_type == "clone":
                    del_url = f"/pm/template/{stype}/adom/{adom}/{target_name}"
                else:  # wanprof-import
                    del_url = f"/pm/wanprof/adom/{adom}/{target_name}"
                client.call("delete", del_url)
                # Ignore delete errors (target may not exist) — we care about the op below

            # Fire the operation
            r = client.call(spec["method"], spec["url"], data=spec["data"])
            status = r.get("result", [{}])[0].get("status") or {}
            code = status.get("code")
            msg = status.get("message") or ""

            # FMG sometimes returns non-zero codes but the object still lands
            # (observed: IPsec phase2 returns -10000 "invalid value" but appears).
            # Verify by GET on the target.
            verify_r = client.get(spec["verify_url"], fields=["name", "oid"])
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
    # Smoke: clone BGP + Static + IPsec (P1+P2) from spoke-1 into ADOM dedicated templates
    # Naming convention BOR-<family>-SINGLE (leaves room for -DUAL variants for dual-circuit)
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host,
        "adom": "BOR_Customer_1",
        "device": dev,
        "vdom": "root",
        "clones": [
            {"preset": "bgp",          "target_name": "BOR-BGP-SINGLE"},
            {"preset": "static-route", "target_name": "BOR-STATIC-SINGLE"},
            {"preset": "ipsec-phase1", "target_name": "BOR-IPSEC-P1-SINGLE"},
            {"preset": "ipsec-phase2", "target_name": "BOR-IPSEC-P2-SINGLE"},
            {"preset": "sdwan",        "target_name": "BOR-SDWAN-SINGLE"},
        ],
        "overwrite": True,
    })), indent=2))
