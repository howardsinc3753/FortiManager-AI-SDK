# FortiManager Install Push — Skills

## How to Call

Use this tool when:
- A device has been imported (via `model-device-import-csv`) and needs its config pushed to the real device
- Building a "Point-and-Fire" MSSP deploy button (Phase 3 of the workflow)
- Running install-preview in CI to validate an ADOM's templates against a device without touching production
- Rolling out template updates across a fleet (loop over devices)

**Example prompts:**
- "Install spa-hub-vm in BOR_Customer_10"
- "Preview install on spoke-1 in BOR_Customer_1 — check for errors, don't push"
- "Deploy to all 4 dual spokes in Customer_10"

## Phase 3 of the deployment workflow

```
Phase 1: fortimanager-adom-init         → ADOM prepped
Phase 2: fortimanager-model-device-import-csv → device install-ready
Phase 3: fortimanager-install-push       ← YOU ARE HERE
              → device installed + dial-home applied
```

## What it does

Fires a single `exec /securityconsole/install/device` task with:
- `flags: ["none"]` for real install (pushes CLI templates + Policy Package to device)
- `flags: ["preview"]` for preview-only (FMG validates, generates rev, does NOT commit)

Then polls the task to terminal state. Returns structured result with per-device install log lines.

Task states: `pending → running → done / error / warning / cancelled / aborted`. Terminal states are surfaced with `num_err` count + line-by-line install log (`name`, `vdom`, `ip`, `state`, `percent`, `detail`, `err`).

**Why one endpoint?** `install/device` handles both CLI templates AND Policy Package in a single task (matches GUI Install Wizard). Preview via `flags: ["preview"]` gives fail-fast validation without a separate `/install/preview` call (which hangs on some FMG 7.6 builds).

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | Yes | — | Target ADOM |
| `device` | string | Yes | — | Device name (DVMDB) |
| `vdom` | string | No | `root` | Target vdom |
| `preview_only` | bool | No | `false` | If true, use `flags: ["preview"]` — FMG validates but does not commit to device. Safe for CI/dry-run. |
| `poll_interval_sec` | float | No | `3` | Seconds between task-state polls |
| `max_wait_sec` | int | No | `300` | Max seconds to wait for task to reach terminal state |
| `dev_rev_comments` | string | No | auto | Comment on the generated device rev |

## Interpreting Results

**Successful install:**
```json
{
  "success": true,
  "action": "installed",
  "adom": "BOR_Customer_10",
  "device": "spoke-2",
  "task_id": 128,
  "state": "done",
  "num_err": 0,
  "num_done": 2,
  "percent": 100,
  "waited_sec": 42.5,
  "lines": [
    {"name": "spoke-2[copy]", "state": "done", "detail": "Copy to device done", "err": 0},
    {"name": "spoke-2[install]", "state": "done", "detail": "install and save finished status=OK", "err": 0}
  ]
}
```

**Preview-only run** (verified against spoke-1 in BOR_Customer_1):
```json
{
  "success": true,
  "action": "preview-passed",
  "preview_only": true,
  "task_id": 128,
  "state": "done",
  "num_err": 0,
  "waited_sec": 3.18,
  "lines": [
    {"name": "spoke-1[copy]", "state": "done", "detail": "Copy to device done", "err": 0},
    {"name": "Write summary[preview]", "state": "done", "detail": "Write preview done", "err": 0}
  ]
}
```

**Install failed** (validation error):
```json
{
  "success": false,
  "action": "install-failed",
  "state": "error", "num_err": 1,
  "error": "task 129 ended in state 'error' (num_err=1): datasrc invalid. object: system sdwan..."
}
```

## Example — CLI usage

```bash
# Real install (default: preview-first + install)
python org.ulysses.noc.fortimanager-install-push.py \
    --fmg-host 184.73.7.106 \
    --adom BOR_Customer_10 \
    --device spoke-2

# Preview only (safe validation)
python org.ulysses.noc.fortimanager-install-push.py \
    --fmg-host 184.73.7.106 \
    --adom BOR_Customer_10 \
    --device spoke-2 \
    --preview-only

# Deploy all 4 dual devices (loop from your app or shell)
for dev in spoke-dual-30g spoke-dual-50g spoke-dual-vm spa-hub-dual-120g; do
    python org.ulysses.noc.fortimanager-install-push.py \
        --fmg-host 184.73.7.106 \
        --adom BOR_Customer_10 \
        --device "$dev"
done
```

## Example — from Streamlit "Point-and-Fire" app

```python
import subprocess, json

result = subprocess.run(
    [sys.executable,
     "org.ulysses.noc.fortimanager-install-push.py",
     "--fmg-host", fmg_host,
     "--adom", adom_name,
     "--device", device_name],
    capture_output=True, text=True, timeout=600,
)
outcome = json.loads(result.stdout)
if outcome["success"]:
    st.success(f"Installed {device_name} in {outcome.get('waited_sec')}s")
else:
    st.error(f"Install failed: {outcome.get('error')}")
    for ln in outcome.get("lines", []):
        st.code(f"{ln.get('name')}: {ln.get('detail')} (err={ln.get('err')})")
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `install/device exec failed: code=-6` | Wrong ADOM name | Verify with `fortimanager-adom-list` |
| `install/device exec failed: code=-3` | Device not in DVMDB or bad scope | Run `model-device-import-csv` first; check `vdom` param |
| `task ... ended in state 'error'` | Config validation or push failed | Check `lines[].detail` — often a datasrc/config error. See `docs/BOR-SASE-DEPLOYMENT-WORKFLOW.md` §5 for the 18-gotcha catalog |
| `state: 'timeout'` after 300s | Task took too long | Increase `max_wait_sec` (real 30G/50G installs can take 60-120s) |

## Pairs With

- `fortimanager-adom-init` — Phase 1, provisions the ADOM before this tool can run
- `fortimanager-model-device-import-csv` — Phase 2, imports the device before this tool can install it
- `fortimanager-template-clone-from-device` — optional Phase 4, clones runtime config to NOC-friendly templates AFTER install lands

## Reference

- Full workflow: `docs/BOR-SASE-DEPLOYMENT-WORKFLOW.md`
- Gotcha catalog with symptom → cause → fix: §5 of workflow doc
- FMG install endpoints: `/securityconsole/install/preview` and `/securityconsole/install/device`
