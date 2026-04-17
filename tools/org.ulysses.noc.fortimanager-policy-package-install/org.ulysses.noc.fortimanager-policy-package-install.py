#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Policy Package Install

Install a policy package to target devices via exec /securityconsole/install/package.
Async — returns task ID; optionally polls until completion.

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


def _norm(v: Any) -> str:
    if isinstance(v, int):
        return _STATE_INT_TO_STR.get(v, str(v))
    return str(v) if v is not None else "unknown"


async def _poll(client: FortiManagerClient, task_id: int,
                poll_interval: float, max_wait: int) -> tuple[Dict[str, Any], float, bool]:
    start = time.monotonic()
    while True:
        resp = client.get(f"/task/task/{task_id}", verbose=1)
        result = resp.get("result", [{}])[0]
        status = result.get("status") or {}
        if status.get("code") != 0:
            raise RuntimeError(f"FMG polling: {status}")
        data = result.get("data") or {}
        state = _norm(data.get("state"))
        waited = time.monotonic() - start
        if state in _TERMINAL:
            return data, round(waited, 2), False
        if waited >= max_wait:
            return data, round(waited, 2), True
        await asyncio.sleep(poll_interval)


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    package = params.get("package")
    if not package:
        return {"success": False, "error": "Missing required parameter: package"}
    scope = params.get("scope") or []
    if not scope:
        return {"success": False, "error": "Missing required parameter: scope (array of {name, vdom})"}

    adom = params.get("adom", "root")
    flags = params.get("flags") or ["none"]
    dev_rev_comments = params.get("dev_rev_comments") or "Installed via FortiManager AI SDK"
    wait = bool(params.get("wait", True))
    poll_interval = float(params.get("poll_interval_sec", 3))
    max_wait = int(params.get("max_wait_sec", 300))

    # Normalize scope
    norm_scope = []
    for s in scope:
        if not isinstance(s, dict) or not s.get("name"):
            return {"success": False, "error": f"Invalid scope entry: {s!r}"}
        entry = {"name": s["name"]}
        entry["vdom"] = s.get("vdom") or "root"
        norm_scope.append(entry)

    body = {
        "adom": adom,
        "pkg": package,
        "scope": norm_scope,
        "flags": flags,
        "dev_rev_comments": dev_rev_comments,
    }

    try:
        client = FortiManagerClient(host=fmg_host)
        resp = client.exec("/securityconsole/install/package", data=body)
        result = resp.get("result", [{}])[0]
        fmg_status = result.get("status") or {}
        if fmg_status.get("code") != 0:
            return {
                "success": False, "adom": adom, "package": package,
                "error": f"FMG exec error: {fmg_status}",
            }

        task_id = (result.get("data") or {}).get("task")
        if task_id is None:
            return {
                "success": False, "adom": adom, "package": package,
                "error": "FMG returned no task ID",
            }
        task_id = int(task_id)

        out: Dict[str, Any] = {
            "success": True, "task_id": task_id,
            "adom": adom, "package": package,
            "state": "pending", "percent": 0,
            "num_err": 0, "num_done": 0, "num_lines": 0,
            "waited_sec": 0.0, "timed_out": False, "lines": [],
        }

        if not wait:
            return out

        data, waited, timed_out = await _poll(client, task_id, poll_interval, max_wait)
        state = _norm(data.get("state"))
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
                    "state": _norm(ln.get("state")),
                    "percent": int(ln.get("percent") or 0),
                    "detail": ln.get("detail") or "",
                    "err": int(ln.get("err") or 0),
                }
                for ln in (data.get("line") or [])
            ],
        })
        out["success"] = (state in _TERMINAL) and num_err == 0 and not timed_out
        return out

    except Exception as e:
        logger.exception("policy-package-install failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    pkg = sys.argv[2] if len(sys.argv) > 2 else "howard-sdwan-spoke-1"
    dev = sys.argv[3] if len(sys.argv) > 3 else "howard-sdwan-spoke-1"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host, "adom": "root", "package": pkg,
        "scope": [{"name": dev, "vdom": "root"}],
        "wait": True, "max_wait_sec": 180,
    })), indent=2))
