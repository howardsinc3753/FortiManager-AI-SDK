# Authoring a FortiManager Tool — Step-by-Step

Use this guide when building a new tool. It walks you through the same flow the reference tool (`org.ulysses.noc.fortimanager-adom-list`) was built from.

## 0. Prerequisites

- SDK credentials in `~/.config/mcp/fortimanager_credentials.yaml`
- Python 3.11+ with `pyyaml` installed
- You have read `CLAUDE.md` and `CONTRACT.md`

## 1. Pick the endpoint

Open `docs/FNDN-API-Reference.md` and choose the JSON-RPC URL the tool will wrap. One tool = one logical FMG operation.

Examples:
| Goal | Endpoint |
|---|---|
| List devices in an ADOM | GET `/dvmdb/adom/{adom}/device` |
| List firewall addresses | GET `/pm/config/adom/{adom}/obj/firewall/address` |
| Install a policy package | exec `/securityconsole/install/package` |

## 2. Pick a canonical ID

Pattern: `org.{ORG}.{domain}.fortimanager-{subject}-{action}`

- `{ORG}`: your org namespace (e.g. `ulysses`, `acme`). Lowercase.
- `{domain}`: `noc` for network ops. `security` for security controls. `platform` for FMG self-ops.
- `{subject}-{action}`: the thing + the verb. Examples:
  - `device-list`, `device-add`
  - `policy-install`, `policy-package-list`
  - `firewall-address-list`, `firewall-address-create`
  - `script-run`, `script-list`

## 3. Scaffold

```bash
python scripts/new_tool.py org.ulysses.noc.fortimanager-firewall-address-list
```

This creates:
```
tools/org.ulysses.noc.fortimanager-firewall-address-list/
├── manifest.yaml    # pre-filled from template
├── org.ulysses.noc.fortimanager-firewall-address-list.py
└── Skills.md
```

## 4. Fill in manifest.yaml

Start with the template. Update these fields for your tool:
- `canonical_id`, `name`, `description`
- `metadata.intent` (usually `discover` for `-list`, `configure` for `-create/update`, `execute` for `-run/install`)
- `metadata.tags` — 3+ lowercase keywords
- `parameters` — JSON Schema. `fmg_host` is always required; add your tool-specific params.
- `output_schema` — match the return shape of your `execute()`
- `capabilities.max_execution_time_ms` — 15000 for reads, 60000 for writes, 300000 for installs

## 5. Implement execute()

In the Python file, replace the sample logic inside `async def execute(params)`.

Standard pattern:
```python
async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    fmg_host = params.get("fmg_host")
    if not fmg_host:
        return {"success": False, "error": "Missing required parameter: fmg_host"}

    # 1. Validate your own required params
    adom = params.get("adom", "root")

    try:
        client = FortiManagerClient(host=fmg_host)

        # 2. Make the JSON-RPC call
        resp = client.get(
            f"/pm/config/adom/{adom}/obj/firewall/address",
            fields=["name", "subnet", "type", "uuid"],
        )

        # 3. Check FMG status
        result = resp.get("result", [{}])[0]
        status = result.get("status", {})
        if status.get("code") != 0:
            return {"success": False, "error": f"FMG {status}"}

        # 4. Normalize output to match output_schema
        addresses = result.get("data") or []
        return {"success": True, "count": len(addresses), "addresses": addresses}

    except Exception as e:
        logger.exception("tool failed")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
```

### Client method cheat-sheet

```python
client.get(url, fields=[...], filter=[...], range=[0,50])
client.exec(url, data={...})    # /dvmdb/script/execute, /sys/logout, etc.
client.set(url, data={...})     # full replace
client.add(url, data={...})     # create
client.delete(url, data={...})  # remove
```

## 6. Fill in Skills.md

Replace placeholders. Critical:
- Minimum 3 example prompts in "How to Call"
- Parameters table matches manifest exactly
- Output Structure shows a real JSON example (paste one from your smoke test)
- 3+ Error Handling rows

## 7. Smoke-test

```bash
python tools/<canonical_dir>/<canonical_dir>.py 192.168.215.17
```

Expect `"success": true`. If you see `FMG {'code': -11, ...}` — the admin profile's `rpc-permit` is disabled for this resource.

## 8. Validate

```bash
python scripts/validate_tool.py tools/<canonical_dir>
```

Fix anything it flags.

## 9. Submit (Trust-Anchor pipeline)

Once validated, the Trust-Anchor publisher flow takes over:
```bash
python scripts/submit_tool.py tools/<canonical_dir>
```

(Trust-Anchor signs the tool. `status: draft` → `status: certified` in the local manifest.)

## Examples By Shape

| Shape | Reference | Endpoint pattern |
|---|---|---|
| Listing | `org.ulysses.noc.fortimanager-adom-list` | GET `/dvmdb/*` with `fields` |
| Object CRUD | (coming) `fortimanager-firewall-address-create` | add/set/delete on `/pm/config/*` |
| Install / Script | (coming) `fortimanager-script-run` | exec + poll `/task/task/{id}` |

When in doubt, diff against the reference.
