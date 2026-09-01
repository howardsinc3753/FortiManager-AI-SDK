#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Install Push - fire install for a device (Phase 3 of BOR-SASE workflow).

Equivalent to right-clicking "Install Wizard" on a device in the FMG GUI.

Wraps `exec /securityconsole/install/device`, which pushes BOTH CLI templates AND
the assigned Policy Package to the specified device(s). Task-based - polls to
terminal state and returns structured result with per-device install log lines.

Modes:
  preview_only=True  -> `flags: ["preview"]` - FMG generates a preview rev,
                         validates the config, does NOT commit to device.
                         Safe for CI validation or partner dry-runs.
  preview_only=False -> `flags: ["none"]` - real push. Default. Matches GUI
                         Install Wizard behavior.

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
_TERMINAL = {"done", "error", "cancelled", "aborted", "warning"}


def _norm(v: Any) -> str:
    if isinstance(v, int):
        return _STATE_INT_TO_STR.get(v, str(v))
    return str(v) if v is not None else "unknown"


async def _poll(client: FortiManagerClient, task_id: int,
                poll_interval: float, max_wait: int) -> Dict[str, Any]:
    """Poll a task to terminal state. Returns {state, num_err, num_done,
    percent, waited_sec, timed_out, lines}. Matches working
    device-settings-install task-line shape."""
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
        if state in _TERMINAL or waited >= max_wait:
            timed_out = state not in _TERMINAL
            return {
                "state": state if not timed_out else "timeout",
                "num_err": int(data.get("num_err") or 0),
                "num_done": int(data.get("num_done") or 0),
                "percent": int(data.get("percent") or data.get("tot_percent") or 0),
                "waited_sec": round(waited, 2),
                "timed_out": timed_out,
                "lines": [
                    {
                        "name": ln.get("name") or "",
                        "vdom": ln.get("vdom") or "",
                        "ip": ln.get("ip") or "",
                        "state": _norm(ln.get("state")),
                        "percent": int(ln.get("percent") or 0),
                        "detail": (ln.get("detail") or "")[:400],
                        "err": int(ln.get("err") or 0),
                    }
                    for ln in (data.get("line") or [])
                ],
            }
        await asyncio.sleep(poll_interval)


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    for req in ("adom", "device"):
        if not params.get(req):
            return {"success": False, "error": f"Missing required parameter: {req}"}

    adom = params["adom"]
    device = params["device"]
    vdom = params.get("vdom", "root")
    preview_only = bool(params.get("preview_only", False))
    poll_interval = float(params.get("poll_interval_sec", 3))
    max_wait = int(params.get("max_wait_sec", 300))
    dev_rev_comments = params.get(
        "dev_rev_comments",
        f"install-push via FortiManager AI SDK (preview_only={preview_only})",
    )

    # Support single device (str) or list of devices
    if isinstance(device, list):
        scope = [{"name": d, "vdom": vdom} for d in device]
    else:
        scope = [{"name": device, "vdom": vdom}]

    body = {
        "adom": adom,
        "scope": scope,
        "flags": ["preview"] if preview_only else ["none"],
        "dev_rev_comments": dev_rev_comments,
    }

    result: Dict[str, Any] = {
        "success": False, "adom": adom, "device": device, "vdom": vdom,
        "preview_only": preview_only,
    }

    try:
        client = FortiManagerClient(host=fmg_host)
    except Exception as e:
        result["error"] = f"Client init failed: {type(e).__name__}: {e}"
        return result

    # Fire install/device (does preview OR real install based on flags)
    try:
        resp = client.exec("/securityconsole/install/device", data=body)
        r0 = resp.get("result", [{}])[0]
        st = r0.get("status") or {}
        if st.get("code") != 0:
            result["exec_status"] = {"code": st.get("code"),
                                     "message": (st.get("message") or "")[:300]}
            result["error"] = f"install/device exec failed: {st}"
            return result

        task_id = (r0.get("data") or {}).get("task")
        if task_id is None:
            result["error"] = "install/device returned no task ID"
            return result
        task_id = int(task_id)
        result["task_id"] = task_id

        # Poll to terminal state
        task_result = await _poll(client, task_id, poll_interval, max_wait)
        result.update(task_result)

        # Verdict
        state = task_result["state"]
        num_err = task_result["num_err"]
        if state == "done" and num_err == 0:
            result["success"] = True
            result["action"] = "preview-passed" if preview_only else "installed"
        elif state == "warning":
            result["success"] = True
            result["action"] = ("preview-passed-with-warnings" if preview_only
                                else "installed-with-warnings")
        elif state == "timeout":
            result["error"] = f"task {task_id} did not reach terminal state within {max_wait}s"
            result["action"] = "timeout"
        else:
            result["action"] = "preview-failed" if preview_only else "install-failed"
            # Surface first error line if we have one
            for ln in task_result.get("lines") or []:
                if ln.get("err") or "error" in (ln.get("detail") or "").lower():
                    result["error"] = (f"task {task_id} ended in state '{state}' "
                                       f"(num_err={num_err}): {ln.get('detail', '')[:200]}")
                    break
            if "error" not in result:
                result["error"] = (f"task {task_id} ended in state '{state}', num_err={num_err}")
    except Exception as e:
        logger.exception("install-push failed")
        result["error"] = f"{type(e).__name__}: {e}"

    return result


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    import argparse
    parser = argparse.ArgumentParser(
        description="Fire install (or install-preview) for a device - equivalent to GUI Install Wizard.",
    )
    parser.add_argument("--fmg-host", required=True)
    parser.add_argument("--adom", required=True)
    parser.add_argument("--device", required=True,
                        help="Device name; repeat --device for multiple devices")
    parser.add_argument("--vdom", default="root")
    parser.add_argument("--preview-only", action="store_true",
                        help="Use `flags: ['preview']` - FMG validates but does not push to device")
    parser.add_argument("--poll-interval-sec", type=float, default=3)
    parser.add_argument("--max-wait-sec", type=int, default=300)
    parser.add_argument("--dev-rev-comments", default=None)
    args = parser.parse_args()

    call_params: Dict[str, Any] = {
        "fmg_host": args.fmg_host, "adom": args.adom, "device": args.device,
        "vdom": args.vdom, "preview_only": args.preview_only,
        "poll_interval_sec": args.poll_interval_sec,
        "max_wait_sec": args.max_wait_sec,
    }
    if args.dev_rev_comments:
        call_params["dev_rev_comments"] = args.dev_rev_comments

    out = asyncio.run(execute(call_params))
    print(json.dumps(out, indent=2, default=str))
    sys.exit(0 if out.get("success") else 1)
