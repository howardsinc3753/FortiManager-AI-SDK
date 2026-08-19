# Pull Request

## What this changes

<!-- One or two sentences. Link to the issue if there is one. -->

Fixes #

## Type of change

- [ ] New tool
- [ ] New playbook
- [ ] Bug fix in existing tool / SDK client
- [ ] Documentation only
- [ ] Refactor with no partner-visible behavior change

## Contract checklist (required for new / changed tools)

- [ ] `python scripts/validate_tool.py tools/<dir>` passes for every new or changed tool
- [ ] Smoke-tested against a live FMG — output pasted below
- [ ] `Skills.md` has 3+ example prompts, 1 real JSON example, 3+ error rows
- [ ] `manifest.yaml` follows [CONTRACT.md](../CONTRACT.md) — no new top-level keys, no new pip deps
- [ ] `status: draft` in manifest (Trust Anchor flips to `certified` at signing time)
- [ ] No hardcoded IPs, credentials, tokens, or customer identifiers
- [ ] Directory name, Python file name, and `canonical_id` all match exactly

## Smoke-test output

```json
// paste the actual JSON response from your smoke test — redact hosts / tokens
```

## Notes for reviewers

<!-- Anything a reviewer should know: FMG version differences, endpoint quirks,
     admin profile requirements, dependent objects, breaking changes. -->
