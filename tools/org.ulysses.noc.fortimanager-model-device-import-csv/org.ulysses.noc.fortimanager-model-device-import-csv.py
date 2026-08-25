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

v1.1.0 auto-bind (opt-in via `auto_bind`):
  After a successful import, the tool can automatically attach the new devices
  to the ADOM's tenant-scale infrastructure:
    1. CLI Template Group `scope member` — appends each new {name, vdom}
    2. Policy Package `scope member`     — appends each new {name, vdom}
    3. Device Group (DVMDB) `object member` — set membership (FMG 7.6.7 API
       accepts but has no readback path; verify in GUI)
    4. Normalized Interface `dynamic_mapping` — one entry per new device per
       named interface, `{_scope: [{name, vdom}], local-intf: [<intf>]}`

  All four are opt-in. If `resolve_from_blueprint=True` and template_group /
  policy_package are omitted, they are inferred from the first row's blueprint
  (`cliprofs[0]` and `pkg`).

  The scope-member appends use GET-extend-UPDATE semantics — FMG's `update`
  on `scope member` REPLACES the whole list, so we merge with existing before
  writing back. Duplicate {name, vdom} pairs are skipped.

v1.2.0 install-readiness fixes:
  Two install-blocking issues found on the first spoke-2 dry run — both
  fixed here so future imports come out install-ready:

  A. Hostname stays as SN. FMG's `add-dev-list` sets `hostname = sn` by
     default (only refreshed at first install-time from the device's
     `config system global`). Fix: right after the per-row DVM verify, we
     `update /dvmdb/adom/{adom}/device/{name}` with `{name, hostname: name}`
     so the FMG display + policy header show the friendly hostname.
     Toggleable via `set_hostname_from_name` (default true).

  B. Normalized-interface dynamic_mapping returned -10131 `datasrc invalid.
     object: system zone`. Root cause: FMG validates the `local-intf` value
     against the device-DB `system zone` table. Fresh model devices have no
     zones yet (they'd be created by BOR-04-ZONE-LAN CLI template at
     install), so validation fails BEFORE install runs and blocks the whole
     Policy Package copy. Fix: BEFORE adding the dynamic_mapping, `set
     /pm/config/device/{dev}/vdom/{vdom}/system/zone/{zone}` to create an
     empty zone shell on the device DB. Now dynamic_mapping validates,
     install starts, CLI template later populates the zone with real
     interface members. Idempotent.

Author: Ulysses Project
Version: 1.2.0
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


def _status(resp: Dict[str, Any]) -> Dict[str, Any]:
    return (resp.get("result", [{}])[0] or {}).get("status") or {}


def _member_key(m: Dict[str, str]) -> tuple[str, str]:
    return (m.get("name") or "", m.get("vdom") or "root")


def _append_scope_member(
    client: FortiManagerClient,
    named_url: str,
    new_entries: List[Dict[str, str]],
    field: str = "scope member",
) -> Dict[str, Any]:
    """GET-extend-UPDATE pattern for FMG scope member fields.

    Reads current scope member, merges with new_entries (deduped by (name,vdom)),
    writes back with `update`. Returns {before, added, after, code, msg}.
    """
    try:
        g = client.get(named_url, fields=["name", field])
        d = (g.get("result", [{}])[0] or {}).get("data") or {}
        existing = list(d.get(field) or [])
        existing_keys = {_member_key(m) for m in existing}

        added: List[Dict[str, str]] = []
        merged = list(existing)
        for m in new_entries:
            if _member_key(m) not in existing_keys:
                merged.append({"name": m["name"], "vdom": m.get("vdom", "root")})
                added.append(m)

        if not added:
            return {"code": 0, "msg": "nothing to add",
                    "before": len(existing), "added": 0, "after": len(existing)}

        # Send only the object identifier + the field we're changing.
        obj_name = d.get("name") or named_url.rsplit("/", 1)[-1]
        r = client.call("update", named_url, data={"name": obj_name, field: merged})
        st = _status(r)
        return {
            "code": st.get("code"),
            "msg": (st.get("message") or "")[:120],
            "before": len(existing),
            "added": len(added),
            "after": len(merged) if st.get("code") == 0 else len(existing),
            "added_members": added,
        }
    except Exception as e:
        return {"code": -1, "msg": f"{type(e).__name__}: {e}",
                "before": None, "added": 0, "after": None}


def _ensure_device_zone_shell(
    client: FortiManagerClient,
    dev_name: str,
    vdom: str,
    zone_name: str,
) -> Dict[str, Any]:
    """Create an EMPTY system zone shell on the device DB.

    v1.2.0 chicken-and-egg fix: FMG validates dynamic_mapping.local-intf
    against the device-side `system zone` table. Fresh model devices have
    no zones. Creating an empty shell (interface=[]) here lets the
    validation pass. CLI templates fill in the real interface members at
    install time. Idempotent (set = create-or-update)."""
    url = f"/pm/config/device/{dev_name}/vdom/{vdom}/system/zone/{zone_name}"
    try:
        r = client.call("set", url, data={"name": zone_name})
        st = _status(r)
        return {"code": st.get("code"), "msg": (st.get("message") or "")[:80]}
    except Exception as e:
        return {"code": -1, "msg": f"{type(e).__name__}: {e}"}


def _add_dynamic_mapping(
    client: FortiManagerClient,
    adom: str,
    intf: str,
    dev_name: str,
    vdom: str,
    local_intf: str,
    pre_create_zone_shell: bool = True,
) -> Dict[str, Any]:
    """POST a new dynamic_mapping entry to a normalized interface for one device.

    v1.2.0: If `pre_create_zone_shell=True` (default), we `set` an empty
    system zone with the local_intf's name on the device DB FIRST so that
    FMG's -10131 `datasrc invalid. object: system zone` validation passes.
    CLI template `BOR-04-ZONE-LAN` populates the zone's interface members
    at install time.

    If `pre_create_zone_shell=False` (legacy), skip the shell step; the
    add will succeed only if the zone already exists device-side (e.g. the
    device has been installed at least once).
    """
    shell_result = None
    if pre_create_zone_shell:
        shell_result = _ensure_device_zone_shell(client, dev_name, vdom, local_intf)
        # If shell create failed, still try the mapping — maybe zone existed
        # already from a prior install and we just don't have write access.

    url = f"/pm/config/adom/{adom}/obj/dynamic/interface/{intf}/dynamic_mapping"
    data = {"_scope": [{"name": dev_name, "vdom": vdom}], "local-intf": [local_intf]}
    try:
        r = client.call("add", url, data=data)
        st = _status(r)
        code = st.get("code")
        msg = (st.get("message") or "")[:160]
        result: Dict[str, Any] = {
            "device": dev_name, "vdom": vdom, "code": code, "msg": msg,
        }
        if pre_create_zone_shell and shell_result is not None:
            result["zone_shell"] = shell_result
        # -10131 should be rare now (we pre-created the zone). If it still
        # hits, mark deferred and hint the user to check zone-shell result.
        if code == -10131:
            result["status"] = "deferred"
            result["hint"] = (
                "Zone shell create may have failed OR device-side validation "
                "still blocks. Check `zone_shell` result and manually create "
                f"the zone via `set /pm/config/device/{dev_name}/vdom/{vdom}"
                f"/system/zone/{local_intf}`."
            )
        else:
            result["status"] = "ok" if code == 0 else "failed"
        return result
    except Exception as e:
        return {"device": dev_name, "vdom": vdom, "code": -1,
                "msg": f"{type(e).__name__}: {e}", "status": "failed",
                **({"zone_shell": shell_result} if shell_result else {})}


def _set_device_hostname(
    client: FortiManagerClient,
    adom: str,
    dev_name: str,
    hostname: str,
) -> Dict[str, Any]:
    """v1.2.0: update `/dvmdb/adom/{adom}/device/{name}` with {name, hostname}.
    FMG's add-dev-list defaults hostname=sn until the first install
    refreshes from device's real `config system global`. This makes the
    FMG display + policy headers show the friendly name immediately."""
    try:
        r = client.call(
            "update",
            f"/dvmdb/adom/{adom}/device/{dev_name}",
            data={"name": dev_name, "hostname": hostname},
        )
        st = _status(r)
        return {"code": st.get("code"), "msg": (st.get("message") or "")[:80]}
    except Exception as e:
        return {"code": -1, "msg": f"{type(e).__name__}: {e}"}


def _resolve_bindings_from_blueprint(
    client: FortiManagerClient,
    adom: str,
    blueprint_name: str,
) -> Dict[str, Optional[str]]:
    """Look up cliprofs[0] + pkg from a blueprint. Returns {template_group, policy_package}."""
    try:
        r = client.get(f"/pm/config/adom/{adom}/obj/fmg/device/blueprint/{blueprint_name}",
                       fields=["cliprofs", "pkg"])
        d = (r.get("result", [{}])[0] or {}).get("data") or {}
        cliprofs = d.get("cliprofs") or []
        return {
            "template_group": (cliprofs[0] if cliprofs else None),
            "policy_package": d.get("pkg"),
        }
    except Exception:
        return {"template_group": None, "policy_package": None}


def _do_auto_bind(
    client: FortiManagerClient,
    adom: str,
    created: List[Dict[str, Any]],
    auto_bind: Dict[str, Any],
    pre_create_zone_shells: bool = True,
) -> Dict[str, Any]:
    """Run the opt-in post-import bindings. `created` is the successful import list."""
    out: Dict[str, Any] = {}
    if not created:
        return out

    resolve = bool(auto_bind.get("resolve_from_blueprint", False))
    tpl_group = auto_bind.get("template_group")
    pkg = auto_bind.get("policy_package")
    dev_group = auto_bind.get("device_group")
    ni_specs = auto_bind.get("normalized_interfaces") or []

    # Blueprint auto-resolve for template_group + policy_package if not set
    if resolve and (not tpl_group or not pkg):
        first_bp = created[0].get("blueprint")
        if first_bp:
            resolved = _resolve_bindings_from_blueprint(client, adom, first_bp)
            if not tpl_group:
                tpl_group = resolved.get("template_group")
            if not pkg:
                pkg = resolved.get("policy_package")
            out["resolved_from_blueprint"] = {
                "blueprint": first_bp,
                "template_group": resolved.get("template_group"),
                "policy_package": resolved.get("policy_package"),
            }

    new_entries = [{"name": c["name"], "vdom": "root"} for c in created]

    # 1. CLI Template Group scope member
    if tpl_group:
        out["template_group"] = {
            "group": tpl_group,
            **_append_scope_member(
                client,
                f"/pm/config/adom/{adom}/obj/cli/template-group/{tpl_group}",
                new_entries,
            ),
        }

    # 2. Policy Package scope member
    if pkg:
        out["policy_package"] = {
            "package": pkg,
            **_append_scope_member(
                client,
                f"/pm/pkg/adom/{adom}/{pkg}",
                new_entries,
            ),
        }

    # 3. DVMDB Device Group object member (FMG 7.6.7: code=0 but no API readback)
    if dev_group:
        try:
            # set replaces; use existing + new
            g = client.get(f"/dvmdb/adom/{adom}/group/{dev_group}", fields=["name"])
            g_st = _status(g)
            if g_st.get("code") != 0:
                out["device_group"] = {
                    "group": dev_group,
                    "code": g_st.get("code"),
                    "msg": f"group not found: {g_st.get('message')}",
                }
            else:
                # DVMDB group has no readback for members, so we can only
                # add-what's-in-created (we don't know existing membership).
                r = client.call(
                    "add",
                    f"/dvmdb/adom/{adom}/group/{dev_group}/object member",
                    data=new_entries,
                )
                st = _status(r)
                out["device_group"] = {
                    "group": dev_group,
                    "code": st.get("code"),
                    "msg": (st.get("message") or "")[:120],
                    "members_submitted": new_entries,
                    "verified_via_api": False,  # FMG 7.6.7 quirk
                    "verify_hint": (
                        f"FMG GUI: Device Manager -> {adom} -> Device Groups -> {dev_group}"
                    ),
                }
        except Exception as e:
            out["device_group"] = {
                "group": dev_group, "code": -1, "msg": f"{type(e).__name__}: {e}",
            }

    # 4. Normalized interface dynamic_mapping (per interface, per new device)
    if ni_specs:
        ni_out = []
        for spec in ni_specs:
            if isinstance(spec, str):
                intf_name, local_intf = spec, spec
            elif isinstance(spec, dict):
                intf_name = spec.get("name") or ""
                local_intf = spec.get("local_intf") or intf_name
            else:
                continue
            if not intf_name:
                continue
            per_dev = []
            for entry in new_entries:
                per_dev.append(_add_dynamic_mapping(
                    client, adom, intf_name, entry["name"], entry["vdom"], local_intf,
                    pre_create_zone_shell=pre_create_zone_shells,
                ))
            ni_out.append({
                "interface": intf_name,
                "local_intf": local_intf,
                "results": per_dev,
            })
        out["normalized_interfaces"] = ni_out

    return out


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
    # v1.1.0: auto-bind (opt-in). None = disabled entirely.
    auto_bind: Dict[str, Any] = params.get("auto_bind") or {}
    # v1.2.0: install-readiness fixes (both on by default)
    set_hostname_from_name = bool(params.get("set_hostname_from_name", True))
    pre_create_zone_shells = bool(params.get("pre_create_zone_shells", True))

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
            # v1.2.0: set hostname to name so FMG display + policy header don't
            # show the raw SN until the first install refreshes it.
            if record["in_dvm"] and set_hostname_from_name:
                record["hostname_fix"] = _set_device_hostname(
                    client, adom, entry["name"], entry["name"],
                )
            if record["in_dvm"]:
                created.append(record)
            else:
                failed.append(record)

        overall_ok = (len(failed) == 0) and (task_state == "done")
        action = "imported" if overall_ok else ("partial" if created else "failed")

        # v1.1.0: auto-bind — opt-in via auto_bind dict.
        # Only run when the import succeeded (partial/failed = skip; user should
        # re-run after fixing the import errors).
        bind_out: Dict[str, Any] = {}
        if auto_bind and created and action != "failed":
            # v1.2.0: pass pre_create_zone_shells through to _do_auto_bind so
            # normalized-interface binds create zone shells device-side first.
            bind_out = _do_auto_bind(
                client, adom, created, auto_bind,
                pre_create_zone_shells=pre_create_zone_shells,
            )

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
            **({"auto_bind": bind_out} if bind_out else {}),
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
