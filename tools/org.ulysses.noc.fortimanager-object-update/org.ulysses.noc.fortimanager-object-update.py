#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Object Update

Partial update of any FMG object via method=update on a named-entity URL.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)


def _escape_url(url: str) -> str:
    """Escape `/` in the last path segment only (entity name). The URL
    structure delimiters must stay as-is."""
    if url.endswith("/"):
        url = url.rstrip("/")
    # Find the LAST segment (after final `/`), escape internal `/` inside it.
    # We can't tell where the table path ends vs name begins, so a reliable
    # approach is to leave URL alone but allow caller to pre-escape. For the
    # common case where the final segment is an unescaped name, we do nothing
    # here — FMG accepts URLs without escaping when names don't contain `/`.
    return url


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    url = params.get("url")
    if not url:
        return {"success": False, "error": "Missing required parameter: url"}
    data = params.get("data")
    if not isinstance(data, dict):
        return {"success": False, "error": "Missing or invalid parameter: data (must be object)"}
    unset_attrs = params.get("unset_attrs")

    if unset_attrs:
        data = dict(data)
        data["unset attrs"] = list(unset_attrs)

    try:
        client = FortiManagerClient(host=fmg_host)
        resp = client.call("update", _escape_url(url), data=data)
        status = resp.get("result", [{}])[0].get("status") or {}
        if status.get("code") != 0:
            return {"success": False, "url": url, "error": f"FMG {status}"}
        return {"success": True, "url": url}

    except Exception as e:
        logger.exception("object-update failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    # Default smoke: update the VIP comment
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host,
        "url": "/pm/config/adom/root/obj/firewall/vip/sdk-vip-test",
        "data": {"comment": "Updated via SDK object-update at runtime", "color": 4},
    })), indent=2))
