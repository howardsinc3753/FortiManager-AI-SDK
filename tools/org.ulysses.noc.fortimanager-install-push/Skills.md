# FortiManager Install Push — Skills (v1.1.0)

## How to Call

Use this tool when:
- A device has been imported (via `model-device-import-csv`) and needs its config installed to the device DB (which the box will pick up on dial-home)
- Building a "Point-and-Fire" MSSP deploy button (Phase 3 of the workflow)
- Running install-preview in CI to validate a config-build against a device without touching device DB
- Rolling out template updates across a fleet (loop over devices)

**Example prompts:**
- "Install spa-hub-vm in BOR_Customer_10"
- "Preview install on spoke-1 in BOR_Customer_1 — check for errors, don't push"
- "Deploy to all 4 dual spokes in Customer_10"

## Phase 3 of the deployment workflow

```
Phase 1: fortimanager-adom-init                → ADOM prepped
Phase 2: fortimanager-model-device-import-csv  → device install-ready
Phase 3: fortimanager-install-push             ← YOU ARE HERE
              → CLI templates AND Policy Package land in device DB
              → device picks up on next dial-home (FGFM)
```

## What it does — TWO exec calls in sequence (equivalent to GUI Install Wizard)

The FMG GUI's "Install Wizard" chains two separate operations; this tool wraps both:

```
Step 1: exec /securityconsole/install/device
        flags: ["none"]  (real install)
        flags: ["preview"] (validate + generate rev, don't commit)
        → CLI templates rendered + copied to device DB
        (interfaces, static routes, sdwan zones + members + health-checks,
         addresses, shapers, system-global settings)

Step 2: exec /securityconsole/install/package
        Runs after Step 1 succeeds. Auto-discovered: iterates
        /pm/config/adom/{adom}/pkg with option=[scope member] and installs
        every package where {device, vdom} appears as a scope member.
        → Policy Package copied to device DB
        (firewall/policy, service groups, shaping-policies)
```

**Critical history note**: v1.0.0 shipped with Step 1 only. Devices "installed successfully" but had 0 firewall policies in device DB. Fixed in v1.1.0 with the auto-discovery + Step 2. If you observe 0 policies post-install, upgrade to v1.1.0+.

Task states polled to terminal: `pending → running → done / error / warning / cancelled / aborted`. Each task returns per-device install log lines (`name, vdom, ip, state, percent, detail, err, history[]`).

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `fmg_host` | string | Yes | — | FMG hostname/IP |
| `adom` | string | Yes | — | Target ADOM |
| `device` | string OR list | Yes | — | Device name (DVMDB); list supports scope with multiple devices |
| `vdom` | string | No | `root` | Target vdom |
| `preview_only` | bool | No | `false` | `flags: ["preview"]` — validates + generates rev; does NOT commit to device DB. Safe for CI/dry-run. Same auto-discovery of pkg for step 2. |
| `pkg` | string | No | — | Override auto-discovered pkg (rare — used when you know which pkg to install and want to skip the scope-member iteration) |
| `skip_pkg` | bool | No | `false` | Skip Step 2 entirely (device-scope install only). Use when config change is CLI-template only and pkg is unchanged. |
| `poll_interval_sec` | float | No | `3` | Seconds between task-state polls |
| `max_wait_sec` | int | No | `300` | Max seconds per task (real 30G/50G installs can take 60-120s) |
| `dev_rev_comments` | string | No | auto | Comment on the generated device rev; defaults to an auto-generated tag |

## Return shape

```json
{
  "success": true,
  "action": "installed",              // preview-passed | installed | installed-device-only | install-failed | pkg-install-failed | timeout
  "adom": "BOR_Customer_10",
  "device": "spoke-2",
  "vdom": "root",
  "preview_only": false,
  "pkgs_to_install": ["BOR-SPOKE-STD-PKG"],

  "device_task": {
    "label": "install/device",
    "task_id": 141,
    "state": "done",
    "num_err": 0,
    "num_done": 1,
    "percent": 100,
    "waited_sec": 3.18,
    "timed_out": false,
    "lines": [
      {
        "name": "spoke-2[copy]",
        "vdom": "root",
        "ip": "",
        "state": "done",
        "percent": 100,
        "detail": "Copy to device done",
        "err": 0,
        "history": [
          {"percent": 1,   "detail": "Start copying shared objs to devdb"},
          {"percent": 100, "detail": "Copy to device done"}
        ]
      }
    ]
  },

  "pkg_tasks": [
    {
      "label": "install/package[BOR-SPOKE-STD-PKG]",
      "task_id": 142,
      "state": "done",
      "num_err": 0,
      "num_done": 2,
      "lines": [ /* same shape */ ]
    }
  ]
}
```

**Key field**: `line[].history[]`. Carries the REAL root cause when top-level `detail` says the useless "Aborted due to previous error." The verdict machinery walks history first when a task errors and surfaces the actual Jinja/CLI/datasrc error at the top-level `error` field.

## Interpreting Results

**Successful install:**
```json
{"success": true, "action": "installed", "pkgs_to_install": ["BOR-SPOKE-STD-PKG"],
 "device_task": {"state": "done", "num_err": 0}, "pkg_tasks": [{"state": "done", "num_err": 0}]}
```

**Successful install with warnings** (config applied, non-critical issues):
```json
{"success": true, "action": "installed-with-warnings", ...}
```

**Preview passed** (validation only — no device DB commit):
```json
{"success": true, "action": "preview-passed",
 "device_task": {"state": "done", "num_err": 0},
 "pkg_tasks": [{"state": "done", "num_err": 0}]}
```

**Install failed at step 1 (device-scope)** — step 2 not attempted:
```json
{"success": false, "action": "install-failed",
 "error": "install/device task 129 failed: [BOR-07-STATIC-ROUTES, line 45] parse cli template fail: 'MGMT_GATEWAY' is undefined",
 "device_task": {"state": "error", "num_err": 1, "lines": [...]}
}
```
Notice the error surfaces the ROOT cause from `history[]`, not just "Aborted due to previous error."

**Install failed at step 2 (pkg)** — step 1 done, pkg install failed:
```json
{"success": false, "action": "pkg-install-failed",
 "device_task": {"state": "done", "num_err": 0},
 "pkg_tasks": [{"state": "error", "num_err": 1, ...}]}
```

**No pkg found for device** (device-scope only install):
```json
{"success": true, "action": "installed-device-only", "pkgs_to_install": []}
```
Happens when device isn't a scope member of any pkg — usually indicates a config bug (Phase 2 auto-bind should have handled this).

## Example — CLI usage

```bash
# Real install (default: step 1 + auto-discovered step 2)
python org.ulysses.noc.fortimanager-install-push.py \
    --fmg-host 184.73.7.106 \
    --adom BOR_Customer_10 \
    --device spoke-2

# Preview only (no device-DB commit; step 1 + step 2 both validated)
python org.ulysses.noc.fortimanager-install-push.py \
    --fmg-host 184.73.7.106 \
    --adom BOR_Customer_10 \
    --device spoke-2 \
    --preview-only

# Device-scope only (skip pkg — config change is CLI-template-only)
python org.ulysses.noc.fortimanager-install-push.py \
    --fmg-host 184.73.7.106 \
    --adom BOR_Customer_10 \
    --device spoke-2 \
    --skip-pkg

# Deploy all 4 dual devices (loop from shell)
for dev in spoke-dual-30g spoke-dual-50g spoke-dual-vm spa-hub-dual-120g; do
    python org.ulysses.noc.fortimanager-install-push.py \
        --fmg-host 184.73.7.106 --adom BOR_Customer_10 --device "$dev"
done
```

## Example — from Streamlit "Point-and-Fire" MSSP Deploy page

```python
import subprocess, json, sys, streamlit as st

result = subprocess.run(
    [sys.executable, "org.ulysses.noc.fortimanager-install-push.py",
     "--fmg-host", fmg_host, "--adom", adom_name, "--device", device_name],
    capture_output=True, text=True, timeout=600,
)
outcome = json.loads(result.stdout)

if outcome["success"]:
    step1 = outcome["device_task"]
    step2_pkgs = ", ".join(outcome.get("pkgs_to_install") or [])
    st.success(f"Installed {device_name} in {step1.get('waited_sec')}s "
               f"(pkg: {step2_pkgs or 'none'})")
else:
    st.error(f"Install failed: {outcome.get('error')}")
    # history[] gives the actual root cause on error
    for pt in [outcome.get("device_task")] + (outcome.get("pkg_tasks") or []):
        if not pt: continue
        for ln in pt.get("lines") or []:
            for h in ln.get("history") or []:
                if h.get("err") or "fail" in (h.get("detail") or "").lower():
                    st.code(f"{pt.get('label')} → {ln.get('name')}: {h.get('detail')}")
```

## Error Handling

| Error | Meaning | Fix |
|---|---|---|
| `install/device exec failed: code=-6` | Wrong ADOM name | Verify with `fortimanager-adom-list` |
| `install/device exec failed: code=-3` | Device not in DVMDB or bad scope | Run `model-device-import-csv` first; check `vdom` param |
| `task N ended in state 'error' (num_err=1): <root-cause>` | Config validation or push failed. Root cause extracted from `line[].history[]` | Read the surfaced error; usually a Jinja `X is undefined`, `-131 datasrc invalid`, or similar. See `docs/BOR-SASE-DEPLOYMENT-WORKFLOW.md` §10 for the 22-gotcha catalog |
| `pkg-install-failed` | Step 1 succeeded, Step 2 (Policy Pkg) failed | Rare — often a policy-scope member drift; check pkg's `scope member` list against device |
| `installed-device-only` unexpected | Device isn't scope member of any pkg | Verify `model-device-import-csv` succeeded and blueprint had `port-provisioning: 1` (auto-attaches pkg scope member on device add) |
| `state: 'timeout'` after 300s | Task took too long | Increase `max_wait_sec` (real 30G/50G installs can take 60-120s) |

## Pairs With

- `fortimanager-adom-init` — Phase 1, provisions the ADOM before this tool can run
- `fortimanager-model-device-import-csv` — Phase 2, imports the device before this tool can install it
- `fortimanager-template-clone-from-device` — optional post-install, clones runtime config to NOC-friendly templates AFTER install lands

## Reference

- **Full workflow**: [`docs/BOR-SASE-DEPLOYMENT-WORKFLOW.md`](../../docs/BOR-SASE-DEPLOYMENT-WORKFLOW.md) §4 (Phase 3 detail) + §10 (22-gotcha catalog)
- **FMG install endpoints**: `/securityconsole/install/device` (step 1) + `/securityconsole/install/package` (step 2)
- **Task polling**: `/task/task/{id}` with `verbose: 1` (returns symbolic state strings vs int enums)
