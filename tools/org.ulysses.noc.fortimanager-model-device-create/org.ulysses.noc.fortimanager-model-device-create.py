#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Model Device Create (v2.0.0)

Comprehensive model device creation via exec /dvm/cmd/add/device (FMG 7.6.7
daemon API — singular, not the older /dev-list endpoint). Attaches CLI
template groups, policy packages, auth templates, and pre-populates
per-device metadata variables in one API call using the inline
"device blueprint" object.

Ref:
  Swagger: FortiManager 7.6.7 Daemon Modules → Device Manager Command dvm_cmd_add
  GUI curl (observed): /dvm/cmd/add/device with data.device.device blueprint = {...}

Author: Ulysses Project
Version: 2.0.0
"""

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)

# Enum maps — swagger uses strings, FMG 7.6.7 daemon accepts either but int is
# what the GUI actually sends. Map friendly strings to ints for wire consistency.
_OS_TYPE_STR_TO_INT = {
    "unknown": -1, "fos": 0, "fsw": 1, "foc": 2, "fml": 3,
    "faz": 4, "fwb": 5, "fch": 6, "fct": 7, "log": 8,
    "fmg": 9, "fsa": 10, "fdd": 11, "fac": 12, "fpx": 13, "fna": 14,
}
_MGMT_MODE_STR_TO_INT = {"unreg": 0, "faz": 1, "fmgfaz": 2, "fmg": 3}
_OS_VER_STR_TO_INT = {  # "7.0" → 7, etc.
    "unknown": -1, "0.0": 0, "1.0": 1, "2.0": 2, "3.0": 3, "4.0": 4,
    "5.0": 5, "6.0": 6, "7.0": 7, "8.0": 8,
}

# Task state map (from FMG /task/task/{id} response)
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


def _to_int(value: Any, mapping: Dict[str, int], default: int) -> int:
    """Accept int or friendly string, map to int."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in mapping:
            return mapping[low]
        # Numeric string
        try:
            return int(low)
        except ValueError:
            pass
    return default


def _build_blueprint(
    platform: str,
    blueprint_param: Optional[Union[str, Dict[str, Any]]],
    templates: Optional[list],
    pkg: Optional[str],
    auth_template: Optional[str],
    enforce_device_config: int,
    sdwan_management: int,
) -> Dict[str, Any]:
    """Assemble the inline device-blueprint dict.

    - If blueprint_param is a dict, use it as the base and layer shortcuts on top.
    - If it's a string, treat it as a legacy devprof name reference (stored in
      the blueprint as `prerun-cliprof` for backward compat).
    - Else start from defaults.
    """
    # Defaults matching what the FMG GUI sends (observed via curl)
    bp: Dict[str, Any] = {
        "platform": platform,
        "port-provisioning": 1,
        "vm-log-disk": 0,
        "linked-to-model": False,
        "prefer-img-ver": None,
        "download_from_fgd": False,
        "enforce-device-config": enforce_device_config,
        "sdwan-management": sdwan_management,
        "folder": "/",
        "auth-template": None,
        "prerun-cliprof": None,
        "pkg": None,
        "cluster-worker": [],
        "templates": [],
    }
    if isinstance(blueprint_param, dict):
        bp.update(blueprint_param)
        # Ensure platform is set even if the caller's dict omitted it
        bp.setdefault("platform", platform)
    elif isinstance(blueprint_param, str):
        bp["prerun-cliprof"] = blueprint_param

    # Apply shortcut params — these win over any dict-supplied values
    if templates:
        bp["templates"] = list(templates)
    if pkg is not None:
        bp["pkg"] = pkg
    if auth_template is not None:
        bp["auth-template"] = auth_template

    return bp


async def _poll_task(client: FortiManagerClient, task_id: int, max_wait: int) -> tuple[str, int, str]:
    start = time.monotonic()
    state = "pending"
    num_err = 0
    last_line = ""
    while time.monotonic() - start < max_wait:
        r = client.get(f"/task/task/{task_id}", verbose=1)
        data = r.get("result", [{}])[0].get("data") or {}
        state = _norm_state(data.get("state"))
        num_err = int(data.get("num_err") or 0)
        # Try to grab a helpful line from history
        history = data.get("history") or []
        if history:
            last_line = str(history[-1].get("detail") or "")[:200]
        if state in _TERMINAL:
            return state, num_err, last_line
        await asyncio.sleep(2)
    return state, num_err, last_line


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    # Required params
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

    # Enums — accept string or int
    os_type = _to_int(params.get("os_type", "fos"), _OS_TYPE_STR_TO_INT, 0)
    os_ver = _to_int(params.get("os_ver", 7), _OS_VER_STR_TO_INT, 7)
    mgmt_mode = _to_int(params.get("mgmt_mode", "fmg"), _MGMT_MODE_STR_TO_INT, 3)
    mr = int(params.get("mr", 6))
    patch = int(params.get("patch", 0))

    # Version int (per GUI: os_ver*100 + mr*10 + patch, e.g. 7.6 → 760, 7.0 → 700)
    version = os_ver * 100 + mr * 10 + patch
    if version == 700 and mr == 0 and patch == 0:
        # Some FMG builds want the "version" field literally as int like 700 or 760
        version = os_ver * 100

    # Blueprint assembly
    blueprint = _build_blueprint(
        platform=platform,
        blueprint_param=params.get("blueprint"),
        templates=params.get("templates"),
        pkg=params.get("pkg"),
        auth_template=params.get("auth_template"),
        enforce_device_config=int(params.get("enforce_device_config", 0)),
        sdwan_management=int(params.get("sdwan_management", 0)),
    )

    # Device object
    device: Dict[str, Any] = {
        "name": name,
        "sn": sn,
        "adm_usr": params.get("adm_usr", "admin"),
        "os_type": os_type,
        "os_ver": os_ver,
        "version": version,
        "mr": mr,
        "mgmt_mode": mgmt_mode,
        "flags": 262176,  # observed GUI default — enable model + FGFM path
        "faz.perm": int(params.get("faz_perm", 15)),
        "faz.quota": int(params.get("faz_quota", 0)),
        "device blueprint": blueprint,
        "meta variables": params.get("meta_variables") or {},
    }
    if params.get("adm_pass"):
        device["adm_pass"] = [params["adm_pass"]]
    if params.get("description"):
        device["desc"] = params["description"]
    if params.get("meta_fields"):
        device["meta fields"] = params["meta_fields"]

    # Top-level data body
    data_body: Dict[str, Any] = {
        "adom": adom,
        "flags": ["create_task", "nonblocking"],
        "device": device,
    }
    if params.get("groups"):
        data_body["groups"] = [{"name": g} for g in params["groups"]]

    payload_snapshot = {
        "url": "/dvm/cmd/add/device",
        "method": "exec",
        "data": data_body,
    }

    # Dry-run bail-out
    if params.get("dry_run"):
        return {
            "success": True,
            "action": "dry-run",
            "name": name,
            "adom": adom,
            "payload_sent": payload_snapshot,
        }

    wait = bool(params.get("wait", True))
    max_wait = int(params.get("max_wait_sec", 60))

    try:
        client = FortiManagerClient(host=fmg_host)
        if client.auth_method == "session" and not client.session:
            client.login()

        # Existence check — bail early with clean error if device already there
        probe0 = client.get(f"/dvmdb/adom/{adom}/device/{name}", fields=["name", "oid", "sn"])
        probe0_status = probe0.get("result", [{}])[0].get("status") or {}
        if probe0_status.get("code") == 0:
            existing = probe0.get("result", [{}])[0].get("data") or {}
            return {
                "success": False,
                "action": "already-exists",
                "name": name,
                "adom": adom,
                "device_oid": existing.get("oid"),
                "error": f"Device {name!r} already exists in ADOM {adom!r} (oid={existing.get('oid')}, sn={existing.get('sn')})",
            }

        # Fire the exec
        rpc = {
            "id": client._next_id(),
            "method": "exec",
            "params": [{"url": "/dvm/cmd/add/device", "data": data_body}],
        }
        if client.session:
            rpc["session"] = client.session

        resp = client._request(rpc)
        result = resp.get("result", [{}])[0]
        status = result.get("status") or {}
        if status.get("code") != 0:
            return {
                "success": False,
                "name": name,
                "adom": adom,
                "error": f"FMG exec error: {status}",
                "payload_sent": payload_snapshot,
            }

        # Extract task id (swagger: resp.data.taskid is an array)
        data_out = result.get("data") or {}
        task_val = data_out.get("taskid") or data_out.get("task") or data_out.get("pid")
        task_id: Optional[int] = None
        if isinstance(task_val, list) and task_val:
            try:
                task_id = int(task_val[0])
            except (ValueError, TypeError):
                task_id = None
        elif task_val is not None:
            try:
                task_id = int(task_val)
            except (ValueError, TypeError):
                task_id = None

        out: Dict[str, Any] = {
            "success": True,
            "action": "created",
            "name": name,
            "adom": adom,
            "task_id": task_id,
            "state": "pending",
            "device_oid": None,
        }

        if wait and task_id is not None:
            final_state, num_err, last_line = await _poll_task(client, task_id, max_wait)
            out["state"] = final_state
            out["success"] = final_state == "done" and num_err == 0
            if not out["success"] and last_line:
                out["error"] = f"Task ended {final_state} (errs={num_err}): {last_line}"

        # Verify device landed in DVM
        probe = client.get(f"/dvmdb/adom/{adom}/device/{name}", fields=["name", "oid", "sn", "platform_str", "flags"])
        probe_status = probe.get("result", [{}])[0].get("status") or {}
        if probe_status.get("code") == 0:
            d = probe.get("result", [{}])[0].get("data") or {}
            out["device_oid"] = d.get("oid")
            out["platform_str_effective"] = d.get("platform_str")
        else:
            if out.get("success"):
                out["success"] = False
                out["error"] = "Device not in DVM after create — task may have failed silently"

        return out

    except Exception as e:
        logger.exception("model-device-create failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}", "payload_sent": payload_snapshot}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "fmg.example.com"
    # Smoke test — matches the GUI curl payload for FortiGate-50G on BOR_Customer_1
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host,
        "adom": "BOR_Customer_1",
        "name": "sdk-bor-50g-test-01",
        "sn": "FGT50GTK26048289",
        "platform": "FortiGate-50G",
        "description": "SDK v2 smoke: FGT-50G model device with templates attached",
        "templates": ["sdk-cli-grp-test"],   # attach the CLI template group built earlier
        # "pkg": "default",                  # uncomment when a policy package exists
        "enforce_device_config": 0,
        "sdwan_management": 0,
    })), indent=2))
