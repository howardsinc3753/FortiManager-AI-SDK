#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager SD-WAN Template Create

Create or update a FortiManager 7.6 SD-WAN Template (WAN Profile) — the
first-class provisioning template that wraps zones, members, health-checks,
service rules and BGP-on-Lo neighbors, and binds onto managed FortiGates
(30G/50G/120G/VM) via a Model Device.

FMG 7.6 endpoint layout (discovered against 184.73.7.106):

  Shell (create / list / delete):
    /pm/wanprof/adom/{adom}                     (collection — `add`, `get`)
    /pm/wanprof/adom/{adom}/{name}              (named — `get`, `delete`)

  SDWAN body (nested inside the shell):
    /pm/config/adom/{adom}/wanprof/{name}/system/sdwan             (`update`)
    /pm/config/adom/{adom}/wanprof/{name}/system/sdwan/zone        (`add`)
    /pm/config/adom/{adom}/wanprof/{name}/system/sdwan/members     (`add`)
    /pm/config/adom/{adom}/wanprof/{name}/system/sdwan/health-check(`add`)
    /pm/config/adom/{adom}/wanprof/{name}/system/sdwan/service     (`add`)
    /pm/config/adom/{adom}/wanprof/{name}/system/sdwan/neighbor    (`add`)

A newly-created wanprof arrives pre-seeded with a reserved `virtual-wan-link`
zone and `Default_AWS` health-check. A whole-body `set` is refused because
the seed is undeletable — we therefore `add` each caller-supplied child
onto the child sub-URL instead of overwriting the body.

Caller field-naming: callers use Python-friendly snake_case in every nested
dict (`seq_num`, `advpn_select`, `health_check`, `priority_members`, etc.).
This tool recursively converts snake_case dict keys to the dash-case keys
FMG expects (`seq-num`, `advpn-select`, `health-check`, `priority-members`).
Values are never rewritten — object names like `HUB_Health` and metadata
variables like `$(HUB1_LO)` pass through intact.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)


def _status_of(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the FMG status envelope from a JSON-RPC response."""
    return (resp.get("result", [{}])[0] or {}).get("status") or {}


def _dashify(obj: Any) -> Any:
    """Recursively convert snake_case dict keys to dash-case.

    Values are left alone — object names like 'HUB_Health' and metadata
    variables like '$(HUB1_LO)' must not be mangled.
    """
    if isinstance(obj, dict):
        return {str(k).replace("_", "-"): _dashify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_dashify(x) for x in obj]
    return obj


def _as_list(val: Any) -> List[Any]:
    """Coerce a parameter that should be an array. None/missing → []."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    # Be forgiving: a single dict handed where an array was expected.
    return [val]


def _add_children(
    client: FortiManagerClient,
    body_url: str,
    child: str,
    items: List[Dict[str, Any]],
    key_hint: str,
    errors: List[Dict[str, Any]],
) -> int:
    """Add each item as an individual child under `body_url/child`.

    Returns the number of successful adds. Failures are appended to `errors`
    with the item's identifying key (best-effort, using `key_hint`).
    """
    if not items:
        return 0
    child_url = f"{body_url}/{child}"
    ok = 0
    for item in items:
        payload = _dashify(item)
        resp = client.call("add", child_url, data=payload)
        st = _status_of(resp)
        if st.get("code") == 0:
            ok += 1
        else:
            errors.append({
                "child": child,
                key_hint: item.get(key_hint) if isinstance(item, dict) else None,
                "status": st,
            })
    return ok


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    name = params.get("name")
    if not name:
        return {"success": False, "error": "Missing required parameter: name"}

    adom = params.get("adom", "root")
    status_val = params.get("status", "enable")
    if status_val not in ("enable", "disable"):
        return {
            "success": False,
            "error": f"Invalid status {status_val!r}. Use: enable | disable",
        }
    description = params.get("description", "") or ""
    overwrite = bool(params.get("overwrite", False))

    zone = _as_list(params.get("zone"))
    members = _as_list(params.get("members"))
    health_check = _as_list(params.get("health_check"))
    service = _as_list(params.get("service"))
    neighbor = _as_list(params.get("neighbor"))

    shell_collection = f"/pm/wanprof/adom/{adom}"
    shell_named = f"{shell_collection}/{name}"
    body_url = f"/pm/config/adom/{adom}/wanprof/{name}/system/sdwan"

    try:
        client = FortiManagerClient(host=fmg_host)

        # Existence probe on the shell — GET named URL. code=0 means it exists.
        existing = client.get(shell_named, fields=["name"])
        exists = _status_of(existing).get("code") == 0

        if exists and not overwrite:
            return {
                "success": False,
                "action": "noop",
                "name": name,
                "adom": adom,
                "error": (
                    f"SDWAN template {name!r} already exists in ADOM {adom!r}. "
                    "Set overwrite=true to update."
                ),
            }

        # Overwrite: delete the old shell first so the body resets to defaults
        # (avoids appending duplicates onto a stale child list).
        if exists:
            del_resp = client.delete(shell_named)
            del_st = _status_of(del_resp)
            if del_st.get("code") != 0:
                return {
                    "success": False,
                    "action": "updated",
                    "name": name,
                    "adom": adom,
                    "error": f"FMG delete-before-recreate failed: {del_st}",
                }

        # Create the shell. Description on the shell is what shows in the UI list.
        shell_data: Dict[str, Any] = {"name": name, "type": "wanprof"}
        if description:
            shell_data["description"] = description
        add_resp = client.call("add", shell_collection, data=shell_data)
        add_st = _status_of(add_resp)
        if add_st.get("code") != 0:
            return {
                "success": False,
                "action": "created",
                "name": name,
                "adom": adom,
                "error": f"FMG shell-add failed: {add_st}",
            }
        action = "updated" if exists else "created"

        # Update body-level status if the caller asked for something other than default.
        # `update` is partial — safe against the reserved virtual-wan-link seed.
        if status_val != "enable":
            body_upd = client.call("update", body_url, data={"status": status_val})
            body_st = _status_of(body_upd)
            if body_st.get("code") != 0:
                return {
                    "success": False,
                    "action": action,
                    "name": name,
                    "adom": adom,
                    "error": f"FMG body-status update failed: {body_st}",
                }

        # Add children in a dependency-safe order:
        # zones first (members reference them), then members (health-checks and
        # services reference member seq-nums), then health-checks (neighbor
        # references health-check name), then services, then neighbors.
        child_errors: List[Dict[str, Any]] = []
        zone_ok = _add_children(client, body_url, "zone", zone, "name", child_errors)
        member_ok = _add_children(client, body_url, "members", members, "seq_num", child_errors)
        hc_ok = _add_children(client, body_url, "health-check", health_check, "name", child_errors)
        svc_ok = _add_children(client, body_url, "service", service, "name", child_errors)
        nbr_ok = _add_children(client, body_url, "neighbor", neighbor, "ip", child_errors)

        result: Dict[str, Any] = {
            "success": not child_errors,
            "action": action,
            "name": name,
            "adom": adom,
            "zone_count": zone_ok,
            "member_count": member_ok,
            "health_check_count": hc_ok,
            "service_count": svc_ok,
            "neighbor_count": nbr_ok,
        }
        if child_errors:
            result["error"] = (
                f"Shell {action}, but {len(child_errors)} child add(s) failed. "
                "First failure: " + repr(child_errors[0])
            )
            result["child_errors"] = child_errors
        return result

    except Exception as e:
        logger.exception("sdwan-template-create failed")
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
        "name": "sdk-sdwan-tpl-test",
        "status": "enable",
        "zone": [
            {"name": "SDWAN-HUB", "advpn_select": "enable"},
            {"name": "SDWAN-WAN"},
        ],
        "health_check": [
            {"name": "Public_SLA", "server": ["8.8.8.8", "4.2.2.2"]},
        ],
        "description": "SDK smoke test",
        "overwrite": True,
    })), indent=2))
