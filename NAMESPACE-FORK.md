# Partner Namespace Fork — Rename `ulysses` → `{your-org}`

This SDK uses `org.ulysses.*` as the example namespace. Your organization forks the repo and replaces `ulysses` with your own org namespace. Your partner AI reads this file and performs the rename as its onboarding task.

## Choose Your Namespace

Pick a short, lowercase identifier for your organization. Rules:
- Lowercase alphanumerics + hyphens only (`^[a-z0-9-]+$`)
- 3–20 characters
- No `fortinet`, `ulysses`, or other reserved orgs
- Examples: `acme`, `contoso`, `nova-security`, `partner42`

## Rename Procedure

### 1. Search-and-replace at the directory level

```bash
# From the SDK root:
cd tools
for d in org.ulysses.*; do
  new_name="${d/ulysses/YOUR_ORG}"
  mv "$d" "$new_name"
  # rename the Python file inside
  mv "$new_name/${d}.py" "$new_name/${new_name}.py"
done
```

PowerShell equivalent:
```powershell
Get-ChildItem tools -Directory -Filter "org.ulysses.*" | ForEach-Object {
    $new = $_.Name.Replace("ulysses", "YOUR_ORG")
    Rename-Item $_.FullName (Join-Path $_.Parent.FullName $new)
    Get-ChildItem (Join-Path $_.Parent.FullName $new) -Filter "*.py" | ForEach-Object {
        Rename-Item $_.FullName ($_.Name.Replace("ulysses", "YOUR_ORG"))
    }
}
```

### 2. Update manifest files

Every `manifest.yaml`:
- `canonical_id: org.YOUR_ORG.noc.fortimanager-...`
- `metadata.org_namespace: YOUR_ORG`

Run this from the SDK root:
```bash
find tools -name manifest.yaml -exec sed -i 's/org\.ulysses\./org.YOUR_ORG./g; s/org_namespace: ulysses/org_namespace: YOUR_ORG/g' {} +
```

### 3. Update Python file imports

The SDK shim import (`from fortimanager_client import FortiManagerClient`) does NOT change. The relative path `parents[2] / "sdk"` handles the directory rename automatically.

### 4. Update README and docs

Replace `org.ulysses` references in docs/ with `org.YOUR_ORG`. The SDK's internal reference tool remains `org.ulysses.noc.fortimanager-adom-list` — do NOT rename the reference example; your AI diff-checks against it.

Actually — **keep one `org.ulysses.*` tool** as the untouchable reference. Delete the rest only after you've shipped your own versions.

### 5. Validate all tools pass

```bash
for d in tools/org.YOUR_ORG.*; do
  python scripts/validate_tool.py "$d" || echo "FAIL: $d"
done
```

### 6. Commit

```bash
git checkout -b onboard/YOUR_ORG-fork
git add -A
git commit -m "onboard: fork ulysses namespace to YOUR_ORG"
```

## AI Onboarding Prompt

Paste this into Claude Code / Cursor / Copilot to have your AI perform the rename:

```
You are onboarding into the FortiManager AI SDK for org "{YOUR_ORG}".

Read CLAUDE.md first, then CONTRACT.md and NAMESPACE-FORK.md.

Task: fork the ulysses namespace to {YOUR_ORG} following the procedure in
NAMESPACE-FORK.md. Keep exactly one untouched reference tool named
org.ulysses.noc.fortimanager-adom-list in tools/ — this stays as our spec
reference.

After the rename, run `python scripts/validate_tool.py` against every tool
and report pass/fail. Do not commit until all tools pass.
```
