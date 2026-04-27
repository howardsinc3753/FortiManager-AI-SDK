#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager Export CSV

Fetch any FMG list URL and write rows as CSV.

Author: Ulysses Project
Version: 1.0.0
"""

import asyncio
import csv
import io
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)


def _flatten_value(v: Any) -> str:
    """Flatten complex values for CSV cells."""
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ";".join(str(x) for x in v)
    if isinstance(v, dict):
        return ";".join(f"{k}={x}" for k, x in v.items())
    return str(v)


def _rows_to_csv(rows: List[Dict[str, Any]], columns: List[str]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for r in rows:
        writer.writerow([_flatten_value(r.get(c)) for c in columns])
    return buf.getvalue()


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    url = params.get("url")
    if not url:
        return {"success": False, "error": "Missing required parameter: url"}

    fields = params.get("fields")
    filter_ = params.get("filter")
    range_ = params.get("range")
    verbose = params.get("verbose")
    output_path = params.get("output_path")
    max_rows = int(params.get("max_rows", 10000))
    preview_rows = int(params.get("preview_rows", 5))

    try:
        client = FortiManagerClient(host=fmg_host)
        if client.auth_method == "session" and not client.session:
            client.login()

        # Build request — use raw shape to support fields/filter/range/verbose
        req_params: Dict[str, Any] = {"url": url}
        if fields is not None:
            req_params["fields"] = list(fields)
        if filter_ is not None:
            req_params["filter"] = filter_
        eff_range = list(range_) if range_ else [0, max_rows]
        req_params["range"] = eff_range

        payload: Dict[str, Any] = {
            "id": client._next_id(),
            "method": "get",
            "params": [req_params],
        }
        if client.session:
            payload["session"] = client.session
        if verbose is not None:
            payload["verbose"] = int(verbose)

        resp = client._request(payload)
        result = resp.get("result", [{}])[0]
        status = result.get("status") or {}
        if status.get("code") != 0:
            return {"success": False, "url": url, "error": f"FMG {status}"}

        data = result.get("data") or []
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return {"success": False, "url": url,
                    "error": f"URL did not return a list — got {type(data).__name__}"}

        rows: List[Dict[str, Any]] = [r for r in data if isinstance(r, dict)]
        if not rows:
            return {"success": True, "url": url, "row_count": 0,
                    "columns": [], "csv_preview": "(no rows)"}

        # Determine columns
        if fields:
            columns = list(fields)
        else:
            # Union of keys across rows, but stable order from first row
            first_keys = list(rows[0].keys())
            extra = sorted({k for r in rows for k in r.keys()} - set(first_keys))
            columns = first_keys + extra

        full_csv = _rows_to_csv(rows, columns)

        out: Dict[str, Any] = {
            "success": True,
            "url": url,
            "row_count": len(rows),
            "columns": columns,
        }

        if output_path:
            p = Path(output_path).expanduser().resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(full_csv, encoding="utf-8")
            out["output_path"] = str(p)
            out["bytes_written"] = p.stat().st_size

        # Always include preview (cheap)
        preview_csv = _rows_to_csv(rows[:preview_rows], columns)
        out["csv_preview"] = preview_csv

        return out

    except Exception as e:
        logger.exception("export-csv failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    raw = sys.argv[2] if len(sys.argv) > 2 else "/dvmdb/adom/root/device"
    idx = raw.find("/pm/") if "/pm/" in raw else raw.find("/dvmdb/") if "/dvmdb/" in raw else 0
    url = raw[idx:] if idx > 0 else raw
    out_path = sys.argv[3] if len(sys.argv) > 3 else None
    print(json.dumps(asyncio.run(execute({
        "fmg_host": host, "url": url,
        "fields": ["name", "ip", "platform_str", "os_ver", "mr", "patch", "conn_status", "conf_status"],
        "verbose": 1,
        "output_path": out_path,
    })), indent=2))
