#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Device Blueprint Create

Create a NAMED, reusable Device Blueprint in FMG 7.6 via
    add /pm/config/adom/{adom}/obj/fmg/device/blueprint

Named blueprints are what the CSV "Device Blueprint" column references, and they
package platform + templates + policy pkg + auth + HA + port-provisioning into
one reusable object.

Auto-prefixing of the `templates` list — observed from FMG GUI curl:
  1__<name>       System Template (devprof)
  4-1__<name>     IPsec Tunnel Template          (stype _ipsec)
  4-2__<name>     Static Route Template          (stype _router_static)
  4-1240__<name>  BGP Template                   (stype router_bgp)
  5__<name>       SD-WAN Template (wanprof)
Others may exist for _sdwan_overlay, _fap_setting — this tool discovers them
at runtime from the /pm/template/adom/{adom} catalog + a small stype->prefix map.

The `cliprofs` list (regular CLI templates) is SEPARATE from `templates`.
`prerun-cliprof` is also SEPARATE (runs before others). Both need no prefix.

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

# stype -> numeric prefix, observed from GUI blueprint create curl on 184.73.7.106
# devprof (System) and wanprof (SDWAN) DON'T live under /pm/template/adom/, so their
# prefixes are hardcoded here. The /pm/template/ family entries use "4-N" pattern
# where N is a stype-specific id.
_STYPE_TO_PREFIX = {
    # System Templates (devprof) — no stype from /pm/template/, use "1"
    "__devprof__":     "1",
    # SDWAN Templates (wanprof) — use "5"
    "__wanprof__":     "5",
    # /pm/template/ family — pattern is "4-<sub-id>"
    "_ipsec":          "4-1",
    "_router_static":  "4-2",
    "router_bgp":      "4-1240",
    # Discovery TBD — probe when needed:
    "_sdwan_overlay":  None,  # not yet observed, will try "4-N" via error probe
    "_fap_setting":    None,
}


def _bool_to_enum(v: Any) -> str:
    """Convert bool/int to FMG's 'enable'/'disable' string."""
    if isinstance(v, bool):
        return "enable" if v else "disable"
    if isinstance(v, int):
        return "enable" if v else "disable"
    if isinstance(v, str):
        return v.lower() if v.lower() in ("enable", "disable") else ("enable" if v else "disable")
    return "disable"


def _resolve_template_ref(client: FortiManagerClient, adom: str, name: str, stype_cache: Dict[str, str]) -> str:
    """Turn a friendly template name into an FMG-prefixed ref like '4-1__my-ipsec'.

    If `name` already has the '__' separator, pass through untouched.
    Otherwise look up the template in the catalog to find its stype, then map to prefix.
    """
    if "__" in name:
        return name  # already prefixed

    # Check if it's a devprof (System Template) — different endpoint family
    r = client.get(f"/pm/devprof/adom/{adom}/{name}", fields=["name"])
    if (r.get("result", [{}])[0].get("status") or {}).get("code") == 0:
        prefix = _STYPE_TO_PREFIX["__devprof__"]
        return f"{prefix}__{name}"

    # Check if it's a wanprof (SDWAN Template)
    r = client.get(f"/pm/wanprof/adom/{adom}/{name}", fields=["name"])
    if (r.get("result", [{}])[0].get("status") or {}).get("code") == 0:
        prefix = _STYPE_TO_PREFIX["__wanprof__"]
        return f"{prefix}__{name}"

    # Try /pm/template/adom/{adom} catalog for stype
    if name in stype_cache:
        stype = stype_cache[name]
    else:
        r = client.get(f"/pm/template/adom/{adom}")
        for entry in (r.get("result", [{}])[0].get("data") or []):
            entry_name = entry.get("name")
            ts = entry.get("template setting") or {}
            entry_stype = ts.get("stype")
            if entry_name and entry_stype:
                stype_cache[entry_name] = entry_stype
        stype = stype_cache.get(name)

    if not stype:
        raise ValueError(f"Template {name!r} not found in devprof, wanprof, or /pm/template catalog on ADOM {adom!r}")

    prefix = _STYPE_TO_PREFIX.get(stype)
    if not prefix:
        raise ValueError(f"Template {name!r} has stype {stype!r} — no numeric prefix mapping known. Update _STYPE_TO_PREFIX or pass a pre-prefixed ref like 'N__{name}'.")

    return f"{prefix}__{name}"


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    for req in ("adom", "name", "platform"):
        if not params.get(req):
            return {"success": False, "error": f"Missing required parameter: {req}"}

    adom = params["adom"]
    name = params["name"]
    platform = params["platform"]
    templates_in: List[str] = list(params.get("templates") or [])
    template_group: Optional[str] = params.get("template_group")
    if templates_in and template_group:
        return {"success": False, "error": "Pass either 'templates' OR 'template_group', not both"}

    # Determine prov-type
    if template_group:
        prov_type = "template-group"
    elif templates_in:
        prov_type = "templates"
    else:
        prov_type = "none"

    endpoint = f"/pm/config/adom/{adom}/obj/fmg/device/blueprint"
    named_url = f"{endpoint}/{name}"

    # Build the payload — start with observed GUI keys, fill from params
    body: Dict[str, Any] = {
        "name": name,
        "description": params.get("description") or None,
        "platform": platform,
        "pkg": params.get("pkg") or None,
        "folder": params.get("folder") or None,
        "prefer-img-ver": params.get("prefer_img_ver") or None,
        "prov-type": prov_type,
        "template-group": template_group,
        "cliprofs": list(params.get("cliprofs") or []),
        "prerun-cliprof": list(params.get("prerun_cliprof") or []),
        "auth-template": list(params.get("auth_template") or []),
        "dev-group": list(params.get("dev_group") or []),
        "port-provisioning": int(params.get("port_provisioning", 1)),
        "enforce-device-config": _bool_to_enum(params.get("enforce_device_config", False)),
        "sdwan-management": _bool_to_enum(params.get("sdwan_management", False)),
        "vm-log-disk": _bool_to_enum(params.get("vm_log_disk", False)),
        "linked-to-model": _bool_to_enum(params.get("linked_to_model", False)),
        "ha-config": _bool_to_enum(params.get("ha_config", False)),
        "ha-password": [params["ha_password"]] if params.get("ha_password") else [],
        "ha-monitor": list(params.get("ha_monitor") or []),
        "ha-hbdev": None,
        "cluster-worker": list(params.get("cluster_worker") or []),
        "templates": [],  # filled below after ref resolution
    }

    payload_snapshot = {"url": endpoint, "method": "add", "data": body}

    if params.get("dry_run"):
        # Can't resolve templates without a live client — dry-run keeps raw names
        body["templates"] = templates_in
        return {
            "success": True,
            "action": "dry-run",
            "name": name,
            "adom": adom,
            "platform": platform,
            "prov_type": prov_type,
            "templates_resolved": templates_in,
            "endpoint_used": endpoint,
            "payload_sent": payload_snapshot,
        }

    try:
        client = FortiManagerClient(host=fmg_host)

        # Resolve template refs (add numeric prefix based on stype/family)
        stype_cache: Dict[str, str] = {}
        resolved: List[str] = []
        for t in templates_in:
            resolved.append(_resolve_template_ref(client, adom, t, stype_cache))
        body["templates"] = resolved

        # Existence check
        probe = client.get(named_url, fields=["name"])
        exists = (probe.get("result", [{}])[0].get("status") or {}).get("code") == 0

        overwrite = bool(params.get("overwrite", False))
        if exists and not overwrite:
            return {
                "success": False,
                "action": "already-exists",
                "name": name,
                "adom": adom,
                "platform": platform,
                "prov_type": prov_type,
                "templates_resolved": resolved,
                "endpoint_used": endpoint,
                "error": f"Blueprint {name!r} already exists in ADOM {adom!r}. Set overwrite=true to update.",
            }

        if exists:
            resp = client.call("update", named_url, data=body)
            action = "updated"
        else:
            resp = client.call("add", endpoint, data=body)
            action = "created"

        status = resp.get("result", [{}])[0].get("status") or {}
        if status.get("code") != 0:
            return {
                "success": False,
                "action": action,
                "name": name,
                "adom": adom,
                "platform": platform,
                "prov_type": prov_type,
                "templates_resolved": resolved,
                "endpoint_used": endpoint,
                "error": f"FMG {status}",
                "payload_sent": payload_snapshot,
            }

        return {
            "success": True,
            "action": action,
            "name": name,
            "adom": adom,
            "platform": platform,
            "prov_type": prov_type,
            "templates_resolved": resolved,
            "endpoint_used": endpoint,
        }

    except Exception as e:
        logger.exception("device-blueprint-create failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}", "payload_sent": payload_snapshot}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "fmg.example.com"
    # Smoke: match the GUI curl exactly (blueprint-50G with the same 5 templates + cliprof)
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host,
        "adom": "BOR_Customer_1",
        "name": "sdk-blueprint-50g-test",
        "platform": "FortiGate-50G",
        "description": "SDK smoke test — mirrors GUI-created blueprint-50G",
        "templates": [
            "sdk-sys-tpl-test",           # System (devprof) -> auto '1__'
            "sdk-bor-ipsec-tpl-v1",       # IPsec -> '4-1__'
            "sdk-sdwan-tpl-test",         # SDWAN (wanprof) -> '5__'
            "sdk-bor-static-route-tpl-v1",# Static -> '4-2__'
            "sdk-bor-bgp-tpl-v1",         # BGP -> '4-1240__'
        ],
        "cliprofs": ["sdk-cli-tpl-test"],
        "port_provisioning": 1,
        "enforce_device_config": False,
        "overwrite": True,
    })), indent=2))
