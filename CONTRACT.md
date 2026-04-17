# Tool Contract — Trust Anchor Spec

This is the **formal, machine-checkable** contract every tool in this SDK must satisfy. Validated by `scripts/validate_tool.py`. If this file and `CLAUDE.md` disagree, this file wins.

## 1. Directory Layout

```
tools/<canonical_dir>/
├── manifest.yaml
├── <canonical_dir>.py
└── Skills.md
```

Where `<canonical_dir>` matches regex:
```
^org\.[a-z0-9-]+\.[a-z][a-z-]*\.[a-z][a-z0-9-]+$
```

Examples:
- ✅ `org.ulysses.noc.fortimanager-adom-list`
- ✅ `org.acme.noc.fortimanager-policy-install`
- ❌ `org.Ulysses.NOC.FortiManagerAdomList` (uppercase)
- ❌ `org.ulysses.noc.fortimanager_adom_list` (underscores)

## 2. manifest.yaml

### Required top-level keys

| Key | Type | Constraint |
|---|---|---|
| `canonical_id` | string | `<canonical_dir>/<version>` e.g. `org.acme.noc.fortimanager-device-list/1.0.0` |
| `name` | string | Human-readable title |
| `version` | string | SemVer (`^\d+\.\d+\.\d+$`) |
| `description` | string | 20–500 chars, what + why |
| `status` | string | `draft` until Trust Anchor certifies |
| `metadata` | object | See §2.1 |
| `runtime` | object | See §2.2 |
| `parameters` | object | JSON Schema object |
| `output_schema` | object | JSON Schema object |
| `credentials` | array | Each entry `{name, type}` |
| `capabilities` | object | See §2.3 |

### §2.1 metadata

| Key | Constraint |
|---|---|
| `org_namespace` | matches org portion of canonical_id |
| `domain` | one of: `noc`, `security`, `workstation`, `cloud`, `docs`, `soc`, `ir`, `threat-intel`, `vuln-mgmt`, `edr`, `iam`, `pam`, `directory`, `server`, `aws`, `azure`, `gcp`, `kubernetes`, `database`, `platform`, `sop`, `hunt`, `teach`, `forge`, `hive` |
| `intent` | one of: `discover`, `monitor`, `audit`, `troubleshoot`, `configure`, `remediate`, `execute`, `documentation` |
| `vendor` | lowercase vendor string (e.g. `fortinet`) |
| `shelf` | `<domain>/<vendor-or-product>` (e.g. `noc/fortimanager`) |
| `tags` | array of lowercase strings, 3+ entries |

### §2.2 runtime

| Key | Value |
|---|---|
| `language` | `python` |
| `entry_point` | `main` |
| `python_packages` | array; allowed: `pyyaml` and anything already pinned in root `requirements.txt`. No `requests`, `httpx`, `pydantic`. Use stdlib. |
| `dotnet_packages` | `[]` |
| `files` | `[]` unless the tool ships data files |
| `services` | `[]` |

### §2.3 capabilities

```yaml
capabilities:
  network:
    outbound:
      - {host: "{fmg_host}", port: 443, protocol: https}
    inbound: []
  filesystem:
    read: ["~/.config/mcp/fortimanager_credentials.yaml"]
    write: []
  process:
    spawn: false
    elevated: false
  max_execution_time_ms: 15000    # discover/audit: 15k, exec: 60k, install: 300k
```

## 3. Python Source

### Required shape

```python
#!/usr/bin/env python3
from __future__ import annotations
"""
<Tool Name>

<One-sentence purpose.>

Author: <name or org>
Version: 1.0.0
"""

import asyncio, logging, sys
from pathlib import Path
from typing import Any, Dict

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

logger = logging.getLogger(__name__)


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}
    try:
        client = FortiManagerClient(host=fmg_host)
        resp = client.get("/dvmdb/adom", fields=["name"])
        result = resp.get("result", [{}])[0]
        status = result.get("status", {})
        if status.get("code") != 0:
            return {"success": False, "error": f"FMG {status}"}
        return {"success": True, "data": result.get("data") or []}
    except Exception as e:
        logger.exception("tool failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def main(context) -> Dict[str, Any]:
    params = context.parameters if hasattr(context, "parameters") else context
    return asyncio.run(execute(params))


if __name__ == "__main__":
    import json
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.215.17"
    print(json.dumps(asyncio.run(execute({"fmg_host": host})), indent=2))
```

### Rules

- `async def execute(params)` — the real logic. Must return dict matching `output_schema`.
- `def main(context)` — sync wrapper for Trust Anchor execution. Keep verbatim.
- `if __name__ == "__main__":` — CLI smoke test. Must run standalone.
- No global state. No module-level side effects.
- Imports at top. `sys.path` shim for SDK is required.

## 4. Skills.md

Required sections in this order:

```markdown
# <Tool Name> — Skills

## How to Call
Use this tool when:
- <trigger 1>
- <trigger 2>
- <trigger 3>

**Example prompts:**
- "<example 1>"
- "<example 2>"
- "<example 3>"

## Parameters
<table>

## Interpreting Results
<JSON example + field meanings>

## Example
<user prompt + tool call>

## Error Handling
<table of error → meaning → fix>
```

Minimums: 3 example prompts. 1 JSON example. 3 error entries.

## 5. Error Contract

Every caller-visible error MUST be a string in `{"success": false, "error": "<string>"}`. No raised exceptions escape `execute()`. No `None` returns. No `{"error": ..., "success": ...}` with other truthiness.

FMG endpoint errors must be surfaced — don't convert `code: -11` to "success: true, data: []".

## 6. Validation

Before commit:
```bash
python scripts/validate_tool.py tools/<canonical_dir>
```

Exit code 0 = pass. Non-zero = fix and retry.
