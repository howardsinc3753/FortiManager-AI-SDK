# Contributing to FortiManager AI SDK

Thanks for wanting to contribute. This project ships partner-facing tools that MSSPs run against live FortiManager infrastructure — the bar for what lands in `main` is "would you run this in production tomorrow?"

## What kinds of contributions are welcome

- **New tools** that wrap a distinct FortiManager JSON-RPC operation
- **New playbooks** that compose existing tools into a repeatable outcome
- **FMG endpoint additions** to [`docs/FNDN-API-Reference.md`](docs/FNDN-API-Reference.md)
- **Fixes** to bugs, doc errors, or contract violations in existing tools
- **CLAUDE.md / CAPABILITIES.md / PARTNER-PROMPTS.md** improvements that make AI agents produce better output on the first try

## What is NOT welcome (please don't)

- Tools that don't pass `python scripts/validate_tool.py`
- Tools that bundle multiple FMG operations into one (composition belongs in playbooks)
- New pip dependencies beyond `pyyaml` (see [CONTRACT.md §2.2](CONTRACT.md))
- Tools that hardcode credentials, tokens, IPs, or customer identifiers
- Vendor-locked code specific to a single customer's environment
- Renaming the reference tool `org.ulysses.noc.fortimanager-adom-list` — it's the untouchable spec reference

## Contribution workflow

### 1. Fork and branch

```bash
git checkout -b feat/short-descriptive-name
```

Branch naming convention:
- `feat/<name>` — new tool or playbook
- `fix/<name>` — bug or contract-violation fix
- `docs/<name>` — documentation-only changes
- `refactor/<name>` — internal cleanup with no partner-visible change

### 2. Build following the contract

**For a new tool:** follow [AUTHORING-GUIDE.md](AUTHORING-GUIDE.md) step-by-step. Every tool has exactly three files:

```
tools/org.<your-org>.<domain>.fortimanager-<subject>-<action>/
├── manifest.yaml
├── org.<your-org>.<domain>.fortimanager-<subject>-<action>.py
└── Skills.md
```

**For a new playbook:** follow the shape of `playbooks/sdwan-health-check.md` — objective, tools used, step-by-step with expected JSON, error handling, and a worked example.

### 3. Validate

Every tool MUST pass the validator before commit:

```bash
python scripts/validate_tool.py tools/<your-tool-dir>
```

Exit code 0 = pass. Non-zero = fix and retry. **Do not open a PR with failing validation.**

### 4. Smoke-test

Run the tool against a live FMG (your lab, not customer infra) and verify it returns `"success": true` with the expected data shape:

```bash
python tools/<your-tool-dir>/<name>.py fmg.example.com
```

Paste the actual output JSON into your tool's `Skills.md` under "Output Structure". Don't invent example output.

### 5. Commit

Use terse, imperative commit messages:

```
Add fortimanager-firewall-vip-list

Read-only enumeration of VIP objects in an ADOM. Follows the same shape
as firewall-address-list. Passes validator, smoke-tested against 7.6.
```

### 6. Open a PR

Fill in the PR template. Required checkboxes:
- [ ] `python scripts/validate_tool.py` passes on all new/changed tools
- [ ] Smoke-tested against a live FMG (paste output JSON)
- [ ] Skills.md has 3+ example prompts, 1 real JSON example, 3+ error rows
- [ ] No new pip dependencies
- [ ] No hardcoded IPs, credentials, tokens, or customer names
- [ ] `status: draft` in manifest (Trust Anchor flips it to `certified`)

## Code style

- **Python 3.11+**, stdlib preferred over anything
- **Async where the SDK is async**, sync elsewhere — don't mix
- **Type hints** on function signatures
- **No global state**, no module-level side effects
- **One-liner comments only** — the WHY, not the WHAT. Long docstrings are noise.
- **Match the reference tool's shape.** When in doubt: `diff` against `tools/org.ulysses.noc.fortimanager-adom-list/`.

## Namespace rules

If you're contributing back a general-purpose tool: keep the `org.ulysses.*` namespace so it lands as a reference example.

If you're contributing a tool that only makes sense in your organization: don't upstream it — keep it in your fork under `org.<your-org>.*`. Upstream `main` stays generic.

## Reporting bugs

Open an [issue](https://github.com/howardsinc3753/FortiManager-AI-SDK/issues) with:
1. **What tool** (canonical ID + version)
2. **What you ran** (exact command)
3. **What you got** (full JSON output — redact credentials)
4. **What you expected**
5. **FortiManager version** and **Python version**

## Reporting security issues

Do NOT open a public issue for security vulnerabilities. Email the maintainer directly — see [README.md § Support](README.md#support).

## License

By contributing, you agree that your contributions are licensed under the Apache License 2.0 that covers this project. See [LICENSE](LICENSE).
