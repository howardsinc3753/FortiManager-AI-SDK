#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Task Status

Generic poller for any FMG async task ID.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, Tuple

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)

# FMG state enum — observed mapping; verbose=1 returns strings, without
# verbose returns ints. Normalize to strings everywhere.
_STATE_INT_TO_STR = {
    0: "pending",
    1: "running",
    2: "cancelling",
    3: "cancelled",
    4: "done",
    5: "error",
    6: "aborting",
    7: "aborted",
    8: "warning",
    9: "waiting",
    10: "ready",
}
_TERMINAL_STATES = {"done", "error", "cancelled", "aborted", "warning"}


def _fetch(client: FortiManagerClient, task_id: int) -> Tuple[dict, dict]:
    resp = client.get(f"/task/task/{task_id}", verbose=1)
    result = resp.get("result", [{}])[0]
    status = result.get("status") or {}
    return status, result.get("data") or {}


def _norm_state(val: Any) -> str:
    if isinstance(val, int):
        return _STATE_INT_TO_STR.get(val, str(val))
    return str(val) if val is not None else "unknown"


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    task_id = params.get("task_id")
    if task_id is None:
        return {"success": False, "error": "Missing required parameter: task_id"}
    try:
        task_id = int(task_id)
    except (TypeError, ValueError):
        return {"success": False, "error": f"task_id must be an integer, got: {task_id!r}"}

    wait = bool(params.get("wait", False))
    poll_interval = float(params.get("poll_interval_sec", 2))
    max_wait = int(params.get("max_wait_sec", 120))
    include_lines = params.get("include_lines", True)
    include_history = params.get("include_history", False)

    try:
        client = FortiManagerClient(host=fmg_host)
        start = time.monotonic()
        waited = 0.0
        timed_out = False

        while True:
            status, data = _fetch(client, task_id)
            if status.get("code") != 0:
                return {"success": False, "error": f"FMG {status}"}
            state_str = _norm_state(data.get("state"))
            if not wait or state_str in _TERMINAL_STATES:
                break
            waited = time.monotonic() - start
            if waited >= max_wait:
                timed_out = True
                break
            await asyncio.sleep(poll_interval)

        state_str = _norm_state(data.get("state"))
        is_terminal = state_str in _TERMINAL_STATES
        num_err = int(data.get("num_err") or 0)

        out: Dict[str, Any] = {
            "success": is_terminal and num_err == 0 and not timed_out,
            "task_id": task_id,
            "state": state_str,
            "state_is_terminal": is_terminal,
            "percent": int(data.get("percent") or 0),
            "num_lines": int(data.get("num_lines") or 0),
            "num_done": int(data.get("num_done") or 0),
            "num_err": num_err,
            "num_warn": int(data.get("num_warn") or 0),
            "title": data.get("title") or "",
            "src": _norm_state(data.get("src")),
            "user": data.get("user") or "",
            "start_tm": int(data.get("start_tm") or 0),
            "end_tm": int(data.get("end_tm") or 0),
            "elapsed_sec": max(0, int((data.get("end_tm") or 0) - (data.get("start_tm") or 0))) if data.get("end_tm") else 0,
            "waited_sec": round(waited, 2),
            "timed_out": timed_out,
        }

        if include_lines:
            lines = []
            for ln in (data.get("line") or []):
                lines.append({
                    "name": ln.get("name") or "",
                    "vdom": ln.get("vdom") or "",
                    "ip": ln.get("ip") or "",
                    "state": _norm_state(ln.get("state")),
                    "percent": int(ln.get("percent") or 0),
                    "detail": ln.get("detail") or "",
                    "err": int(ln.get("err") or 0),
                })
            out["lines"] = lines

        if include_history:
            out["history"] = data.get("history") or []

        return out

    except Exception as e:
        logger.exception("task-status failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    tid = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    print(json.dumps(
        asyncio.run(execute({"fmg_host": host, "task_id": tid})),
        indent=2,
    ))
