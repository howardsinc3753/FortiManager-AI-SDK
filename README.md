# FortiManager AI SDK

Python SDK + MCP tool collection for FortiManager 7.6, built for MSSP partners to operate managed FortiGate fleets through AI agents.

## Structure

```
FortiManager-AI-SDK/
├── sdk/                    # Shared JSON-RPC client (fortimanager_client.py)
├── API_reference/          # FMG Swagger/OpenAPI JSON (drop exports here)
├── docs/                   # Markdown guides per workflow
└── tools/                  # Certified MCP tools, one dir per canonical ID
    └── org.ulysses.noc.fortimanager-*/
        ├── manifest.yaml
        ├── org.ulysses.noc.fortimanager-*.py
        └── Skills.md
```

## v1 Tool Set (5 core)

| Canonical ID | Purpose |
|---|---|
| `org.ulysses.noc.fortimanager-adom-list/1.0.0` | Enumerate ADOMs |
| `org.ulysses.noc.fortimanager-device-list/1.0.0` | List managed FortiGates in an ADOM |
| `org.ulysses.noc.fortimanager-policy-package-list/1.0.0` | List policy packages |
| `org.ulysses.noc.fortimanager-policy-list/1.0.0` | List firewall policies in a package |
| `org.ulysses.noc.fortimanager-script-run/1.0.0` | Run CLI script against managed device |

## Credentials

All tools look up credentials from:
```
~/.config/mcp/fortimanager_credentials.yaml
```

Format:
```yaml
devices:
  fmg-lab:
    host: 192.168.209.X
    username: admin
    password: <secret>
```
