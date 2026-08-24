#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager CLI Template Group Create

Create or update a FortiManager CLI Template Group — the ordered bundle of CLI
templates FMG applies to a device in sequence at install time.

Endpoint:
  collection : /pm/config/adom/{adom}/obj/cli/template-group
  named      : /pm/config/adom/{adom}/obj/cli/template-group/{name}

Payload shape FMG 7.6 expects (schema-verified against
/pm/config/adom/{adom}/obj/cli/template-group with option=syntax):

    {
      "name": "sdwan-build",
      "description": "...",
      "member": ["system", "interface", "static", "ipsec", "bgp", "sdwan"]
    }

`member` is a flat `datasrc` list of CLI template names. The FMG GUI preserves
the order the array is submitted in for install-time execution, so we keep
whatever order the caller passed — never sort.

Optional pre-check: for each member, GET
/pm/config/adom/{adom}/obj/cli/template/{tpl_name} and report any that don't
yet exist via `missing_templates`. FMG allows references to templates that
don't exist yet — they resolve at install time — so this is warning-only and
does NOT block creation.

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


def _status(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the FMG status envelope from a JSON-RPC response."""
    return (resp.get("result", [{}])[0] or {}).get("status") or {}


def _find_missing_templates(client: FortiManagerClient, adom: str,
                            members: List[str]) -> List[str]:
    """Return the subset of members whose underlying CLI template is not
    present in the ADOM. Best-effort — any lookup exception is swallowed
    (we don't want the pre-check to break the create)."""
    missing: List[str] = []
    for tpl in members:
        try:
            resp = client.get(
                f"/pm/config/adom/{adom}/obj/cli/template/{tpl}",
                fields=["name"],
            )
            if _status(resp).get("code") != 0:
                missing.append(tpl)
        except Exception:
            # Pre-check is advisory; never let it block the create.
            logger.debug("pre-check lookup failed for %r", tpl, exc_info=True)
    return missing


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    name = params.get("name")
    if not name:
        return {"success": False, "error": "Missing required parameter: name"}

    raw_members = params.get("members")
    if raw_members is None:
        return {"success": False, "error": "Missing required parameter: members"}
    if not isinstance(raw_members, list) or not raw_members:
        return {"success": False, "error": "'members' must be a non-empty list of CLI template names"}
    # Preserve caller-provided order verbatim; strip only whitespace.
    members: List[str] = []
    for i, m in enumerate(raw_members):
        if not isinstance(m, str) or not m.strip():
            return {"success": False, "error": f"members[{i}] must be a non-empty string"}
        members.append(m.strip())

    adom = params.get("adom", "root")
    description = params.get("description", "") or ""
    overwrite = bool(params.get("overwrite", False))

    # FMG 7.6 wants a flat list of template names for `member` (schema-verified
    # via option=syntax). Order is preserved verbatim — do NOT sort here; order
    # == install-time execution order.
    data: Dict[str, Any] = {
        "name": name,
        "member": list(members),
    }
    if description:
        data["description"] = description

    collection_url = f"/pm/config/adom/{adom}/obj/cli/template-group"
    named_url = f"{collection_url}/{name}"

    try:
        client = FortiManagerClient(host=fmg_host)

        # Existence check
        existing = client.get(named_url, fields=["name"])
        exists = _status(existing).get("code") == 0

        # Warning-only pre-check: which member templates don't exist yet?
        missing_templates = _find_missing_templates(client, adom, members)

        if exists and not overwrite:
            return {
                "success": False,
                "action": "noop",
                "name": name,
                "adom": adom,
                "member_count": len(members),
                "members": members,
                "missing_templates": missing_templates,
                "error": (
                    f"CLI template group {name!r} already exists in ADOM {adom!r}. "
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
                "member_count": len(members),
                "members": members,
                "missing_templates": missing_templates,
                "error": f"FMG {status}",
            }

        return {
            "success": True,
            "action": action,
            "name": name,
            "adom": adom,
            "member_count": len(members),
            "members": members,
            "missing_templates": missing_templates,
        }

    except Exception as e:
        logger.exception("cli-template-group-create failed")
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
        "name": "sdk-cli-grp-test",
        "members": ["sdk-cli-tpl-test"],
        "description": "SDK smoke test",
        "overwrite": True,
    })), indent=2))
