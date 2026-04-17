#!/usr/bin/env python3
"""
validate_tool.py — Pre-submission linter for FortiManager AI SDK tools.

Enforces CONTRACT.md. Exit 0 on pass, non-zero on fail.

Usage:
  python scripts/validate_tool.py tools/org.<org>.<domain>.fortimanager-<name>
  python scripts/validate_tool.py --all
"""
from __future__ import annotations

import re
import sys
import ast
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


SDK_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = SDK_ROOT / "tools"

DIR_NAME_RE = re.compile(r"^org\.[a-z0-9-]+\.[a-z][a-z-]*\.[a-z][a-z0-9-]+$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

VALID_DOMAINS = {
    "noc", "security", "workstation", "cloud", "docs", "soc", "ir",
    "threat-intel", "vuln-mgmt", "edr", "iam", "pam", "directory",
    "server", "aws", "azure", "gcp", "kubernetes", "database",
    "platform", "sop", "hunt", "teach", "forge", "hive",
}
VALID_INTENTS = {
    "discover", "monitor", "audit", "troubleshoot",
    "configure", "remediate", "execute", "documentation",
}
FORBIDDEN_IMPORTS = {"requests", "httpx", "pydantic"}

SKILLS_REQUIRED_SECTIONS = [
    r"^##\s+How to Call",
    r"^##\s+Parameters",
    r"^##\s+(Interpreting Results|Output)",
    r"^##\s+Example",
    r"^##\s+Error Handling",
]


class V:
    def __init__(self, path: Path):
        self.path = path
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def ok(self) -> bool:
        return not self.errors


def validate(tool_dir: Path) -> V:
    v = V(tool_dir)
    name = tool_dir.name

    if not DIR_NAME_RE.match(name):
        v.err(f"Directory name does not match ^org\\.ORG\\.DOMAIN\\.NAME$: {name}")

    manifest_path = tool_dir / "manifest.yaml"
    py_path = tool_dir / f"{name}.py"
    skills_path = tool_dir / "Skills.md"

    for required in (manifest_path, py_path, skills_path):
        if not required.exists():
            v.err(f"Missing file: {required.name}")
    if v.errors:
        return v

    _check_manifest(manifest_path, name, v)
    _check_python(py_path, v)
    _check_skills(skills_path, v)
    return v


def _check_manifest(path: Path, dir_name: str, v: V) -> None:
    try:
        m = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        v.err(f"manifest.yaml: invalid YAML — {e}")
        return

    required = ["canonical_id", "name", "version", "description", "status",
                "metadata", "runtime", "parameters", "output_schema",
                "credentials", "capabilities"]
    for key in required:
        if key not in m:
            v.err(f"manifest.yaml: missing required key '{key}'")

    cid = m.get("canonical_id", "")
    version = m.get("version", "")
    if not isinstance(cid, str) or f"{dir_name}/" not in cid:
        v.err(f"manifest.yaml: canonical_id '{cid}' must start with '{dir_name}/'")
    if not SEMVER_RE.match(str(version)):
        v.err(f"manifest.yaml: version '{version}' is not semver")
    if m.get("status") not in {"draft", "certified"}:
        v.err(f"manifest.yaml: status must be 'draft' or 'certified' (got '{m.get('status')}')")

    desc = m.get("description", "") or ""
    if len(desc) < 20 or len(desc) > 500:
        v.err(f"manifest.yaml: description length {len(desc)} outside 20–500 chars")

    meta = m.get("metadata") or {}
    org_ns = meta.get("org_namespace", "")
    expected_org = dir_name.split(".")[1] if "." in dir_name else ""
    if org_ns != expected_org:
        v.err(f"metadata.org_namespace '{org_ns}' != directory org '{expected_org}'")
    if meta.get("domain") not in VALID_DOMAINS:
        v.err(f"metadata.domain '{meta.get('domain')}' not in {sorted(VALID_DOMAINS)}")
    if meta.get("intent") not in VALID_INTENTS:
        v.err(f"metadata.intent '{meta.get('intent')}' not in {sorted(VALID_INTENTS)}")
    tags = meta.get("tags") or []
    if not isinstance(tags, list) or len(tags) < 3:
        v.err(f"metadata.tags must be array with 3+ entries")

    rt = m.get("runtime") or {}
    if rt.get("language") != "python":
        v.err("runtime.language must be 'python'")
    if rt.get("entry_point") != "main":
        v.err("runtime.entry_point must be 'main'")
    pkgs = rt.get("python_packages") or []
    if any(p in FORBIDDEN_IMPORTS for p in pkgs):
        v.err(f"runtime.python_packages contains forbidden: {set(pkgs) & FORBIDDEN_IMPORTS}")

    caps = m.get("capabilities") or {}
    if "max_execution_time_ms" not in caps:
        v.err("capabilities.max_execution_time_ms required")


def _check_python(path: Path, v: V) -> None:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        v.err(f"{path.name}: Python syntax error — {e}")
        return

    fns = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if "main" not in fns:
        v.err(f"{path.name}: missing 'def main(context)'")
    if "execute" not in fns:
        v.err(f"{path.name}: missing 'async def execute(params)'")

    imports: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imports.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            imports.add(n.module.split(".")[0])
    bad = imports & FORBIDDEN_IMPORTS
    if bad:
        v.err(f"{path.name}: forbidden imports {bad} — use sdk/fortimanager_client.py")
    if "fortimanager_client" not in imports:
        v.err(f"{path.name}: must import from fortimanager_client (the shared SDK)")

    if "if __name__" not in src:
        v.warn(f"{path.name}: no '__main__' block — CLI smoke test missing")


def _check_skills(path: Path, v: V) -> None:
    text = path.read_text(encoding="utf-8")
    for pat in SKILLS_REQUIRED_SECTIONS:
        if not re.search(pat, text, re.MULTILINE):
            v.err(f"Skills.md: missing required section matching /{pat}/")
    # Count example prompts (bulleted quoted strings under How to Call)
    m = re.search(r"##\s+How to Call(.*?)(\n##\s|\Z)", text, re.DOTALL)
    if m:
        prompts = re.findall(r'^\s*-\s*"[^"]+"\s*$', m.group(1), re.MULTILINE)
        if len(prompts) < 3:
            v.err(f"Skills.md: need 3+ example prompts in 'How to Call' (found {len(prompts)})")


def _report(v: V) -> int:
    name = v.path.name
    if v.ok():
        warn = f"  ({len(v.warnings)} warnings)" if v.warnings else ""
        print(f"PASS  {name}{warn}")
        for w in v.warnings:
            print(f"  WARN: {w}")
        return 0
    print(f"FAIL  {name}")
    for e in v.errors:
        print(f"  ERR:  {e}")
    for w in v.warnings:
        print(f"  WARN: {w}")
    return 1


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    if args[0] == "--all":
        targets = sorted([p for p in TOOLS_DIR.iterdir() if p.is_dir() and p.name.startswith("org.")])
    else:
        targets = [Path(a) for a in args]

    if not targets:
        print("No tools found.")
        return 1

    rc = 0
    for t in targets:
        if not t.exists() or not t.is_dir():
            print(f"SKIP  {t}  (not a directory)")
            rc = 1
            continue
        rc |= _report(validate(t))
    return rc


if __name__ == "__main__":
    sys.exit(main())
