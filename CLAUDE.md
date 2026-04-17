# FortiManager AI SDK — AI Assistant Entry Point

**If you are an AI assistant (Claude Code, Copilot, Cursor, etc.) working in this repo, you MUST read this file first.** Your output must conform to the contract below. Deviation = rejection.

## The Contract In One Screen

This SDK produces **Trust-Anchor-certified MCP tools** that wrap the FortiManager JSON-RPC API. Every tool you author follows the same shape:

```
tools/org.{ORG}.{domain}.fortimanager-{subject}-{action}/
├── manifest.yaml                                           # Trust-Anchor spec
├── org.{ORG}.{domain}.fortimanager-{subject}-{action}.py  # Python, entry_point = main(context)
└── Skills.md                                               # AI guidance for downstream agents
```

Three files. Same names. Always.

## Hard Rules (Non-Negotiable)

1. **Use the shared client.** All FMG access goes through `sdk/fortimanager_client.py` → `FortiManagerClient`. Do NOT reinvent login, session management, or HTTP. Do NOT add a new requests dependency.
2. **Credentials from YAML only.** Load via `FortiManagerClient(host=...)`, which reads `~/.config/mcp/fortimanager_credentials.yaml`. Never hardcode tokens. Never log them.
3. **Return the standard envelope.**
   - Success: `{"success": true, ...tool-specific keys...}`
   - Failure: `{"success": false, "error": "<human-readable>"}`
4. **Directory name == canonical_id prefix.** If the directory is `org.acme.noc.fortimanager-device-list`, the Python file is `org.acme.noc.fortimanager-device-list.py` and the `manifest.yaml` declares `canonical_id: org.acme.noc.fortimanager-device-list/1.0.0`.
5. **No `mkey` CRUD.** Read-only discovery tools go to `intent: discover`, mutating tools go to `intent: configure|remediate|execute` and MUST bump `max_execution_time_ms` appropriately. Mutating tools MUST support a dry-run/validate mode when the FMG endpoint allows it.
6. **Pass `python scripts/validate_tool.py tools/<your-dir>` before claiming done.** No exceptions.

## Read Order

If you are building a new tool, read these files, in this order:

1. `CONTRACT.md` — the formal spec (manifest fields, Python template, Skills.md template)
2. `docs/FNDN-API-Reference.md` — the FortiManager JSON-RPC endpoint map
3. `AUTHORING-GUIDE.md` — step-by-step walkthrough with commentary
4. `tools/org.ulysses.noc.fortimanager-adom-list/` — the reference implementation. Imitate this.
5. `PARTNER-PROMPTS.md` — prompt patterns for repeatable, high-quality generation

If you are onboarding a partner org (e.g. renaming `ulysses` → `acme`):

1. `NAMESPACE-FORK.md`

## The Reference Tool

**Every tool in this repo must be indistinguishable in shape from `tools/org.ulysses.noc.fortimanager-adom-list/`.** When in doubt, diff against it.

## What "Done" Means

A tool is done when ALL of these hold:

- [ ] Directory + file names match canonical_id
- [ ] `python scripts/validate_tool.py tools/<dir>` passes
- [ ] CLI smoke test runs: `python tools/<dir>/<name>.py <fmg-host>` returns `"success": true`
- [ ] Skills.md has: Purpose, When to Use (with 3+ example prompts), Parameters table, Output Structure, Example, Error Handling
- [ ] `status: draft` in manifest (Trust-Anchor certification flips this to `certified` after signing)

## What You Do NOT Do

- Don't invent new top-level manifest keys.
- Don't add `requests`, `httpx`, `pydantic` as dependencies. Use stdlib + the shared client.
- Don't write tools that combine multiple endpoints. One tool = one logical FMG operation. Multi-step workflows go in **runbooks** (see `RUNBOOKS.md` when it exists).
- Don't silently swallow errors. If FMG returns `status.code != 0`, surface it.
- Don't write long docstrings or multi-paragraph comments. One-liner WHY only if non-obvious.

## How to Ask For Help

If the contract is ambiguous for your case, stop and ask the human. Do not guess and ship.
