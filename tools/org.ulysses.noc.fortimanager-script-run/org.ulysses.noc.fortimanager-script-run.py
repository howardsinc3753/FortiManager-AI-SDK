#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Script Run

Execute a named FortiManager CLI script against a policy package, device(s),
or device group(s). Optionally waits for task completion and fetches log output.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

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
_TERMINAL_STATES = {"done", "error", "cancelled", "aborted", "warning"}


def _norm_state(val: Any) -> str:
    if isinstance(val, int):
        return _STATE_INT_TO_STR.get(val, str(val))
    return str(val) if val is not None else "unknown"


def _normalize_task_ids(raw: Any) -> List[int]:
    """FMG Swagger says task is [string]; live returns int. Handle both."""
    if raw is None:
        return []
    if isinstance(raw, int):
        return [raw]
    if isinstance(raw, list):
        out: List[int] = []
        for v in raw:
            try:
                out.append(int(v))
            except (TypeError, ValueError):
                continue
        return out
    try:
        return [int(raw)]
    except (TypeError, ValueError):
        return []


async def _poll_task(client: FortiManagerClient, task_id: int,
                     poll_interval: float, max_wait: int) -> tuple[Dict[str, Any], float, bool]:
    start = time.monotonic()
    waited = 0.0
    while True:
        resp = client.get(f"/task/task/{task_id}", verbose=1)
        result = resp.get("result", [{}])[0]
        status = result.get("status") or {}
        if status.get("code") != 0:
            raise RuntimeError(f"FMG polling error: {status}")
        data = result.get("data") or {}
        state = _norm_state(data.get("state"))
        if state in _TERMINAL_STATES:
            return data, round(time.monotonic() - start, 2), False
        waited = time.monotonic() - start
        if waited >= max_wait:
            return data, round(waited, 2), True
        await asyncio.sleep(poll_interval)


def _derive_log_id(task_id: int, scope_type: str) -> int:
    """FMG convention: log_id = str(task_id) + '1' for DB/package, + '0' for device."""
    suffix = "1" if scope_type == "package" else "0"
    return int(f"{task_id}{suffix}")


def _fetch_log(client: FortiManagerClient, adom: str, log_id: int,
               scope_type: str, device_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Fetch script log. Try derived-log_id path first, fall back to /latest."""
    tries: List[str] = []
    if scope_type == "device" and device_name:
        tries.append(f"/dvmdb/adom/{adom}/script/log/output/device/{device_name}/logid/{log_id}")
        tries.append(f"/dvmdb/adom/{adom}/script/log/latest/device/{device_name}")
    else:
        tries.append(f"/dvmdb/adom/{adom}/script/log/output/logid/{log_id}")
        tries.append(f"/dvmdb/adom/{adom}/script/log/latest")
    for url in tries:
        try:
            resp = client.get(url)
            result = resp.get("result", [{}])[0]
            if (result.get("status") or {}).get("code") != 0:
                continue
            data = result.get("data") or {}
            if data.get("content") is not None:
                return {
                    "content": data.get("content"),
                    "exec_time": data.get("exec_time"),
                    "script_name": data.get("script_name"),
                    "log_id": data.get("log_id"),
                }
        except Exception:
            continue
    return None


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    script = params.get("script")
    if not script:
        return {"success": False, "error": "Missing required parameter: script"}

    adom = params.get("adom", "root")
    scope_type = (params.get("scope_type") or "device").lower()
    if scope_type not in {"package", "device", "group"}:
        return {"success": False, "error": f"scope_type must be package|device|group (got {scope_type!r})"}

    wait = bool(params.get("wait", True))
    poll_interval = float(params.get("poll_interval_sec", 2))
    max_wait = int(params.get("max_wait_sec", 180))
    fetch_log = bool(params.get("fetch_log", True))

    # Build the exec-data envelope per scope type
    data_body: Dict[str, Any] = {"adom": adom, "script": script}
    first_device: Optional[str] = None

    if scope_type == "package":
        pkg = params.get("package")
        if not pkg:
            return {"success": False, "error": "scope_type=package requires 'package' parameter"}
        data_body["package"] = pkg
    elif scope_type == "device":
        scope = params.get("scope") or []
        if not scope:
            return {"success": False, "error": "scope_type=device requires 'scope' (array of {name, vdom})"}
        # Normalize: accept list of dicts; reject anything else
        norm_scope = []
        for s in scope:
            if not isinstance(s, dict) or not s.get("name"):
                return {"success": False, "error": f"scope entry invalid: {s!r}"}
            entry = {"name": s["name"]}
            if s.get("vdom"):
                entry["vdom"] = s["vdom"]
            norm_scope.append(entry)
        data_body["scope"] = norm_scope
        first_device = norm_scope[0]["name"]
    else:  # group
        groups = params.get("groups") or []
        if not groups:
            return {"success": False, "error": "scope_type=group requires 'groups' (array of group names)"}
        data_body["scope"] = [{"name": g} for g in groups]

    exec_url = f"/dvmdb/adom/{adom}/script/execute"

    try:
        client = FortiManagerClient(host=fmg_host)
        exec_resp = client.exec(exec_url, data=data_body)
        exec_result = exec_resp.get("result", [{}])[0]
        exec_status = exec_result.get("status") or {}
        if exec_status.get("code") != 0:
            return {
                "success": False,
                "script": script, "adom": adom,
                "error": f"FMG exec error: {exec_status}",
            }

        task_ids = _normalize_task_ids((exec_result.get("data") or {}).get("task"))
        if not task_ids:
            return {
                "success": False, "script": script, "adom": adom,
                "error": "FMG returned no task ID",
            }
        task_id = task_ids[0]

        out: Dict[str, Any] = {
            "success": True, "task_id": task_id, "log_id": None,
            "script": script, "adom": adom,
            "state": "pending", "percent": 0,
            "num_err": 0, "num_done": 0, "num_lines": 0,
            "waited_sec": 0.0, "timed_out": False,
            "lines": [], "log": None,
        }

        if not wait:
            return out  # fire-and-forget

        data, waited, timed_out = await _poll_task(client, task_id, poll_interval, max_wait)
        state = _norm_state(data.get("state"))
        num_err = int(data.get("num_err") or 0)

        out.update({
            "state": state,
            "percent": int(data.get("percent") or 0),
            "num_err": num_err,
            "num_done": int(data.get("num_done") or 0),
            "num_lines": int(data.get("num_lines") or 0),
            "waited_sec": waited,
            "timed_out": timed_out,
            "lines": [
                {
                    "name": ln.get("name") or "",
                    "vdom": ln.get("vdom") or "",
                    "ip": ln.get("ip") or "",
                    "state": _norm_state(ln.get("state")),
                    "percent": int(ln.get("percent") or 0),
                    "detail": ln.get("detail") or "",
                    "err": int(ln.get("err") or 0),
                }
                for ln in (data.get("line") or [])
            ],
        })
        out["success"] = (state in _TERMINAL_STATES) and num_err == 0 and not timed_out

        if fetch_log and state in _TERMINAL_STATES and not timed_out:
            log_id = _derive_log_id(task_id, scope_type)
            out["log_id"] = log_id
            log = _fetch_log(client, adom, log_id, scope_type, first_device)
            if log:
                out["log"] = log

        return out

    except Exception as e:
        logger.exception("script-run failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    # Usage: script-run.py <fmg_host> <adom> <script_name> <device_name> [vdom]
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    adom = sys.argv[2] if len(sys.argv) > 2 else "root"
    script = sys.argv[3] if len(sys.argv) > 3 else "sdk-smoke-test"
    dev = sys.argv[4] if len(sys.argv) > 4 else "howard-sdwan-spoke-1"
    vdom = sys.argv[5] if len(sys.argv) > 5 else "root"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host, "adom": adom, "script": script,
        "scope_type": "device",
        "scope": [{"name": dev, "vdom": vdom}],
        "wait": True, "max_wait_sec": 60,
    })), indent=2))
