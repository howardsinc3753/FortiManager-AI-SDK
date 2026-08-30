#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager ADOM Init - Bootstrap a fresh ADOM with the full BOR-SASE state.

Encodes the "Phase 1: ADOM Prep" of the BOR-SASE deployment workflow as a
single idempotent SDK tool. A partner points this at a fresh (or existing)
ADOM and it creates:

  - 56 meta variables (48 spoke + 8 SPA fabric)
  - 3 normalized interfaces (LAN_ZONE, SDWAN_ZONE, Underlay_ZONE) with 45
    platform_mappings each
  - 22 CLI templates (12 BOR spoke + 10 BOR-SPA hub) from .j2 files in
    content/templates/
  - 4 CLI template groups (BOR-SINGLE-STD, BOR-SINGLE-STD-HW,
    BOR-SPA-SINGLE-STD-VM, BOR-SPA-SINGLE-STD-HW)
  - 3 firewall addresses (LOCAL-LAN, BOR_Primary_PUBLIC, BOR_Secondary_PUBLIC)
  - 2 traffic shapers (BOR_UP_SHAPER, BOR_DOWN_SHAPER)
  - 2 Policy Packages (BOR-SINGLE-STD-PKG spoke, BOR-SPA-SINGLE-STD-PKG hub)
    each with their policies + shaping-policy
  - 8 Blueprints (spoke + hub across VM/30G/50G/120G)
  - 3 DVMDB device groups (BOR_Branch_Single, BOR_Branch_Dual,
    BOR_Branch_SPA_Hub)

Idempotent - safe to re-run. Uses `set` on named URLs (create-or-update) and
tolerates `-2 already exists` on collection adds.

After running this, the partner can use `model-device-import-csv v1.2.1+` to
import per-site devices via CSVs from the config-generator.

Usage:
    python org.ulysses.noc.fortimanager-adom-init.py \\
        --fmg-host 192.168.1.1 \\
        --adom BOR_Customer_8 \\
        --tenant-config my-customer.yaml
    (add --create-adom to auto-create the ADOM if it doesn't exist)
    (add --dry-run to print what would happen without calling FMG)

See content/tenant-defaults.example.yaml for the tenant config shape.

Author: Ulysses Project
Version: 1.0.0
"""
import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

_SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if _SDK_PATH.exists() and str(_SDK_PATH) not in sys.path:
    sys.path.insert(0, str(_SDK_PATH))

from fortimanager_client import FortiManagerClient  # noqa: E402

CONTENT_DIR = Path(__file__).parent / "content"


def _st(r: dict) -> dict:
    return (r.get("result", [{}])[0] or {}).get("status") or {}


class AdomInitializer:
    def __init__(self, host: str, adom: str, tenant_config_path: str | None = None,
                 dry_run: bool = False, create_adom: bool = False):
        self.host = host
        self.adom = adom
        self.dry_run = dry_run
        self.create_adom_flag = create_adom
        self.client = FortiManagerClient(host=host)
        self.manifest = yaml.safe_load((CONTENT_DIR / "adom-manifest.yaml").read_text(encoding="utf-8"))
        self.platforms = yaml.safe_load((CONTENT_DIR / "platform-list.yaml").read_text(encoding="utf-8"))["platforms"]
        self.tenant_config = {}
        if tenant_config_path:
            self.tenant_config = yaml.safe_load(Path(tenant_config_path).read_text(encoding="utf-8"))
        self.summary = {"ok": 0, "skipped": 0, "failed": 0, "errors": []}

    # ==== HTTP wrappers ====================================================
    def _call(self, method: str, url: str, **kwargs) -> dict:
        if self.dry_run:
            print(f"    [DRY-RUN] {method} {url}")
            return {"result": [{"status": {"code": 0, "message": "OK (dry-run)"}}]}
        return self.client.call(method, url, **kwargs)

    def _get(self, url: str, **kwargs) -> dict:
        if self.dry_run:
            return {"result": [{"status": {"code": -3, "message": "N/A (dry-run)"}, "data": None}]}
        return self.client.get(url, **kwargs)

    def _track(self, label: str, status: dict, allow_codes: tuple = (0, -2)) -> bool:
        code = status.get("code")
        if code in allow_codes:
            self.summary["ok"] += 1
            return True
        self.summary["failed"] += 1
        err = f"{label}: code={code} msg={(status.get('message') or '')[:120]}"
        self.summary["errors"].append(err)
        return False

    # ==== Stages ==========================================================
    def stage_adom(self):
        """Verify/create ADOM."""
        r = self._get(f"/dvmdb/adom/{self.adom}", fields=["name", "oid"])
        code = _st(r).get("code")
        if code == 0:
            d = (r.get("result", [{}])[0] or {}).get("data") or {}
            print(f"  ADOM {self.adom!r} exists (oid {d.get('oid')})")
            return
        if not self.create_adom_flag:
            print(f"  ADOM {self.adom!r} does NOT exist. Rerun with --create-adom to auto-create, OR create it via FMG GUI first.")
            raise SystemExit(2)
        print(f"  Creating ADOM {self.adom!r}...")
        r = self._call("add", "/dvmdb/adom",
                       data={"name": self.adom, "os_ver": 7, "mr": 6, "restricted_prds": 1})
        self._track(f"ADOM {self.adom}", _st(r))

    def stage_meta_vars(self):
        for mv in self.manifest.get("meta_vars", []):
            name = mv["name"]
            default = self.tenant_config.get(name, mv.get("default") or "")
            data = {"name": name, "value": default}
            if mv.get("description"):
                data["description"] = mv["description"]
            r = self._call("set", f"/pm/config/adom/{self.adom}/obj/fmg/variable/{name}", data=data)
            self._track(f"meta_var {name}", _st(r))

    def stage_normalized_interfaces(self):
        for ni in self.manifest.get("normalized_interfaces", []):
            name = ni["name"]
            # Create interface
            r = self._call("set", f"/pm/config/adom/{self.adom}/obj/dynamic/interface/{name}",
                           data={"name": name, "description": ni.get("description") or ""})
            self._track(f"normalized_interface {name}", _st(r))
            # Bulk-add platform_mappings (all 45 platforms)
            intf_zone = ni.get("intf_zone") or name
            for plat in self.platforms:
                r = self._call("add",
                               f"/pm/config/adom/{self.adom}/obj/dynamic/interface/{name}/platform_mapping",
                               data={"name": plat, "intf-zone": intf_zone})
                # -2 (already exists) is OK
                self._track(f"platform_mapping {name}/{plat}", _st(r))

    def stage_cli_templates(self):
        # Read all .j2 files under content/templates/**
        for subfolder in ("bor-single", "bor-spa-single"):
            tpl_dir = CONTENT_DIR / "templates" / subfolder
            if not tpl_dir.exists():
                continue
            for tpl_file in sorted(tpl_dir.glob("*.j2")):
                name = tpl_file.stem
                script = tpl_file.read_text(encoding="utf-8")
                data = {
                    "name": name,
                    "type": 1,
                    "script": script,
                    "description": f"BOR-SASE {name} - provisioned by adom-init tool",
                }
                r = self._call("set", f"/pm/config/adom/{self.adom}/obj/cli/template/{name}", data=data)
                self._track(f"cli_template {name}", _st(r))

    def stage_template_groups(self):
        for tg in self.manifest.get("template_groups", []):
            name = tg["name"]
            data = {
                "name": name,
                "description": tg.get("description") or "",
                "member": tg.get("members", []),
            }
            r = self._call("set", f"/pm/config/adom/{self.adom}/obj/cli/template-group/{name}", data=data)
            self._track(f"template_group {name}", _st(r))

    def stage_firewall_addresses(self):
        for addr in self.manifest.get("firewall_addresses", []):
            name = addr["name"]
            payload: dict[str, Any] = {"name": name}
            if addr.get("type") is not None:
                payload["type"] = addr["type"]
            if addr.get("subnet"):
                payload["subnet"] = addr["subnet"]
            if addr.get("fqdn"):
                payload["fqdn"] = addr["fqdn"]
            if addr.get("allow_routing") is not None:
                payload["allow-routing"] = addr["allow_routing"]
            r = self._call("set", f"/pm/config/adom/{self.adom}/obj/firewall/address/{name}", data=payload)
            self._track(f"address {name}", _st(r))

    def stage_shapers(self):
        for sh in self.manifest.get("shapers", []):
            name = sh["name"]
            data = {
                "name": name,
                "guaranteed-bandwidth": sh.get("guaranteed_bandwidth") or 0,
                "maximum-bandwidth": sh.get("maximum_bandwidth") or 100,
                "bandwidth-unit": sh.get("bandwidth_unit") or 1,
            }
            r = self._call("set", f"/pm/config/adom/{self.adom}/obj/firewall/shaper/traffic-shaper/{name}",
                           data=data)
            self._track(f"shaper {name}", _st(r))

    def stage_policy_packages(self):
        for pp in self.manifest.get("policy_packages", []):
            name = pp["name"]
            # Create pkg (idempotent — -2 already exists is OK)
            r = self._call("add", f"/pm/pkg/adom/{self.adom}",
                           data={"name": name, "type": "pkg"})
            self._track(f"pkg {name}", _st(r))
            # Policies
            for pol in pp.get("policies", []):
                data = {
                    "policyid": pol["policyid"],
                    "name": pol["name"],
                    "srcintf": pol.get("srcintf") or [],
                    "dstintf": pol.get("dstintf") or [],
                    "srcaddr": pol.get("srcaddr") or [],
                    "dstaddr": pol.get("dstaddr") or [],
                    "action": pol.get("action") if pol.get("action") is not None else 1,
                    "schedule": pol.get("schedule") or ["always"],
                    "service": pol.get("service") or ["ALL"],
                }
                if pol.get("nat") is not None:
                    data["nat"] = pol["nat"]
                if pol.get("logtraffic") is not None:
                    data["logtraffic"] = pol["logtraffic"]
                r = self._call("add",
                               f"/pm/config/adom/{self.adom}/pkg/{name}/firewall/policy", data=data)
                self._track(f"policy {name}[{pol['policyid']}]", _st(r))
            # Shaping-policies
            for sp in pp.get("shaping_policies", []):
                data = {
                    "id": sp["id"],
                    "name": sp["name"],
                    "service": sp.get("service") or ["ALL"],
                    "srcaddr": sp.get("srcaddr") or ["all"],
                    "dstaddr": sp.get("dstaddr") or ["all"],
                    "dstintf": sp.get("dstintf") or [],
                    "traffic-shaper": sp["traffic_shaper"],
                    "traffic-shaper-reverse": sp["traffic_shaper_reverse"],
                }
                r = self._call("add",
                               f"/pm/config/adom/{self.adom}/pkg/{name}/firewall/shaping-policy",
                               data=data)
                self._track(f"shaping-policy {name}[{sp['id']}]", _st(r))

    def stage_blueprints(self):
        for bp in self.manifest.get("blueprints", []):
            name = bp["name"]
            data = {
                "name": name,
                "platform": bp["platform"],
                "prov-type": bp.get("prov_type") if bp.get("prov_type") is not None else 1,
                "cliprofs": bp.get("cliprofs") or [],
                "prerun-cliprof": bp.get("prerun_cliprof") or [],
                "pkg": bp["pkg"],
                "port-provisioning": bp.get("port_provisioning") if bp.get("port_provisioning") is not None else 1,
                "linked-to-model": bp.get("linked_to_model") if bp.get("linked_to_model") is not None else 1,
                "enforce-device-config": bp.get("enforce_device_config") if bp.get("enforce_device_config") is not None else 0,
            }
            r = self._call("set",
                           f"/pm/config/adom/{self.adom}/obj/fmg/device/blueprint/{name}", data=data)
            self._track(f"blueprint {name}", _st(r))

    def stage_device_groups(self):
        for dg in self.manifest.get("device_groups", []):
            name = dg["name"]
            data = {
                "name": name,
                "desc": dg.get("description") or "",
                "type": dg.get("type") or "normal",
                "meta fields": {},
                "os_type": dg.get("os_type") or "fos",
            }
            r = self._call("add", f"/dvmdb/adom/{self.adom}/group/{name}", data=data)
            self._track(f"device_group {name}", _st(r))

    # ==== Orchestration ===================================================
    def run(self):
        print("=" * 70)
        print(f"FortiManager ADOM Init - target: {self.adom}")
        print(f"  FMG host      : {self.host}")
        print(f"  Tenant config : {'(none — using manifest defaults)' if not self.tenant_config else 'loaded'}")
        print(f"  Dry-run       : {self.dry_run}")
        print(f"  Create ADOM   : {self.create_adom_flag}")
        print("=" * 70)

        stages = [
            ("1. ADOM verify/create",                    self.stage_adom),
            ("2. Meta variables",                         self.stage_meta_vars),
            ("3. Normalized interfaces + platform_mapping", self.stage_normalized_interfaces),
            ("4. CLI templates",                          self.stage_cli_templates),
            ("5. CLI template groups",                    self.stage_template_groups),
            ("6. Firewall addresses",                     self.stage_firewall_addresses),
            ("7. Traffic shapers",                        self.stage_shapers),
            ("8. Policy packages + policies + shapers",   self.stage_policy_packages),
            ("9. Device blueprints",                      self.stage_blueprints),
            ("10. DVMDB device groups",                   self.stage_device_groups),
        ]
        for label, fn in stages:
            print(f"\n{label}")
            print("-" * 70)
            fn()

        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"  OK    : {self.summary['ok']}")
        print(f"  Failed: {self.summary['failed']}")
        if self.summary["errors"]:
            print(f"\n  Errors (first 20):")
            for e in self.summary["errors"][:20]:
                print(f"    - {e}")
        else:
            print(f"\n  ADOM {self.adom!r} is READY for CSV imports (Phase 2).")
            print(f"  Next: model-device-import-csv v1.2.1+ with your site CSVs.")


def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap a fresh FortiManager ADOM with the full BOR-SASE state (Phase 1 of the deployment workflow).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--fmg-host", required=True, help="FortiManager hostname/IP")
    parser.add_argument("--adom", required=True, help="Target ADOM name")
    parser.add_argument("--tenant-config",
                        help="YAML file with tenant-specific meta var overrides. See content/tenant-defaults.example.yaml")
    parser.add_argument("--create-adom", action="store_true",
                        help="Auto-create the ADOM if it doesn't exist (default: fail if ADOM missing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without calling FMG")
    args = parser.parse_args()

    init = AdomInitializer(
        host=args.fmg_host, adom=args.adom,
        tenant_config_path=args.tenant_config,
        dry_run=args.dry_run,
        create_adom=args.create_adom,
    )
    init.run()


if __name__ == "__main__":
    main()
