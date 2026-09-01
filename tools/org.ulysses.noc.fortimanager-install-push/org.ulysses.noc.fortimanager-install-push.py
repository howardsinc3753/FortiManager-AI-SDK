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
                        # history[] carries the actual root cause when detail
                        # is the useless "Aborted due to previous error"
                        "history": [
                            {"percent": int(h.get("percent") or 0),
                             "detail": (h.get("detail") or "")[:400]}
                            for h in (ln.get("history") or [])
                        ],
                    }
                    for ln in (data.get("line") or [])
                ],
            }
        await asyncio.sleep(poll_interval)


def _discover_pkgs_for_device(client: FortiManagerClient, adom: str,
                              device: str, vdom: str) -> List[str]:
    """Return names of policy packages where {device, vdom} is a scope member.
    Empty list if none - device would only get device-scope install."""
    r = client.get(f"/pm/pkg/adom/{adom}", option=["scope member"])
    pkgs = r.get("result", [{}])[0].get("data") or []
    hits = []
    for p in pkgs:
        for m in (p.get("scope member") or []):
            if m.get("name") == device and (m.get("vdom") or "root") == vdom:
                hits.append(p.get("name"))
                break
    return hits


async def _run_task(client: FortiManagerClient, url: str, body: Dict[str, Any],
                    poll_interval: float, max_wait: int, label: str) -> Dict[str, Any]:
    """Fire an install exec, poll its task, return {label, task_id, state,
    num_err, num_done, percent, waited_sec, timed_out, lines[], error?}."""
    out: Dict[str, Any] = {"label": label}
    resp = client.exec(url, data=body)
    r0 = resp.get("result", [{}])[0]
    st = r0.get("status") or {}
    if st.get("code") != 0:
        out["error"] = f"{label} exec failed: code={st.get('code')} msg={(st.get('message') or '')[:200]}"
        return out
    tid = (r0.get("data") or {}).get("task")
    if tid is None:
        out["error"] = f"{label} returned no task ID"
        return out
    out["task_id"] = int(tid)
    tr = await _poll(client, int(tid), poll_interval, max_wait)
    out.update(tr)
    return out


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
    skip_pkg = bool(params.get("skip_pkg", False))
    pkg_override = params.get("pkg")     # explicit pkg(s) to install; skips auto-discovery
    poll_interval = float(params.get("poll_interval_sec", 3))
    max_wait = int(params.get("max_wait_sec", 300))
    dev_rev_comments = params.get(
        "dev_rev_comments",
        f"install-push via FortiManager AI SDK (preview_only={preview_only})",
    )

    # Support single device (str) or list of devices for scope
    if isinstance(device, list):
        scope = [{"name": d, "vdom": vdom} for d in device]
        primary_device = device[0]
    else:
        scope = [{"name": device, "vdom": vdom}]
        primary_device = device

    flags = ["preview"] if preview_only else ["none"]

    result: Dict[str, Any] = {
        "success": False, "adom": adom, "device": device, "vdom": vdom,
        "preview_only": preview_only, "device_task": None, "pkg_tasks": [],
    }

    try:
        client = FortiManagerClient(host=fmg_host)
    except Exception as e:
        result["error"] = f"Client init failed: {type(e).__name__}: {e}"
        return result

    # ---- STEP 1: install/device (CLI templates -> device DB) ----
    try:
        step1 = await _run_task(
            client, "/securityconsole/install/device",
            {"adom": adom, "scope": scope, "flags": flags,
             "dev_rev_comments": dev_rev_comments},
            poll_interval, max_wait, "install/device",
        )
        result["device_task"] = step1
    except Exception as e:
        logger.exception("install/device raised")
        result["error"] = f"install/device raised: {type(e).__name__}: {e}"
        return result

    # ---- STEP 1 verdict — abort pkg install on failure ----
    if step1.get("error"):
        result["action"] = "install-failed"
        result["error"] = step1["error"]
        return result
    d_state = step1.get("state")
    d_err = step1.get("num_err", 0)
    if d_state not in ("done", "warning") or d_err > 0:
        result["action"] = "preview-failed" if preview_only else "install-failed"
        # Surface real root cause from history if detail is uninformative
        for ln in step1.get("lines") or []:
            for h in (ln.get("history") or []):
                dt = (h.get("detail") or "").lower()
                if "fail" in dt or "error" in dt or "invalid" in dt or "undefined" in dt:
                    result["error"] = (f"install/device task {step1.get('task_id')} "
                                       f"failed: {h.get('detail')[:300]}")
                    return result
        # Fallback to the top-level line detail
        for ln in step1.get("lines") or []:
            if ln.get("err") or "error" in (ln.get("detail") or "").lower() \
                    or "abort" in (ln.get("detail") or "").lower():
                result["error"] = (f"install/device task {step1.get('task_id')} "
                                   f"failed: {ln.get('detail')[:300]}")
                return result
        result["error"] = (f"install/device task {step1.get('task_id')} "
                           f"ended in state '{d_state}', num_err={d_err}")
        return result

    # ---- STEP 2: install/package (Policy Package -> device DB) ----
    if skip_pkg:
        pkgs_to_install = []
    elif pkg_override:
        pkgs_to_install = [pkg_override] if isinstance(pkg_override, str) else list(pkg_override)
    else:
        try:
            pkgs_to_install = _discover_pkgs_for_device(client, adom, primary_device, vdom)
        except Exception as e:
            logger.exception("pkg discovery failed")
            result["pkg_discovery_error"] = f"{type(e).__name__}: {e}"
            pkgs_to_install = []
    result["pkgs_to_install"] = pkgs_to_install

    for pkg_name in pkgs_to_install:
        try:
            step2 = await _run_task(
                client, "/securityconsole/install/package",
                {"adom": adom, "pkg": pkg_name, "scope": scope, "flags": flags,
                 "adom_rev_name": dev_rev_comments},
                poll_interval, max_wait, f"install/package[{pkg_name}]",
            )
        except Exception as e:
            logger.exception("install/package raised")
            step2 = {"label": f"install/package[{pkg_name}]",
                     "error": f"{type(e).__name__}: {e}"}
        result["pkg_tasks"].append(step2)
        if step2.get("error") or step2.get("state") not in ("done", "warning") \
                or step2.get("num_err", 0) > 0:
            result["action"] = "pkg-install-failed"
            # Try to surface real root cause from history
            for ln in step2.get("lines") or []:
                for h in (ln.get("history") or []):
                    dt = (h.get("detail") or "").lower()
                    if "fail" in dt or "error" in dt or "invalid" in dt:
                        result["error"] = (f"install/package[{pkg_name}] task "
                                           f"{step2.get('task_id')} failed: {h.get('detail')[:300]}")
                        return result
            result["error"] = (step2.get("error")
                               or f"install/package[{pkg_name}] ended in state "
                                  f"'{step2.get('state')}', num_err={step2.get('num_err', 0)}")
            return result

    # ---- ALL STEPS PASSED ----
    result["success"] = True
    if preview_only:
        result["action"] = "preview-passed"
    elif not pkgs_to_install:
        result["action"] = "installed-device-only"   # no pkg assigned - device-scope only
    else:
        result["action"] = "installed"
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
    parser.add_argument("--pkg", default=None,
                        help="Explicit policy package to install (skip auto-discovery)")
    parser.add_argument("--skip-pkg", action="store_true",
                        help="Skip Step 2 (install/package) - device-scope install only")
    parser.add_argument("--poll-interval-sec", type=float, default=3)
    parser.add_argument("--max-wait-sec", type=int, default=300)
    parser.add_argument("--dev-rev-comments", default=None)
    args = parser.parse_args()

    call_params: Dict[str, Any] = {
        "fmg_host": args.fmg_host, "adom": args.adom, "device": args.device,
        "vdom": args.vdom, "preview_only": args.preview_only,
        "skip_pkg": args.skip_pkg,
        "poll_interval_sec": args.poll_interval_sec,
        "max_wait_sec": args.max_wait_sec,
    }
    if args.pkg:
        call_params["pkg"] = args.pkg
    if args.dev_rev_comments:
        call_params["dev_rev_comments"] = args.dev_rev_comments

    out = asyncio.run(execute(call_params))
    print(json.dumps(out, indent=2, default=str))
    sys.exit(0 if out.get("success") else 1)
