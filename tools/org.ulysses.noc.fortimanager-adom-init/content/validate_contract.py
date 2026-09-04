#!/usr/bin/env python3
"""
FMG SDK -> Contract validator.

Reads the byte-vendored roles-and-columns.yaml (../../../contract/) and asserts
this repo's adom-manifest.yaml + platform-list.yaml + content/templates/{role}/
match the frozen contract. Fail-loud if they drift - a mismatch here means an
install-time failure downstream (missing blueprint, Jinja undefined var, wrong
policy package binding).

Runs at:
  - `adom-init --create-adom`  (before any FMG writes - fail before we
                                 bootstrap a broken ADOM)
  - CI                          (per-commit)

If you're reading this because a validator failure blocked you: don't patch
this file to make it pass. Either fix the drift (usually adom-manifest.yaml or
a template .j2), or update the contract in the FortiSASE App repo first, then
re-vendor a byte-identical copy to FortiManager-AI-SDK/contract/. Contract is
the source of truth.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

# Layout: this file is content/validate_contract.py; contract dir is repo-root/contract/
_CONTENT_DIR = Path(__file__).parent
_TOOL_DIR = _CONTENT_DIR.parent
_REPO_ROOT = _TOOL_DIR.parents[1]          # tools/<tool>/content/ -> repo root
_CONTRACT_FILE = _REPO_ROOT / "contract" / "roles-and-columns.yaml"

# App uses short aliases in the contract (VM/30G/50G/120G); manifest carries the
# full FortiOS platform string. This is the ONLY translation the SDK owns.
_PLATFORM_ALIAS_TO_FORTIOS = {
    "VM":   "FortiGate-VM64-KVM",
    "30G":  "FortiGate-30G",
    "50G":  "FortiGate-50G",
    "120G": "FortiGate-120G",
}

# Match `{{ VAR_NAME }}` OR `{% ... VAR_NAME ... %}` in Jinja templates. Case-
# sensitive uppercase names are the meta-var convention; lowercase words in
# expressions (e.g. `is defined`, `if`) are ignored.
_JINJA_TOKEN_RE = re.compile(r"\{\{[^}]*?\b([A-Z][A-Z0-9_]*)\b[^}]*?\}\}"
                             r"|\{%[^%]*?\b([A-Z][A-Z0-9_]*)\b[^%]*?%\}")


class ContractDrift(Exception):
    """Raised on any invariant break. Carries a list of drift messages."""

    def __init__(self, drifts: list[str]):
        super().__init__(f"{len(drifts)} contract invariant(s) violated")
        self.drifts = drifts


# ==================================================================
# Loaders
# ==================================================================
def load_contract() -> dict:
    if not _CONTRACT_FILE.exists():
        raise FileNotFoundError(
            f"Contract not found at {_CONTRACT_FILE}. Vendor a byte-identical "
            f"copy from FortiSASE-SDK/automation/sdwan-ztp/config-generator/"
            f"contract/roles-and-columns.yaml.")
    return yaml.safe_load(_CONTRACT_FILE.read_text(encoding="utf-8"))


def load_manifest() -> dict:
    return yaml.safe_load((_CONTENT_DIR / "adom-manifest.yaml").read_text(encoding="utf-8"))


def load_platform_list() -> dict:
    return yaml.safe_load((_CONTENT_DIR / "platform-list.yaml").read_text(encoding="utf-8"))


def _extract_jinja_vars(text: str) -> set[str]:
    """Return the set of UPPER_SNAKE identifiers referenced inside {{ }} or {% %}."""
    hits = set()
    for m in _JINJA_TOKEN_RE.finditer(text):
        for group in m.groups():
            if group:
                hits.add(group)
    return hits


def _template_vars_in_folder(folder: Path) -> set[str]:
    """Union of meta-var names referenced by every .j2 under `folder`."""
    vars_seen: set[str] = set()
    for j2 in folder.rglob("*.j2"):
        vars_seen |= _extract_jinja_vars(j2.read_text(encoding="utf-8"))
    return vars_seen


# ==================================================================
# Assertions
# ==================================================================
def _bp_names(manifest: dict) -> set[str]:
    return {bp.get("name") for bp in (manifest.get("blueprints") or []) if bp.get("name")}


def _tg_names(manifest: dict) -> set[str]:
    return {tg.get("name") for tg in (manifest.get("template_groups") or []) if tg.get("name")}


def _pkg_names(manifest: dict) -> set[str]:
    return {p.get("name") for p in (manifest.get("policy_packages") or []) if p.get("name")}


def _dg_names(manifest: dict) -> set[str]:
    return {g.get("name") for g in (manifest.get("device_groups") or []) if g.get("name")}


def _mv_names(manifest: dict) -> set[str]:
    return {v.get("name") for v in (manifest.get("meta_vars") or [])
            if isinstance(v, dict) and v.get("name")}


def validate(contract: dict, manifest: dict, platforms: dict) -> list[str]:
    """Return a list of drift messages. Empty list = GREEN."""
    drifts: list[str] = []
    bp_names = _bp_names(manifest)
    tg_names = _tg_names(manifest)
    pkg_names = _pkg_names(manifest)
    dg_names = _dg_names(manifest)
    manifest_meta_vars = _mv_names(manifest)
    contract_meta_vars_all_scopes = set((contract.get("meta_vars") or {}).keys())

    # Fallback for a role that has NO applies_to hits: use contract-wide union
    def _contract_vars_for_role(role_id: str) -> set[str]:
        """Every meta_var whose applies_to matches this role, regardless of scope."""
        catalog = contract.get("meta_vars") or {}
        hits = set()
        for name, spec in catalog.items():
            applies_to = (spec or {}).get("applies_to", "all")
            if applies_to == "all":
                hits.add(name)
            elif applies_to == "dual" and "dual" in role_id:
                hits.add(name)
            elif applies_to == "spa" and "spa" in role_id:
                hits.add(name)
        return hits

    for role in contract.get("roles") or []:
        rid = role["id"]
        fmg = role.get("fmg") or {}
        template_folder = _CONTENT_DIR / "templates" / fmg.get("template_folder", "")
        blueprint_prefix = fmg.get("blueprint_prefix", "")
        tg_map = fmg.get("template_group") or {}

        # ---- #1 - template folder exists on disk ----
        if not template_folder.is_dir():
            drifts.append(f"[{rid}] template folder missing: {template_folder}")
            continue    # remaining checks need the folder

        # ---- #2 - blueprint exists per platform ----
        for plat in role.get("platforms") or []:
            expected = f"{blueprint_prefix}-{plat}"
            if expected not in bp_names:
                drifts.append(f"[{rid}] blueprint missing in adom-manifest.yaml: {expected}")

        # ---- #3 - template_group.{vm,hw} exist ----
        for kind in ("vm", "hw"):
            tg = tg_map.get(kind)
            if not tg:
                drifts.append(f"[{rid}] template_group.{kind} not declared in contract")
            elif tg not in tg_names:
                drifts.append(f"[{rid}] template_group.{kind} '{tg}' missing in adom-manifest.yaml")

        # ---- #4 - policy_package + device_group exist ----
        pkg = fmg.get("policy_package")
        if not pkg or pkg not in pkg_names:
            drifts.append(f"[{rid}] policy_package '{pkg}' missing in adom-manifest.yaml")
        dg = fmg.get("device_group")
        if not dg or dg not in dg_names:
            drifts.append(f"[{rid}] device_group '{dg}' missing in adom-manifest.yaml")

        # ---- #5 - templates ONLY reference vars declared in contract ----
        # App Claude's refinement (a): use ALL scopes (per_device + tenant + sdk_internal),
        # since scope classifies WHERE the value comes from, not whether templates use it.
        # Refinement (b): scan is naturally scoped to the role folder because all our
        # templates are role-scoped today (no shared/system folder). If we ever add shared
        # templates, extend this scan.
        template_vars = _template_vars_in_folder(template_folder)
        contract_vars_for_role = _contract_vars_for_role(rid)
        undeclared = template_vars - contract_meta_vars_all_scopes
        # Filter out common false-positives - Jinja keywords / macro locals that happen
        # to match UPPER_SNAKE (rare, but safe to allowlist).
        _JINJA_KEYWORDS = {"TRUE", "FALSE", "NONE", "AND", "OR", "NOT", "IN", "IS"}
        undeclared -= _JINJA_KEYWORDS
        for v in sorted(undeclared):
            drifts.append(f"[{rid}] template references '{v}' but contract meta_vars doesn't declare it")
        # Also: any contract var supposedly applying to this role but never referenced?
        # We only warn on this - declared-but-unused isn't a functional break, it's tech debt.
        # (Skipping for v1 - tighten in v2 once catalog stabilizes.)

        # ---- Manifest completeness - every contract var used by this role must also be
        # in the manifest (adom-init needs to declare it as an FMG meta var). ----
        for v in contract_vars_for_role & template_vars:
            if v not in manifest_meta_vars:
                drifts.append(f"[{rid}] meta_var '{v}' used by templates + contract, "
                              "but missing from adom-manifest.yaml meta_vars[]")

    # ---- #6 - SITE_ID safety-belt (gotcha #17 - installs fail silently if SITE_ID
    # gets treated as tenant-scope; recurrence prevention) ----
    site_id_spec = (contract.get("meta_vars") or {}).get("SITE_ID") or {}
    if site_id_spec.get("scope") != "per_device":
        drifts.append(f"[GLOBAL] SITE_ID scope is '{site_id_spec.get('scope')}' in contract; "
                      "MUST be per_device (safety-belt for gotcha #17)")

    # ---- Platform alias sanity - every alias the contract uses must map to a real
    # FortiOS platform present in platform-list.yaml. ----
    known_platforms = {p if isinstance(p, str) else p.get("name") or p.get("platform")
                       for p in (platforms.get("platforms") or [])}
    for role in contract.get("roles") or []:
        for alias in role.get("platforms") or []:
            fortios = _PLATFORM_ALIAS_TO_FORTIOS.get(alias)
            if not fortios:
                drifts.append(f"[GLOBAL] platform alias '{alias}' has no FortiOS mapping "
                              "(edit _PLATFORM_ALIAS_TO_FORTIOS in this validator)")
            elif fortios not in known_platforms:
                drifts.append(f"[GLOBAL] platform alias '{alias}' -> '{fortios}' but that "
                              "FortiOS platform is not in platform-list.yaml")

    return drifts


def run(*, verbose: bool = True) -> bool:
    """Load + validate. Returns True on GREEN. Prints a report either way."""
    contract = load_contract()
    manifest = load_manifest()
    platforms = load_platform_list()
    drifts = validate(contract, manifest, platforms)
    if not drifts:
        if verbose:
            n_roles = len(contract.get("roles") or [])
            n_meta = len(contract.get("meta_vars") or {})
            # schema_version lives in a YAML comment today; parse it out.
            sv = "?"
            for line in _CONTRACT_FILE.read_text(encoding="utf-8").splitlines()[:10]:
                m = re.match(r"#\s*schema_version:\s*(\d+)", line)
                if m:
                    sv = m.group(1)
                    break
            print(f"[contract] GREEN - {n_roles} role(s) match contract v{sv} "
                  f"({n_meta} meta_vars declared)")
        return True
    print("[contract] RED - contract v1 drift detected:")
    for d in drifts:
        print(f"  - {d}")
    print(f"\n[contract] {len(drifts)} invariant(s) failed. Fix drift or update contract "
          "(App Claude re-authors; then vendor byte-identical to FMG-SDK/contract/).")
    return False


# ==================================================================
# CLI entry point
# ==================================================================
if __name__ == "__main__":
    ok = run(verbose=True)
    sys.exit(0 if ok else 2)
