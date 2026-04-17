#!/usr/bin/env python3
"""
new_tool.py — Scaffold a new FortiManager SDK tool from templates.

Usage:
  python scripts/new_tool.py org.<org>.<domain>.fortimanager-<subject>-<action>

Example:
  python scripts/new_tool.py org.acme.noc.fortimanager-firewall-address-list
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DIR_NAME_RE = re.compile(r"^org\.[a-z0-9-]+\.[a-z][a-z-]*\.[a-z][a-z0-9-]+$")
SDK_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = SDK_ROOT / "tools"
TEMPLATE_DIR = SDK_ROOT / "templates" / "tool_template"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    name = sys.argv[1]
    if not DIR_NAME_RE.match(name):
        print(f"ERROR: '{name}' does not match ^org\\.ORG\\.DOMAIN\\.NAME$")
        return 1

    parts = name.split(".")
    org = parts[1]
    domain = parts[2]
    subject_action = parts[3]           # e.g. fortimanager-firewall-address-list
    human = subject_action.replace("-", " ").title()

    target = TOOLS_DIR / name
    if target.exists():
        print(f"ERROR: {target} already exists")
        return 1

    if not TEMPLATE_DIR.exists():
        print(f"ERROR: template not found at {TEMPLATE_DIR}")
        return 1

    target.mkdir(parents=True)
    subs = {
        "{{CANONICAL_DIR}}": name,
        "{{CANONICAL_ID}}": f"{name}/1.0.0",
        "{{NAME}}": human,
        "{{ORG}}": org,
        "{{DOMAIN}}": domain,
    }

    for src in TEMPLATE_DIR.iterdir():
        if src.is_dir():
            continue
        out_name = src.name.replace("tool_template", name)
        dst = target / out_name
        text = src.read_text(encoding="utf-8")
        for k, v in subs.items():
            text = text.replace(k, v)
        dst.write_text(text, encoding="utf-8")

    print(f"Created {target}")
    print("Next:")
    print(f"  1. Edit {target/'manifest.yaml'}  (description, intent, params)")
    print(f"  2. Implement execute() in {target/(name+'.py')}")
    print(f"  3. Flesh out {target/'Skills.md'}")
    print(f"  4. python scripts/validate_tool.py {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
