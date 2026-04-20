#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Model Device Create

Create a placeholder (model) device in FMG DVM via exec /dvm/cmd/add/dev-list.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)

_STATE_INT_TO_STR = {
    0: "pending", 1: "running", 2: "cancelling", 3: "cancelled",
    4: "done", 5: "error", 6: "aborting", 7: "aborted",
    8: "warning", 9: "waiting", 10: "ready",
}
_TERMINAL = {"done", "error", "cancelled", "aborted", "warning"}


def _norm_state(v: Any) -> str:
    if isinstance(v, int):
        return _STATE_INT_TO_STR.get(v, str(v))
    return str(v) if v is not None else "unknown"


async def _poll_task(client: FortiManagerClient, task_id: int, max_wait: int) -> tuple[str, int]:
    start = time.monotonic()
    state = "pending"; num_err = 0
    while time.monotonic() - start < max_wait:
        r = client.get(f"/task/task/{task_id}", verbose=1)
        data = r.get("result", [{}])[0].get("data") or {}
        state = _norm_state(data.get("state"))
        num_err = int(data.get("num_err") or 0)
        if state in _TERMINAL:
            return state, num_err
        await asyncio.sleep(2)
    return state, num_err


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    for req in ("adom", "name", "sn", "platform"):
        if not params.get(req):
            return {"success": False, "error": f"Missing required parameter: {req}"}

    adom = params["adom"]
    name = params["name"]
    sn = params["sn"]
    platform = params["platform"]
    os_type = int(params.get("os_type", 0))
    os_ver = int(params.get("os_ver", 7))
    mr = int(params.get("mr", 6))
    adm_usr = params.get("adm_usr", "admin")
    description = params.get("description", "") or ""
    mgmt_mode = int(params.get("mgmt_mode", 3))
    blueprint = params.get("blueprint")
    extra_commands = params.get("extra_commands") or []
    wait = bool(params.get("wait", True))
    max_wait = int(params.get("max_wait_sec", 60))

    add_entry: Dict[str, Any] = {
        "name": name,
        "sn": sn,
        "_platform": platform,
        "os_type": os_type,
        "os_ver": os_ver,
        "mr": mr,
        "device action": "add_model",
        "adm_usr": adm_usr,
        "desc": description,
        "mgmt_mode": mgmt_mode,
    }
    if blueprint:
        add_entry["device blueprint"] = blueprint
    if extra_commands:
        add_entry["extra commands"] = list(extra_commands)

    data_body: Dict[str, Any] = {
        "adom": adom,
        "flags": ["create_task", "nonblocking"],
        "add-dev-list": [add_entry],
    }

    try:
        client = FortiManagerClient(host=fmg_host)
        if client.auth_method == "session" and not client.session:
            client.login()

        payload = {
            "id": client._next_id(),
            "method": "exec",
            "params": [{"url": "/dvm/cmd/add/dev-list", "data": data_body}],
        }
        if client.session:
            payload["session"] = client.session

        resp = client._request(payload)
        result = resp.get("result", [{}])[0]
        status = result.get("status") or {}
        if status.get("code") != 0:
            return {
                "success": False, "name": name, "adom": adom,
                "error": f"FMG exec error: {status}",
            }

        task_id = (result.get("data") or {}).get("taskid") or (result.get("data") or {}).get("task")
        if task_id is not None:
            task_id = int(task_id)

        out: Dict[str, Any] = {
            "success": True, "name": name, "adom": adom,
            "task_id": task_id, "state": "pending", "device_oid": None,
        }

        if wait and task_id:
            final_state, num_err = await _poll_task(client, task_id, max_wait)
            out["state"] = final_state
            out["success"] = (final_state in _TERMINAL) and num_err == 0

        # Verify device landed
        probe = client.get(f"/dvmdb/adom/{adom}/device/{name}", fields=["name", "oid", "sn"])
        probe_status = probe.get("result", [{}])[0].get("status") or {}
        if probe_status.get("code") == 0:
            d = probe.get("result", [{}])[0].get("data") or {}
            out["device_oid"] = d.get("oid")
        else:
            out["success"] = False
            out["error"] = "Device not in DVM after create — task may have failed silently"

        return out

    except Exception as e:
        logger.exception("model-device-create failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    name = sys.argv[2] if len(sys.argv) > 2 else "sdk-smoke-model"
    sn = sys.argv[3] if len(sys.argv) > 3 else "FGT60FTK12345678"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host, "adom": "root", "name": name, "sn": sn,
        "platform": "FortiGate-60F",
        "description": "SDK smoke test model device",
    })), indent=2))
