#!/usr/bin/env python3
from __future__ import annotations
"""
FortiManager JSON-RPC API Client — Shared SDK Module

Provides the base HTTP client for all FortiManager SDK tools.
Implements the FortiManager 7.6 JSON-RPC API authentication and request patterns.

Auth Modes:
  - token   : Bearer <api_token> in Authorization header (FMG 7.2+, preferred)
  - session : exec /sys/login/user, reuse session token across calls

URL Paths (common):
  /sys/login/user              — Login (session mode)
  /sys/logout                  — Logout (session mode)
  /sys/status                  — System status / version check
  /dvmdb/adom                  — List ADOMs
  /dvmdb/adom/{adom}/device    — List devices in ADOM
  /pm/pkg/adom/{adom}          — List policy packages
  /pm/config/adom/{adom}/pkg/{pkg}/firewall/policy  — Policies
  /dvmdb/script                — Scripts
  /dvmdb/script/execute        — Execute script

JSON-RPC Envelope:
  {
    "id": <int>,
    "method": "get|set|add|update|delete|exec|clone|move",
    "params": [ {"url": "...", "data": {...}, "option": [...]} ],
    "session": "<token>"    # session mode only
  }

Reference: https://how-to-fortimanager-api.readthedocs.io/en/latest/
"""

import urllib.request
import urllib.error
import ssl
import json
import os
from pathlib import Path
from typing import Any, Optional

import yaml


CREDENTIAL_SEARCH_PATHS = [
    os.path.expanduser("~/.config/mcp"),
    os.path.expanduser("~/AppData/Local/mcp"),
    "C:/ProgramData/mcp",
]


def _make_ssl_context(verify: bool = False) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def load_credentials(host: str) -> dict:
    """Load FortiManager credentials from fortimanager_credentials.yaml.

    Returns dict with keys: host, port, auth_method, api_token|username/password,
    verify_ssl, (optional) notes.
    """
    for base in CREDENTIAL_SEARCH_PATHS:
        path = Path(base) / "fortimanager_credentials.yaml"
        if not path.exists():
            continue
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        for _, dev in (data.get("devices") or {}).items():
            if dev.get("host") == host:
                return dev
    raise RuntimeError(
        f"No credentials found for {host}. "
        f"Create ~/.config/mcp/fortimanager_credentials.yaml"
    )


class FortiManagerClient:
    """FortiManager JSON-RPC client supporting token and session auth."""

    def __init__(
        self,
        host: str,
        auth_method: Optional[str] = None,
        api_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        port: int = 443,
        verify_ssl: bool = False,
        timeout: int = 30,
    ):
        self.host = host

        # Auto-load from credentials file if any required field missing
        need_load = (
            (auth_method == "token" and not api_token) or
            (auth_method == "session" and not (username and password)) or
            (auth_method is None and not api_token and not (username and password))
        )
        if need_load:
            creds = load_credentials(host)
            auth_method = auth_method or creds.get("auth_method", "token")
            api_token = api_token or creds.get("api_token")
            username = username or creds.get("username")
            password = password or creds.get("password")
            port = creds.get("port", port)
            verify_ssl = creds.get("verify_ssl", verify_ssl)

        self.auth_method = auth_method or "token"
        self.api_token = api_token
        self.username = username
        self.password = password
        self.port = port
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.session: Optional[str] = None
        self._req_id = 0
        self.base_url = f"https://{host}:{port}/jsonrpc"

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _request(self, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.auth_method == "token" and self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        req = urllib.request.Request(
            self.base_url, data=body, headers=headers, method="POST"
        )
        ctx = _make_ssl_context(self.verify_ssl)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"FMG HTTP {e.code}: {body}") from e

    def login(self) -> Optional[str]:
        """Login (session auth only). Token auth is stateless — no-op."""
        if self.auth_method == "token":
            return None
        if not (self.username and self.password):
            raise RuntimeError("session auth requires username and password")
        payload = {
            "id": self._next_id(),
            "method": "exec",
            "params": [{
                "url": "/sys/login/user",
                "data": {"user": self.username, "passwd": self.password},
            }],
        }
        resp = self._request(payload)
        status = resp.get("result", [{}])[0].get("status", {})
        if status.get("code") != 0:
            raise RuntimeError(f"FMG login failed: {status}")
        self.session = resp.get("session")
        if not self.session:
            raise RuntimeError("FMG login returned no session token")
        return self.session

    def logout(self) -> None:
        if self.auth_method == "token" or not self.session:
            return
        payload = {
            "id": self._next_id(),
            "method": "exec",
            "params": [{"url": "/sys/logout"}],
            "session": self.session,
        }
        try:
            self._request(payload)
        except Exception:
            pass
        self.session = None

    def call(self, method: str, url: str, data: Optional[dict] = None,
             option: Optional[list] = None, fields: Optional[list] = None,
             filter: Optional[list] = None, range: Optional[list] = None) -> dict:
        """Generic JSON-RPC call.

        FMG GET supports extra param keys beyond `url`:
          fields : list of field names to return (reduces payload)
          filter : nested list for server-side filtering, e.g. [["name","==","x"]]
          range  : [offset, limit] pagination, e.g. [0, 50]
          option : FMG options like ["object member","no loadsub","scope member"]
        """
        if self.auth_method == "session" and not self.session:
            self.login()
        params: dict = {"url": url}
        if data is not None:
            params["data"] = data
        if option is not None:
            params["option"] = option
        if fields is not None:
            params["fields"] = fields
        if filter is not None:
            params["filter"] = filter
        if range is not None:
            params["range"] = range
        payload: dict = {
            "id": self._next_id(),
            "method": method,
            "params": [params],
        }
        if self.session:
            payload["session"] = self.session
        return self._request(payload)

    def get(self, url: str, fields: Optional[list] = None,
            filter: Optional[list] = None, range: Optional[list] = None,
            option: Optional[list] = None) -> dict:
        return self.call("get", url, fields=fields, filter=filter,
                         range=range, option=option)

    def exec(self, url: str, data: Optional[dict] = None) -> dict:
        return self.call("exec", url, data=data)

    def set(self, url: str, data: dict) -> dict:
        return self.call("set", url, data=data)

    def add(self, url: str, data: dict) -> dict:
        return self.call("add", url, data=data)

    def delete(self, url: str, data: Optional[dict] = None) -> dict:
        return self.call("delete", url, data=data)

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.logout()
