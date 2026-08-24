#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager CLI Template Create

Create or update a FortiManager 7.6 CLI Template — the workhorse container
that holds a plain FortiOS CLI body or a Jinja2 template body, referenced by
Model Devices during zero-touch provisioning.

Endpoint:
  Collection: /pm/config/adom/{adom}/obj/cli/template
  Named:      /pm/config/adom/{adom}/obj/cli/template/{name}

Multi-line 'script' bodies are stored verbatim — no escaping is applied. FMG
metadata variables use $(VAR) syntax, e.g. set hostname "$(HOSTNAME)".

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

# FMG 7.6 encoding: 0 = plain CLI, 1 = Jinja2. Some builds accept string enums.
_TYPE_TO_INT = {"cli": 0, "jinja": 1}
_TYPE_TO_STR = {"cli": "cli", "jinja": "jinja"}

# FMG status codes that suggest 'type' was rejected as the wrong shape.
# We retry the write once with the string form when we see these.
_TYPE_RETRY_CODES = {-10, -8, -3, -6}


def _status_of(resp: Dict[str, Any]) -> Dict[str, Any]:
    return (resp.get("result", [{}])[0] or {}).get("status") or {}


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}

    name = params.get("name")
    script = params.get("script")
    if not name:
        return {"success": False, "error": "Missing required parameter: name"}
    if script is None or script == "":
        return {"success": False, "error": "Missing required parameter: script"}

    adom = params.get("adom", "root")
    type_str = (params.get("type") or "cli").lower()
    description = params.get("description", "") or ""
    overwrite = bool(params.get("overwrite", False))

    if type_str not in _TYPE_TO_INT:
        return {
            "success": False,
            "error": f"Invalid type {type_str!r}. Use: cli | jinja",
        }

    # Coerce to string in case the caller handed us bytes/other
    script = str(script)
    script_lines = script.count("\n") + (0 if script.endswith("\n") else 1) if script else 0

    def _build_data(type_value: Any) -> Dict[str, Any]:
        return {
            "name": name,
            "script": script,
            "type": type_value,
            "description": description,
        }

    collection_url = f"/pm/config/adom/{adom}/obj/cli/template"
    named_url = f"{collection_url}/{name}"

    try:
        client = FortiManagerClient(host=fmg_host)

        # Existence probe
        existing_resp = client.get(named_url, fields=["name"])
        exists = _status_of(existing_resp).get("code") == 0

        if exists and not overwrite:
            return {
                "success": False,
                "action": "noop",
                "name": name,
                "adom": adom,
                "type": type_str,
                "error": (
                    f"CLI template {name!r} already exists in ADOM {adom!r}. "
                    "Set overwrite=true to update."
                ),
            }

        action = "updated" if exists else "created"

        # First attempt: int-encoded type (0/1) as documented for FMG 7.6
        int_data = _build_data(_TYPE_TO_INT[type_str])
        if exists:
            resp = client.call("update", named_url, data=int_data)
        else:
            resp = client.call("add", collection_url, data=int_data)
        status = _status_of(resp)

        # Fallback: some FMG builds want the enum spelled as a string
        if status.get("code") in _TYPE_RETRY_CODES:
            str_data = _build_data(_TYPE_TO_STR[type_str])
            if exists:
                resp2 = client.call("update", named_url, data=str_data)
            else:
                resp2 = client.call("add", collection_url, data=str_data)
            status2 = _status_of(resp2)
            if status2.get("code") == 0:
                return {
                    "success": True,
                    "action": action,
                    "name": name,
                    "adom": adom,
                    "type": type_str,
                    "script_lines": script_lines,
                    "type_encoding": "string",
                }

        if status.get("code") != 0:
            return {
                "success": False,
                "action": action,
                "name": name,
                "adom": adom,
                "type": type_str,
                "error": f"FMG {status}",
            }

        return {
            "success": True,
            "action": action,
            "name": name,
            "adom": adom,
            "type": type_str,
            "script_lines": script_lines,
            "type_encoding": "int",
        }

    except Exception as e:
        logger.exception("cli-template-create failed")
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
        "name": "sdk-cli-tpl-test",
        "script": (
            "config system global\n"
            "    set admin-lockout-threshold 5\n"
            "    set admin-lockout-duration 60\n"
            "end\n"
        ),
        "type": "cli",
        "description": "SDK smoke test",
        "overwrite": True,
    })), indent=2))
