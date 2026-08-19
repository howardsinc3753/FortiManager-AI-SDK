# Quickstart — First Tool In 5 Minutes

This walks you from a fresh clone to your first successful FortiManager tool call.

## Prerequisites

- **Python 3.11+** (`python --version` to check)
- **FortiManager 7.6** you can reach on port 443
- **A FortiManager admin account** with JSON-RPC API access, or an **FMG API token**
- **Network path** from your workstation to the FMG (VPN / lab bridge / VPC peering — whatever)

## 1. Clone and install

```bash
git clone https://github.com/howardsinc3753/FortiManager-AI-SDK.git
cd FortiManager-AI-SDK
pip install pyyaml
```

That's the entire dependency list. Everything else is Python stdlib.

## 2. Create your credentials file

The SDK looks for credentials at **`~/.config/mcp/fortimanager_credentials.yaml`** by default.

**Password auth (simplest):**

```bash
mkdir -p ~/.config/mcp
cat > ~/.config/mcp/fortimanager_credentials.yaml <<'EOF'
devices:
  fmg-lab:
    host: fmg.example.com          # your FMG hostname or IP
    username: your-admin-user
    password: your-admin-password
EOF
chmod 600 ~/.config/mcp/fortimanager_credentials.yaml
```

**API token auth (recommended for automation):**

```yaml
devices:
  fmg-lab:
    host: fmg.example.com
    api_key: your-fmg-api-token
```

Generate an FMG API token: **FortiManager GUI → System Settings → Admin → Administrators → edit user → JSON API Access → Read/Write**, then log in as that user via CLI and run `execute api-user generate-key <username>`. Save the token that comes back.

The `host:` field maps to the value you pass as the first CLI arg to tools (or via `fmg_host` param in MCP). Multiple devices are fine — key them however you like.

## 3. Run your first tool

The `adom-list` tool is the reference implementation — smallest, simplest, no side effects. Point it at your FMG hostname:

```bash
python tools/org.ulysses.noc.fortimanager-adom-list/org.ulysses.noc.fortimanager-adom-list.py fmg.example.com
```

Expected output:

```json
{
  "success": true,
  "adoms": [
    {"name": "root", "oid": 3},
    {"name": "Global", "oid": 6}
  ]
}
```

If you see that, you're done — the SDK is working end to end.

## 4. Common first-run failures

| Symptom | Cause | Fix |
|---|---|---|
| `Missing required parameter: fmg_host` | You didn't pass the host as the CLI arg | Add the host: `python tools/…/…adom-list.py fmg.example.com` |
| `FileNotFoundError: fortimanager_credentials.yaml` | Credentials file missing or wrong path | Create the file at `~/.config/mcp/fortimanager_credentials.yaml` |
| `KeyError: 'fmg-lab'` etc. (device not found) | The `host:` value in the YAML doesn't match the arg you passed | Match them exactly — the YAML `host:` field is looked up by the value you pass |
| `FMG {'code': -11, ...}` (permission denied) | Admin profile lacks JSON-RPC read access on that endpoint | In FMG: Admin profile → JSON API Access → Read/Write on the required object families |
| `ConnectionError` / `TimeoutError` | Network / firewall block, or wrong host | Verify port 443 reachable: `curl -k https://fmg.example.com/` |
| `SSL: CERTIFICATE_VERIFY_FAILED` | FMG has a self-signed cert | The shared client already sets `verify=False` for lab certs — check you're on the current `sdk/fortimanager_client.py` |

## 5. Try a second tool

Once `adom-list` works, try one of these:

**Enumerate managed devices in an ADOM:**
```bash
python tools/org.ulysses.noc.fortimanager-device-list/org.ulysses.noc.fortimanager-device-list.py fmg.example.com
```

**Count firewall addresses in the root ADOM:**
```bash
python tools/org.ulysses.noc.fortimanager-object-count/org.ulysses.noc.fortimanager-object-count.py fmg.example.com
```

**Full capability map with outcome-to-tool mapping:** [CAPABILITIES.md](CAPABILITIES.md).

## 6. Next steps

- **Fork the namespace** to your org: [NAMESPACE-FORK.md](NAMESPACE-FORK.md) — replace `org.ulysses.*` with `org.<your-org>.*`
- **Feed prompts to your AI** to build new tools: [PARTNER-PROMPTS.md](PARTNER-PROMPTS.md)
- **Read the tool contract** before building: [CONTRACT.md](CONTRACT.md)
- **Walk a full playbook** end to end: [`playbooks/sdwan-health-check.md`](playbooks/sdwan-health-check.md) is the easiest starting point
- **Bind to an MCP host** (Claude Code, Cursor, Copilot) — each tool's `manifest.yaml` is MCP-compatible; wire it into your MCP server config or use Trust Anchor for signed execution

## Troubleshooting

Full FMG endpoint reference: [`docs/FNDN-API-Reference.md`](docs/FNDN-API-Reference.md).

If a tool fails with an FMG error code, check:
1. The endpoint exists on your FMG version (`docs/FNDN-API-Reference.md`)
2. Your admin profile's JSON API Access grants read/write on that object family
3. The ADOM you're targeting exists and your user has access to it

File issues at [github.com/howardsinc3753/FortiManager-AI-SDK/issues](https://github.com/howardsinc3753/FortiManager-AI-SDK/issues).
