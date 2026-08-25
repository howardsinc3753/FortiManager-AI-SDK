#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Device Group Create

Create or update a FortiManager DVMDB Device Group in an ADOM.

Device groups are the tenant-scale organizational unit — group all BOR-Single
sites into one group, BOR-Dual into another, and downstream operations (bulk
install, bulk metadata push, template-group scope binding) can target the
group instead of each device individually.

Endpoints (JSON-RPC, per FMG 7.6 GUI curl capture):
  create group (named URL create pattern):
      add /dvmdb/adom/{adom}/group/{name}
      data: {name, desc, type: "normal", meta fields: {}, os_type: "fos"}
  set members (child endpoint on `object member`, space not hyphen):
      set /dvmdb/adom/{adom}/group/{name}/object member
      data: [{name: "spoke-1", vdom: "root"}, ...]
  read members:
      get /dvmdb/adom/{adom}/group/{name}/object member

Field-name quirks (FMG 7.6 accepts these EXACT names, hyphenated equivalents
return -10):
  - `desc`         (NOT `description`)
  - `meta fields`  (space, NOT `meta-fields`)
  - `object member` (space, NOT `object-member`)
  - `os_type`      (underscore, valid values: `fos`, `fsw`, `fpx`, `foc`, `faz`, `fml`, `fdd`, `fac`, `fca`)

MEMBER PERSISTENCE / READBACK QUIRK — FMG 7.6.7 (discovered 2026-08-25):
  Writes on `object member` (set, add, update) all return code=0 OK. However,
  the JSON-RPC API has NO read-back path — GET on the same child endpoint
  returns the parent group's metadata, not the member collection. The device
  side has no `grp` field either. Schema queries confirm: `device_group` has
  no `member` attribute declared.

  The GUI reads membership via `/gui/adoms/{adom_oid}/groups/{grp_oid}?fields=memb`
  through `/cgi-bin/module/flatui_proxy` — but that endpoint requires a session
  COOKIE (Bearer token is rejected as "HTTP 400 need session cookie").

  Practical impact:
    - Tool cannot API-verify membership. `members_verified: null` in output.
    - Return `members_submitted` (what we sent) instead of a readback.
    - User should confirm via FMG GUI: Device Manager → Groups → {name}
    - `member_count` in output reflects what we submitted, not a fresh read.

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


def _status(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the FMG status envelope from a JSON-RPC response."""
    return (resp.get("result", [{}])[0] or {}).get("status") or {}


def _normalize_members(raw: Any) -> List[Dict[str, str]]:
    """Accept members as either a list of strings (device names, vdom defaults to
    'root') or a list of {name, vdom} dicts. Returns a normalized list of dicts.
    Empty/None -> []."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("members must be a list")
    out: List[Dict[str, str]] = []
    for i, m in enumerate(raw):
        if isinstance(m, str):
            n = m.strip()
            if not n:
                raise ValueError(f"members[{i}] is an empty string")
            out.append({"name": n, "vdom": "root"})
        elif isinstance(m, dict):
            n = (m.get("name") or "").strip()
            if not n:
                raise ValueError(f"members[{i}] missing 'name'")
            v = (m.get("vdom") or "root").strip() or "root"
            out.append({"name": n, "vdom": v})
        else:
            raise ValueError(f"members[{i}] must be a string or {{name, vdom}} dict")
    return out


def _find_missing_devices(client: FortiManagerClient, adom: str,
                          members: List[Dict[str, str]]) -> List[str]:
    """Return the subset of member device NAMES that don't exist in DVMDB.
    Best-effort — swallow lookup exceptions to keep the create unblocked."""
    missing: List[str] = []
    for m in members:
        try:
            resp = client.get(f"/dvmdb/adom/{adom}/device/{m['name']}", fields=["name"])
            if _status(resp).get("code") != 0:
                missing.append(m["name"])
        except Exception:
            logger.debug("pre-check lookup failed for %r", m["name"], exc_info=True)
    return missing


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    name = params.get("name")
    if not name:
        return {"success": False, "error": "Missing required parameter: name"}

    adom = params.get("adom", "root")
    desc = params.get("desc") or params.get("description") or ""
    group_type = params.get("type", "normal")  # normal, default (dynamic groups use different path)
    os_type = params.get("os_type", "fos")
    meta_fields = params.get("meta_fields") or params.get("meta fields") or {}
    overwrite = bool(params.get("overwrite", False))
    raw_members = params.get("members")

    if not isinstance(meta_fields, dict):
        return {"success": False, "error": "meta_fields must be an object/dict"}

    try:
        members = _normalize_members(raw_members)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    # Payload shape per user's GUI curl capture — space-fields and desc quirks matter.
    group_data: Dict[str, Any] = {
        "name": name,
        "desc": desc,
        "type": group_type,
        "meta fields": meta_fields,
        "os_type": os_type,
    }

    group_named_url = f"/dvmdb/adom/{adom}/group/{name}"
    members_url = f"/dvmdb/adom/{adom}/group/{name}/object member"

    try:
        client = FortiManagerClient(host=fmg_host)

        # Existence check
        existing = client.get(group_named_url, fields=["name"])
        exists = _status(existing).get("code") == 0

        # Optional pre-check of member devices
        missing_devices = _find_missing_devices(client, adom, members) if members else []

        if exists and not overwrite:
            return {
                "success": False,
                "action": "noop",
                "name": name,
                "adom": adom,
                "member_count": len(members),
                "missing_devices": missing_devices,
                "error": (
                    f"Device group {name!r} already exists in ADOM {adom!r}. "
                    "Set overwrite=true to update (updates desc/type/os_type + REPLACES members)."
                ),
            }

        if exists:
            # Update the top-level group fields
            resp = client.call("update", group_named_url, data=group_data)
            action = "updated"
        else:
            # Create — pattern is `add /dvmdb/adom/{adom}/group/{name}` per GUI curl
            resp = client.call("add", group_named_url, data=group_data)
            action = "created"

        status = _status(resp)
        if status.get("code") != 0:
            return {
                "success": False,
                "action": action,
                "name": name,
                "adom": adom,
                "member_count": len(members),
                "missing_devices": missing_devices,
                "error": f"FMG {status}",
            }

        # Set members (replace) if any were provided. Child endpoint requires
        # `set` on `object member` (space, not hyphen). Empty list clears members.
        members_action = None
        if raw_members is not None:
            mresp = client.call("set", members_url, data=members)
            mstatus = _status(mresp)
            if mstatus.get("code") != 0:
                return {
                    "success": False,
                    "action": f"{action}+members-failed",
                    "name": name,
                    "adom": adom,
                    "member_count": len(members),
                    "missing_devices": missing_devices,
                    "error": f"Group {action} OK but member set failed: FMG {mstatus}",
                }
            members_action = "replaced" if exists else "set"

        # Read back for verification (parent group only — member readback is
        # not supported on this API surface; see module docstring).
        vresp = client.get(group_named_url, fields=["name", "oid", "desc", "type", "os_type"])
        vdata = (vresp.get("result", [{}])[0] or {}).get("data") or {}

        return {
            "success": True,
            "action": action,
            "members_action": members_action,
            "name": name,
            "adom": adom,
            "oid": vdata.get("oid"),
            "os_type": vdata.get("os_type"),
            "type": vdata.get("type"),
            "member_count": len(members),          # what we SENT (write returned code=0)
            "members_submitted": members,          # what we sent — API can't read back
            "members_verified": None,              # None = API-unreachable, not empty
            "missing_devices": missing_devices,
            "verify_hint": (
                f"FMG GUI: Device Manager -> {adom} -> Device Group -> {name} "
                "(JSON-RPC has no member readback on this endpoint)"
            ),
        }

    except Exception as e:
        logger.exception("device-group-create failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "184.73.7.106"
    # Smoke: create BOR_Branch_Single + BOR_Branch_Dual in BOR_Customer_1, seed spoke-1 into Single
    print("--- BOR_Branch_Single (with spoke-1) ---")
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host,
        "adom": "BOR_Customer_1",
        "name": "BOR_Branch_Single",
        "desc": "Single-BOR branches (one WAN circuit + one SASE tunnel per site)",
        "members": [{"name": "spoke-1", "vdom": "root"}],
        "overwrite": True,
    })), indent=2))
    print("\n--- BOR_Branch_Dual (empty; DUAL blueprints land here later) ---")
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host,
        "adom": "BOR_Customer_1",
        "name": "BOR_Branch_Dual",
        "desc": "Dual-BOR branches (two WAN circuits + two SASE tunnels per site)",
        "members": [],
        "overwrite": True,
    })), indent=2))
