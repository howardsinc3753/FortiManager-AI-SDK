# FortiManager AI SDK

> **AI-ready FortiManager JSON-RPC SDK** — Trust-Anchor-certified MCP tool framework for MSSP partners. Fork the namespace, feed prompts to Claude Code / Cursor, ship tools that pass validation on the first try.

Python SDK plus a 28-tool MCP collection covering discovery, authoring, change, execute, and monitor operations against FortiManager 7.6. Built for MSSP partners who operate managed FortiGate fleets through AI agents.

**License:** Apache 2.0 — see [LICENSE](LICENSE).

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/howardsinc3753/FortiManager-AI-SDK.git
cd FortiManager-AI-SDK

# 2. Install deps (stdlib + pyyaml only)
pip install pyyaml

# 3. Drop credentials
mkdir -p ~/.config/mcp
cat > ~/.config/mcp/fortimanager_credentials.yaml <<'EOF'
devices:
  fmg-lab:
    host: fmg.example.com
    username: admin
    password: <your-password>
    # or use an API token:
    # api_key: <your-fmg-api-token>
EOF

# 4. Run your first tool
python tools/org.ulysses.noc.fortimanager-adom-list/org.ulysses.noc.fortimanager-adom-list.py fmg.example.com
```

Expected output: `{"success": true, "adoms": [...]}`

Full walkthrough: **[QUICKSTART.md](QUICKSTART.md)**.

---

## What's inside

| Path | What it is |
|---|---|
| [`sdk/`](sdk/) | Shared FortiManager JSON-RPC client (`fortimanager_client.py`). All tools import this — do not reinvent HTTP or session management. |
| [`tools/`](tools/) | 28 certified MCP tools, one directory per canonical ID. Each has `manifest.yaml` + `<name>.py` + `Skills.md`. |
| [`playbooks/`](playbooks/) | Executable multi-step workflows composed of tools (SD-WAN spoke onboarding, health checks, tenant onboarding). |
| [`docs/`](docs/) | FortiManager JSON-RPC endpoint reference. |
| [`API_reference/`](API_reference/) | Drop raw FMG Swagger/OpenAPI exports here for tool authors to consult. |
| [`scripts/`](scripts/) | Scaffolder (`new_tool.py`) and validator (`validate_tool.py`). |
| [`templates/`](templates/) | Tool boilerplate the scaffolder copies from. |

---

## Tool inventory (28 tools)

Canonical prefix: `org.ulysses.noc.fortimanager-*` (fork this to your org via [NAMESPACE-FORK.md](NAMESPACE-FORK.md))

### 🟢 Discovery — 11 tools
Read-only enumeration and audit.

| Tool | Purpose |
|---|---|
| `adom-list` | Enumerate ADOMs |
| `device-list` | List managed FortiGates in an ADOM (conn/conf status, HA, platform) |
| `policy-package-list` | List policy packages |
| `policy-list` | List firewall policies in a package |
| `firewall-address-list` | List firewall address objects |
| `object-list` | Generic object read with optional `expand_datasrc` for readable names |
| `object-count` | Count any object type in an ADOM |
| `object-schema` | Schema introspection for any object type |
| `field-datasrc` | Discover valid values for policy fields (srcaddr, service, etc.) |
| `metadata-get-device` | Read effective per-device metadata values |
| `export-csv` | Export any object listing to CSV (devices, policies, addresses, services, ADOMs, metadata) |

### 🟡 Configure / Author — 9 tools
Create and modify objects and templates.

| Tool | Purpose |
|---|---|
| `firewall-address-create` | Create firewall address (subnet / iprange / fqdn) |
| `object-create` | Generic object create for any FMG object type |
| `object-update` | Edit any object |
| `object-delete` | Delete any object (idempotent mode supported) |
| `object-member-update` | Atomically add / remove / clear group members |
| `policy-create` | Create firewall policy |
| `script-create` | Author CLI script library entries |
| `metadata-create` | Define MSSP variable templates (LAN_SUBNET, HOSTNAME, BGP_LOOPBACK, …) |
| `metadata-set-device` | Override per-device variable values |
| `model-device-create` | Create a model device (hardware or VM) for ZTP staging |

### 🔴 Execute — 3 tools
Push to live devices.

| Tool | Purpose |
|---|---|
| `policy-package-install` | Install a policy package to live FortiGates |
| `device-settings-install` | Push device-scope settings (DNS, SNMP, interfaces) |
| `script-run` | Run a CLI script against live devices (exec + poll + log) |

### 🔵 Monitor — 4 tools
Live and historical operational state.

| Tool | Purpose |
|---|---|
| `device-monitor-proxy` | Live FortiGate state via FMG broker — interfaces, sessions, CPU, routes, BGP, IPsec (no per-device creds) |
| `sdwan-history` | Historical SD-WAN metrics (latency / jitter / packet loss) |
| `object-checksum` | Change-detection via object hash |
| `task-status` | Poll any long-running FMG task |

### 🟠 Remediate — 1 tool

| Tool | Purpose |
|---|---|
| `object-delete` (see Configure above) | Also usable for cleanup / remediation flows |

---

## Playbooks

Executable, step-by-step workflows in [`playbooks/`](playbooks/):

| Playbook | Outcome |
|---|---|
| [`sdwan-health-check.md`](playbooks/sdwan-health-check.md) | Live + historical SD-WAN health snapshot |
| [`sdwan-config-audit.md`](playbooks/sdwan-config-audit.md) | Read-only SD-WAN config grade against MSSP best practices |
| [`sdwan-spoke-onboard.md`](playbooks/sdwan-spoke-onboard.md) | Build SD-WAN config on a spoke from scratch with dry-run + rollback |
| [`tenant-sdwan-onboarding.md`](playbooks/tenant-sdwan-onboarding.md) | FMG-native MSSP tenant onboarding: ADOM + SDWAN Template + model devices + BGP-on-Lo + install staging |

Full capability map with outcomes-to-tools mapping: **[CAPABILITIES.md](CAPABILITIES.md)**.

---

## Documentation map

| For… | Read |
|---|---|
| Getting started fast | [QUICKSTART.md](QUICKSTART.md) |
| Understanding what the SDK can do | [CAPABILITIES.md](CAPABILITIES.md) — outcome-oriented capability index |
| Forking to your org namespace | [NAMESPACE-FORK.md](NAMESPACE-FORK.md) |
| Feeding prompts to your AI (Claude Code / Cursor / Copilot) | [PARTNER-PROMPTS.md](PARTNER-PROMPTS.md) |
| Building a new tool | [AUTHORING-GUIDE.md](AUTHORING-GUIDE.md) |
| The formal, machine-checkable tool contract | [CONTRACT.md](CONTRACT.md) |
| AI-assistant entry point | [CLAUDE.md](CLAUDE.md) |
| FMG JSON-RPC endpoint reference | [docs/FNDN-API-Reference.md](docs/FNDN-API-Reference.md) |
| Contributing back | [CONTRIBUTING.md](CONTRIBUTING.md) |

---

## Prerequisites

- **Python 3.11+**
- **`pyyaml`** (only pip dependency)
- **FortiManager 7.6** with a service account that has JSON-RPC access to the ADOMs you want to operate on
- **Credentials file** at `~/.config/mcp/fortimanager_credentials.yaml` (see Quickstart)

Optional:
- **Trust Anchor** — for signed, certified tool execution. Tools work standalone without it; Trust Anchor adds provenance / signing / policy enforcement.

---

## Design principles

- **One tool = one logical FMG operation.** Composition happens in playbooks, not inside tools.
- **Shared client only.** Every tool imports `sdk/fortimanager_client.py`. No parallel HTTP libraries. No hidden dependencies.
- **Standard envelope.** Success = `{"success": true, ...}`. Failure = `{"success": false, "error": "..."}`. No exceptions escape `execute()`.
- **Machine-validated contract.** Every tool passes `python scripts/validate_tool.py <dir>` before commit. See [CONTRACT.md](CONTRACT.md).
- **Fork-first.** Partners rename `org.ulysses.*` to their own namespace via [NAMESPACE-FORK.md](NAMESPACE-FORK.md) — no upstream branch pollution.

---

## Support

- **Issues:** file at [github.com/howardsinc3753/FortiManager-AI-SDK/issues](https://github.com/howardsinc3753/FortiManager-AI-SDK/issues)
- **Contact:** Daniel Howard, Fortinet Systems Engineer

---

## License

Apache License 2.0 — see [LICENSE](LICENSE). Not affiliated with or endorsed by Fortinet, Inc. "FortiManager" and "FortiGate" are trademarks of Fortinet, Inc.
