#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Template Bind To Device

Bind a provisioning template (System / CLI Template Group / SDWAN) to a
device or model device in FMG by merging the device into the template's
`scope-member` array.

FMG's provisioning-template binding model: each template has a `scope-member`
array of ``{name: <device>, vdom: <vdom>}`` entries. Membership is the bind.
`scope-member` is REPLACED on write, not appended — so this tool always
reads the current list, merges in the caller's device (deduped by
(name, vdom)), and writes the full merged list back via ``update``.

Template-type -> endpoint layout:
  system     -> /pm/config/adom/{adom}/devprof/{name}
                fallback: /pm/devprof/adom/{adom}/{name}
  cli-group  -> /pm/config/adom/{adom}/obj/cli/template-group/{name}
  sdwan      -> /pm/config/adom/{adom}/obj/system/sdwan/{name}

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)

# FMG return codes that indicate "URL doesn't exist at this path"; we swap layouts.
_URL_NOT_FOUND_CODES = {-3, -6}

_VALID_TYPES = ("system", "cli-group", "sdwan")


def _status(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the FMG status envelope from a JSON-RPC response."""
    return (resp.get("result", [{}])[0] or {}).get("status") or {}


def _data(resp: Dict[str, Any]) -> Any:
    """Extract the data payload from a JSON-RPC response."""
    return (resp.get("result", [{}])[0] or {}).get("data")


def _candidate_urls(template_type: str, adom: str, name: str) -> List[str]:
    """Return the ordered list of URLs to try for this template type."""
    if template_type == "system":
        return [
            f"/pm/config/adom/{adom}/devprof/{name}",
            f"/pm/devprof/adom/{adom}/{name}",
        ]
    if template_type == "cli-group":
        return [f"/pm/config/adom/{adom}/obj/cli/template-group/{name}"]
    if template_type == "sdwan":
        return [f"/pm/config/adom/{adom}/obj/system/sdwan/{name}"]
    return []


def _resolve_template(
    client: FortiManagerClient, template_type: str, adom: str, name: str
) -> Tuple[Optional[str], Any, Optional[Dict[str, Any]]]:
    """Locate the template and return (url_used, data, first_real_error).

    Walks the candidate URLs. If a candidate returns code 0, that URL and its
    data payload are returned. If a candidate returns "URL not found", we try
    the next. Any other error is captured as the "real" error to surface if
    no URL succeeds.
    """
    first_err: Optional[Dict[str, Any]] = None
    for url in _candidate_urls(template_type, adom, name):
        resp = client.get(url, option=["scope member"])
        st = _status(resp)
        code = st.get("code")
        if code == 0:
            return url, _data(resp), None
        if code in _URL_NOT_FOUND_CODES:
            if first_err is None:
                first_err = st
            continue
        # Real error (permission denied, ADOM missing, etc.)
        return None, None, st
    return None, None, first_err


def _normalize_scope_members(raw: Any) -> List[Dict[str, str]]:
    """Coerce whatever FMG returned into a list of {name, vdom} dicts."""
    if not raw:
        return []
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name:
            continue
        out.append({"name": str(name), "vdom": str(entry.get("vdom", "root"))})
    return out


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}

    template_type = (params.get("template_type") or "").lower()
    if template_type not in _VALID_TYPES:
        return {
            "success": False,
            "error": f"Invalid template_type {template_type!r}. Use: {' | '.join(_VALID_TYPES)}",
        }

    template_name = params.get("template_name")
    if not template_name:
        return {"success": False, "error": "Missing required parameter: template_name"}

    device = params.get("device")
    if not device:
        return {"success": False, "error": "Missing required parameter: device"}

    adom = params.get("adom", "root")
    vdom = params.get("vdom", "root")
    dry_run = bool(params.get("dry_run", False))

    try:
        client = FortiManagerClient(host=fmg_host)

        # 1. Locate the template + read its current scope-member.
        url, tpl_data, err = _resolve_template(client, template_type, adom, template_name)
        if err is not None:
            code = err.get("code")
            if code in _URL_NOT_FOUND_CODES:
                return {
                    "success": False,
                    "template_type": template_type,
                    "template_name": template_name,
                    "adom": adom,
                    "error": (
                        f"Template {template_name!r} (type={template_type}) "
                        f"not found in ADOM {adom!r}"
                    ),
                }
            return {
                "success": False,
                "template_type": template_type,
                "template_name": template_name,
                "adom": adom,
                "error": f"FMG {err}",
            }
        if url is None:
            return {
                "success": False,
                "template_type": template_type,
                "template_name": template_name,
                "adom": adom,
                "error": (
                    f"Template {template_name!r} (type={template_type}) "
                    f"not found in ADOM {adom!r}"
                ),
            }

        # tpl_data may be dict (named-URL GET) or list (single-entry list).
        if isinstance(tpl_data, list):
            tpl_data = tpl_data[0] if tpl_data else {}
        raw_scope = (tpl_data or {}).get("scope member") or (tpl_data or {}).get("scope-member")
        existing = _normalize_scope_members(raw_scope)

        # 2. Merge (dedupe by (name, vdom)).
        want = {"name": str(device), "vdom": str(vdom)}
        already = any(m["name"] == want["name"] and m["vdom"] == want["vdom"] for m in existing)
        merged = list(existing) if already else existing + [want]

        # 3. Dry run: return what we would POST without touching FMG.
        if dry_run:
            return {
                "success": True,
                "action": "dry-run",
                "template_type": template_type,
                "template_name": template_name,
                "adom": adom,
                "would_bind_device": want["name"],
                "would_bind_vdom": want["vdom"],
                "existing_scope_members": existing,
                "new_scope_members": merged,
                "endpoint_used": url,
            }

        # 4. Idempotent: skip the write if already bound.
        if already:
            return {
                "success": True,
                "action": "already-bound",
                "template_type": template_type,
                "template_name": template_name,
                "adom": adom,
                "device": want["name"],
                "vdom": want["vdom"],
                "scope_members_after": len(merged),
                "endpoint_used": url,
            }

        # 5. Write the merged list back. FMG accepts both spellings; we send
        # both to match the flavor FMG returned in step 1.
        payload = {"scope member": merged, "scope-member": merged}
        resp = client.call("update", url, data=payload)
        st = _status(resp)
        if st.get("code") != 0:
            return {
                "success": False,
                "action": "bound",
                "template_type": template_type,
                "template_name": template_name,
                "adom": adom,
                "device": want["name"],
                "vdom": want["vdom"],
                "endpoint_used": url,
                "error": f"FMG {st}",
            }

        return {
            "success": True,
            "action": "bound",
            "template_type": template_type,
            "template_name": template_name,
            "adom": adom,
            "device": want["name"],
            "vdom": want["vdom"],
            "scope_members_after": len(merged),
            "endpoint_used": url,
        }

    except Exception as e:
        logger.exception("template-bind-to-device failed")
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
        "template_type": "sdwan",
        "template_name": "sdk-sdwan-tpl-test",
        "device": "spoke-test-01",
        "vdom": "root",
        "dry_run": True,
    })), indent=2))
