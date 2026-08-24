#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Model Device Import CSV

Bulk-create model devices from a local CSV file, mirroring the FMG 7.6 GUI's
"Add Model Devices from CSV" flow. The GUI parses the CSV client-side and
fires exec /dvm/cmd/add/dev-list with the parsed rows — this tool does the
same server-side wrap.

CSV Format (per FMG doc + GUI observed):
    Required columns: "Serial Number", "Device Blueprint", "Name"
    Optional HA cols: "Cluster Id", "Cluster Name", "Priority", "HA Mode"  (Phase 2)
    Extra columns  : any metadata variable name -> per-row value

Observed GUI payload (single row):
    exec /dvm/cmd/add/dev-list
    data:
      adom: <adom>
      flags: [create_task, nonblocking]
      add-dev-list:
        - name: <Name>
          sn: <Serial Number>
          device blueprint: <Device Blueprint>   (STRING ref to named blueprint)
          meta variables: {<extra col>: <value>, ...}
          device action: add_model
          mgmt_mode: 3
          os_type: 0, os_ver: 7, mr: 6
          _platform: <derived from blueprint.platform>
          groups: []
          faz.perm: 15
          faz.quota: 0

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import csv
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

# CSV columns handled explicitly; anything else becomes a meta variable
_REQUIRED_COLS = {"Serial Number", "Device Blueprint", "Name"}
_HA_COLS = {"Cluster Id", "Cluster Name", "Priority", "HA Mode"}

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


def _parse_csv(csv_path: str) -> tuple[List[Dict[str, str]], List[str]]:
    """Return (rows, meta_col_names). Each row is a dict of column->value."""
    p = Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    with open(p, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = [{k: (v or "").strip() for k, v in r.items()} for r in reader]
    missing = _REQUIRED_COLS - set(headers)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}. Found: {headers}")
    meta_cols = [h for h in headers if h not in _REQUIRED_COLS and h not in _HA_COLS]
    return rows, meta_cols


def _resolve_blueprint_platform(client: FortiManagerClient, adom: str, blueprint_name: str, cache: Dict[str, str]) -> Optional[str]:
    """Look up a blueprint's platform from FMG (cached)."""
    if blueprint_name in cache:
        return cache[blueprint_name]
    r = client.get(f"/pm/config/adom/{adom}/obj/fmg/device/blueprint/{blueprint_name}", fields=["name", "platform"])
    d = r.get("result", [{}])[0].get("data") or {}
    plat = d.get("platform")
    cache[blueprint_name] = plat
    return plat


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
        history = data.get("history") or []
        if history:
            last_line = str(history[-1].get("detail") or "")[:200]
        if state in _TERMINAL:
            return state, num_err, last_line
        await asyncio.sleep(2)
    return state, num_err, last_line


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    for req in ("adom", "csv_path"):
        if not params.get(req):
            return {"success": False, "error": f"Missing required parameter: {req}"}

    adom = params["adom"]
    csv_path = params["csv_path"]

    try:
        rows, meta_cols = _parse_csv(csv_path)
    except Exception as e:
        return {"success": False, "error": f"CSV parse failed: {e}", "csv_path": csv_path}

    if not rows:
        return {"success": False, "error": "CSV has no data rows", "csv_path": csv_path}

    default_platform = params.get("default_platform")
    default_os_type = int(params.get("default_os_type", 0))
    default_os_ver = int(params.get("default_os_ver", 7))
    default_mr = int(params.get("default_mr", 6))
    default_mgmt_mode = int(params.get("default_mgmt_mode", 3))
    default_adm_usr = params.get("default_adm_usr", "admin")
    default_adm_pass = params.get("default_adm_pass", "") or ""
    default_description = params.get("default_description", "Model device (CSV import)")
    faz_perm = int(params.get("faz_perm", 15))
    faz_quota = int(params.get("faz_quota", 0))
    resolve_bp = bool(params.get("resolve_blueprint_platform", True))
    wait = bool(params.get("wait", True))
    max_wait = int(params.get("max_wait_sec", 120))
    dry_run = bool(params.get("dry_run", False))

    # Client + blueprint platform cache
    client = None if dry_run else FortiManagerClient(host=fmg_host)
    plat_cache: Dict[str, str] = {}

    add_dev_list: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        name = row.get("Name") or ""
        sn = row.get("Serial Number") or ""
        blueprint = row.get("Device Blueprint") or ""
        if not (name and sn and blueprint):
            return {
                "success": False,
                "error": f"Row {idx}: missing required value (Name={name!r}, Serial={sn!r}, Blueprint={blueprint!r})",
                "csv_path": csv_path, "rows_parsed": len(rows),
            }
        # Meta variables from extra columns (skip blanks)
        meta_vars = {c: row[c] for c in meta_cols if row.get(c)}

        # Platform resolution: prefer blueprint's platform if requested, else default
        platform = default_platform
        if resolve_bp and client is not None:
            plat = _resolve_blueprint_platform(client, adom, blueprint, plat_cache)
            if plat:
                platform = plat

        entry: Dict[str, Any] = {
            "name": name,
            "sn": sn,
            "device blueprint": blueprint,
            "device action": "add_model",
            "adm_usr": default_adm_usr,
            "adm_pass": default_adm_pass,
            "desc": default_description,
            "mgmt_mode": default_mgmt_mode,
            "os_type": default_os_type,
            "os_ver": default_os_ver,
            "mr": default_mr,
            "groups": [],
            "faz.perm": faz_perm,
            "faz.quota": faz_quota,
            "meta variables": meta_vars,
        }
        if platform:
            entry["_platform"] = platform
        add_dev_list.append(entry)

    data_body: Dict[str, Any] = {
        "adom": adom,
        "flags": ["create_task", "nonblocking"],
        "add-dev-list": add_dev_list,
    }
    payload_snapshot = {"url": "/dvm/cmd/add/dev-list", "method": "exec", "data": data_body}

    if dry_run:
        return {
            "success": True,
            "action": "dry-run",
            "adom": adom,
            "csv_path": csv_path,
            "rows_parsed": len(rows),
            "payload_sent": payload_snapshot,
        }

    try:
        # Fire the bulk exec
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
                "success": False,
                "action": "failed",
                "adom": adom,
                "csv_path": csv_path,
                "rows_parsed": len(rows),
                "error": f"FMG exec error: {status}",
                "payload_sent": payload_snapshot,
            }

        data_out = result.get("data") or {}
        task_val = data_out.get("taskid") or data_out.get("task")
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

        task_state = "pending"
        task_err = ""
        if wait and task_id is not None:
            task_state, num_err, last_line = await _poll_task(client, task_id, max_wait)
            if num_err and last_line:
                task_err = f"errs={num_err}: {last_line}"

        # Per-row verification: probe each device in DVM
        created: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        for entry in add_dev_list:
            probe = client.get(f"/dvmdb/adom/{adom}/device/{entry['name']}", fields=["name", "oid", "sn"])
            probe_status = probe.get("result", [{}])[0].get("status") or {}
            probe_data = probe.get("result", [{}])[0].get("data") or {}
            record = {
                "name": entry["name"],
                "sn": entry["sn"],
                "blueprint": entry["device blueprint"],
                "oid": probe_data.get("oid"),
                "in_dvm": probe_status.get("code") == 0,
            }
            if record["in_dvm"]:
                created.append(record)
            else:
                failed.append(record)

        overall_ok = (len(failed) == 0) and (task_state == "done")
        action = "imported" if overall_ok else ("partial" if created else "failed")

        return {
            "success": overall_ok,
            "action": action,
            "adom": adom,
            "csv_path": csv_path,
            "rows_parsed": len(rows),
            "task_id": task_id,
            "task_state": task_state,
            "devices_created": created,
            "devices_failed": failed,
            **({"error": task_err} if task_err else {}),
        }

    except Exception as e:
        logger.exception("model-device-import-csv failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}", "payload_sent": payload_snapshot}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "fmg.example.com"
    csv_path = sys.argv[2] if len(sys.argv) > 2 else "C:/temp/sdk-import-smoke.csv"
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host,
        "adom": "BOR_Customer_1",
        "csv_path": csv_path,
        "default_platform": "FortiGate-50G",
        "resolve_blueprint_platform": True,
        "dry_run": False,
    })), indent=2))
