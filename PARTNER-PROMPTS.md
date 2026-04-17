# Partner Prompts — Feed These to Your AI

Copy-paste prompts for Claude Code / Cursor / Copilot. Each one produces a contract-compliant tool on the first try.

## Prompt 1 — Onboarding

```
You are onboarding into the FortiManager AI SDK for my org "{ORG}".

Step 1: Read these files, in order:
  - CLAUDE.md
  - CONTRACT.md
  - AUTHORING-GUIDE.md
  - docs/FNDN-API-Reference.md
  - tools/org.ulysses.noc.fortimanager-adom-list/ (the reference implementation)

Step 2: Confirm you understand the contract by answering in <100 words:
  - What are the 3 files every tool has?
  - What is the shared SDK module you MUST use for FMG calls?
  - What does a success response look like? A failure response?
  - What command validates a tool?

Do NOT write any code yet.
```

## Prompt 2 — Build a new listing tool

```
Build a new tool for my org "{ORG}" that lists firewall addresses in an ADOM.

Endpoint: GET /pm/config/adom/{adom}/obj/firewall/address
Tool name: org.{ORG}.noc.fortimanager-firewall-address-list

Procedure:
  1. Run: python scripts/new_tool.py org.{ORG}.noc.fortimanager-firewall-address-list
  2. Edit manifest.yaml:
     - description (what it does + why)
     - intent: discover
     - tags: [fortimanager, firewall, address, object, list]
     - parameters: add optional `name_like` (substring filter), `type_filter` (0|1|2 for subnet/iprange/fqdn)
     - output_schema: addresses array with {name, type, subnet, fqdn, uuid}
  3. Implement execute() using FortiManagerClient. Use `fields=[...]` to limit payload.
  4. Fill Skills.md — 3+ example prompts, real JSON output from smoke test, 3 error rows.
  5. Smoke test: python tools/.../*.py 192.168.215.17
  6. Validate: python scripts/validate_tool.py tools/org.{ORG}.noc.fortimanager-firewall-address-list
  7. Report pass/fail. If fail, fix and re-validate. Do not claim done until it passes.

Do NOT invent new manifest keys. Do NOT import requests/httpx/pydantic. Do NOT write prose comments.
```

## Prompt 3 — Build a mutating tool

```
Build a mutating tool for my org "{ORG}" that creates a firewall address object.

Endpoint: add /pm/config/adom/{adom}/obj/firewall/address
Tool name: org.{ORG}.noc.fortimanager-firewall-address-create

Extra rules (on top of Prompt 2):
  - intent: configure
  - capabilities.max_execution_time_ms: 60000
  - Add a dry_run parameter (default false). When true, GET-check the ADOM and
    return {success: true, would_create: {...}} without adding.
  - Validate params before the RPC call: name, type (subnet|iprange|fqdn), and
    the matching value (subnet: cidr, iprange: start/end, fqdn: string).
  - On FMG error code -22 (already exists), return a clean error mentioning it.

Follow Prompt 2's procedure for everything else.
```

## Prompt 4 — Build a task-polling tool (script run, install, etc.)

```
Build an exec-with-poll tool for my org "{ORG}": run a CLI script against a managed device.

Endpoints:
  exec /dvmdb/script/execute  → returns taskid
  get  /task/task/{taskid}     → poll until state == 'done' or 'error'

Tool name: org.{ORG}.noc.fortimanager-script-run

Extra rules:
  - intent: execute
  - capabilities.max_execution_time_ms: 180000
  - Parameters: script_name (required), adom (default root), target_device (required),
    poll_interval_sec (default 2), max_wait_sec (default 120)
  - Poll loop respects max_wait_sec; return partial result with status=timeout if exceeded
  - Return taskid in the response so callers can re-poll if needed

Follow Prompt 2's procedure for everything else.
```

## Prompt 5 — Bulk onboarding (10 tools at once)

```
I need to build these 10 listing tools following the SDK contract. For each one,
run scripts/new_tool.py, edit all 3 files, smoke-test, and validate. Report a
table of pass/fail at the end.

  1. org.{ORG}.noc.fortimanager-device-list              GET /dvmdb/adom/{adom}/device
  2. org.{ORG}.noc.fortimanager-policy-package-list      GET /pm/pkg/adom/{adom}
  3. org.{ORG}.noc.fortimanager-policy-list              GET /pm/config/adom/{adom}/pkg/{pkg}/firewall/policy
  4. org.{ORG}.noc.fortimanager-firewall-address-list    GET /pm/config/adom/{adom}/obj/firewall/address
  5. org.{ORG}.noc.fortimanager-firewall-service-list    GET /pm/config/adom/{adom}/obj/firewall/service/custom
  6. org.{ORG}.noc.fortimanager-firewall-vip-list        GET /pm/config/adom/{adom}/obj/firewall/vip
  7. org.{ORG}.noc.fortimanager-script-list              GET /dvmdb/adom/{adom}/script
  8. org.{ORG}.noc.fortimanager-device-group-list        GET /dvmdb/adom/{adom}/group
  9. org.{ORG}.noc.fortimanager-adom-revision-list       GET /dvmdb/adom/{adom}/revision
 10. org.{ORG}.noc.fortimanager-workspace-status         GET /dvmdb/adom/{adom}/workspace/dirty

Use fields= on every GET. Cap all max_execution_time_ms at 15000. All intent=discover.

Do not skip smoke tests. Do not skip validation.
```

## Prompt Tips

- **Always tell the AI to STOP and read** before building. AIs that skip the read step produce garbage.
- **Always demand the validator pass** before the AI claims done. This is your automated guard.
- **If the AI adds a dependency**, reject and re-prompt with "no new pip packages — use the shared client".
- **If the AI invents a manifest key**, point at `CONTRACT.md §2` and ask it to reconcile.
- **Diff against the reference tool** — a quick `diff tools/<new>/manifest.yaml tools/org.ulysses.noc.fortimanager-adom-list/manifest.yaml` catches most drift.
