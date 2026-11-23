#!/usr/bin/env python3
"""Enable Dropbear via GL.iNet /rpc and seed Dropbear authorized_keys via LuCI ubus.

Used after a firmware upgrade that keeps UCI (Dropbear disabled) but removes the
OpenSSH packages. Admin HTTPS remains reachable, so this restores temporary SSH
without clicking LuCI.

Requires: openssl (passwd), and network access to the router's management IP.
Prefer the management IP for GL /rpc — nginx may 403 SNI hostnames.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class RpcError(RuntimeError):
    """JSON-RPC or HTTP failure talking to the router."""


def _ssl_context(verify: bool) -> ssl.SSLContext:
    if verify:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _http_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    context: ssl.SSLContext,
    timeout: float,
) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers or {"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=context, timeout=timeout) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise RpcError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RpcError(f"request failed for {url}: {exc}") from exc
    if not isinstance(body, dict):
        raise RpcError(f"non-object JSON from {url}")
    return body


def glinet_login(
    rpc_url: str,
    password: str,
    *,
    context: ssl.SSLContext,
    timeout: float,
    username: str = "root",
) -> str:
    challenge = _http_json(
        rpc_url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "challenge",
            "params": {"username": username},
        },
        headers={"Content-Type": "application/json", "glinet": "1"},
        context=context,
        timeout=timeout,
    )
    result = challenge.get("result") or {}
    try:
        alg = int(result["alg"])
        salt = str(result["salt"])
        nonce = str(result["nonce"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RpcError(f"unexpected challenge payload: {challenge}") from exc
    if alg not in (1, 5, 6):
        raise RpcError(f"unsupported challenge.alg: {alg}")

    crypted = subprocess.run(
        ["openssl", "passwd", f"-{alg}", "-salt", salt, "-stdin"],
        input=password.encode(),
        capture_output=True,
        check=False,
    )
    if crypted.returncode != 0:
        err = crypted.stderr.decode(errors="replace").strip()
        raise RpcError(f"openssl passwd failed: {err or crypted.returncode}")
    crypt_text = crypted.stdout.decode().strip()
    digest = hashlib.sha256(f"{username}:{crypt_text}:{nonce}".encode()).hexdigest()

    login = _http_json(
        rpc_url,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "login",
            "params": {"username": username, "hash": digest},
        },
        headers={"Content-Type": "application/json", "glinet": "1"},
        context=context,
        timeout=timeout,
    )
    sid = (login.get("result") or {}).get("sid")
    if not sid:
        raise RpcError(f"login failed: {login}")
    return str(sid)


def glinet_call(
    rpc_url: str,
    sid: str,
    module: str,
    method: str,
    params: dict[str, Any] | None,
    *,
    context: ssl.SSLContext,
    timeout: float,
    req_id: int,
) -> Any:
    body = _http_json(
        rpc_url,
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "call",
            "params": [sid, module, method, params or {}],
        },
        headers={"Content-Type": "application/json", "glinet": "1"},
        context=context,
        timeout=timeout,
    )
    if "error" in body:
        raise RpcError(f"{module}.{method} error: {body['error']}")
    return body.get("result")


def luci_login(
    ubus_url: str,
    password: str,
    *,
    context: ssl.SSLContext,
    timeout: float,
    username: str = "root",
) -> str:
    body = _http_json(
        ubus_url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": [
                "00000000000000000000000000000000",
                "session",
                "login",
                {"username": username, "password": password},
            ],
        },
        context=context,
        timeout=timeout,
    )
    result = body.get("result")
    if not isinstance(result, list) or not result or result[0] != 0:
        raise RpcError(f"LuCI ubus login failed: {body}")
    sid = result[1].get("ubus_rpc_session")
    if not sid:
        raise RpcError(f"LuCI ubus login missing session: {body}")
    return str(sid)


def luci_call(
    ubus_url: str,
    sid: str,
    obj: str,
    method: str,
    params: dict[str, Any] | None,
    *,
    context: ssl.SSLContext,
    timeout: float,
) -> Any:
    body = _http_json(
        ubus_url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": [sid, obj, method, params or {}],
        },
        context=context,
        timeout=timeout,
    )
    if "error" in body:
        raise RpcError(f"ubus {obj}.{method} error: {body['error']}")
    result = body.get("result")
    if not isinstance(result, list) or not result:
        raise RpcError(f"ubus {obj}.{method} unexpected result: {body}")
    if result[0] != 0:
        raise RpcError(f"ubus {obj}.{method} status {result[0]}: {body}")
    return result[1] if len(result) > 1 else None


def _load_password(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RpcError(f"password file is empty: {path}")
    return text


def _load_authorized_keys(paths: list[Path]) -> str:
    keys: list[str] = []
    for path in paths:
        line = path.read_text(encoding="utf-8").strip()
        if not line:
            raise RpcError(f"authorized key file is empty: {path}")
        keys.append(line)
    if not keys:
        raise RpcError("no authorized key files provided")
    return "\n".join(keys) + "\n"


def enable_dropbear(
    *,
    rpc_url: str,
    ubus_url: str,
    password: str,
    authorized_keys: str,
    verify_tls: bool,
    timeout: float,
) -> dict[str, Any]:
    context = _ssl_context(verify_tls)
    summary: dict[str, Any] = {
        "ssh_enabled_before": None,
        "ssh_enabled_after": None,
        "dropbear_enable_changed": False,
        "authorized_keys_changed": False,
        "authorized_keys_path": "/etc/dropbear/authorized_keys",
    }

    sid = glinet_login(rpc_url, password, context=context, timeout=timeout)
    cfg = glinet_call(
        rpc_url,
        sid,
        "local-access",
        "get_config",
        {},
        context=context,
        timeout=timeout,
        req_id=3,
    )
    if not isinstance(cfg, dict):
        raise RpcError(f"local-access.get_config unexpected: {cfg}")
    summary["ssh_enabled_before"] = bool(cfg.get("ssh_enabled"))

    if not cfg.get("ssh_enabled"):
        payload = {
            "http_port": cfg["http_port"],
            "https_port": cfg["https_port"],
            "redirect_https": cfg["redirect_https"],
            "session_timeout": cfg["session_timeout"],
            "ssh_enabled": True,
            "ssh_port": cfg.get("ssh_port", 22),
            "luci_http_port": cfg["luci_http_port"],
            "luci_https_port": cfg["luci_https_port"],
            "luci_redirect_https": cfg["luci_redirect_https"],
        }
        glinet_call(
            rpc_url,
            sid,
            "local-access",
            "set_config",
            payload,
            context=context,
            timeout=timeout,
            req_id=4,
        )
        summary["dropbear_enable_changed"] = True

    cfg_after = glinet_call(
        rpc_url,
        sid,
        "local-access",
        "get_config",
        {},
        context=context,
        timeout=timeout,
        req_id=5,
    )
    summary["ssh_enabled_after"] = bool((cfg_after or {}).get("ssh_enabled"))

    ubus_sid = luci_login(ubus_url, password, context=context, timeout=timeout)
    existing = ""
    try:
        read = luci_call(
            ubus_url,
            ubus_sid,
            "file",
            "read",
            {"path": "/etc/dropbear/authorized_keys"},
            context=context,
            timeout=timeout,
        )
        if isinstance(read, dict):
            existing = str(read.get("data") or "")
    except RpcError:
        existing = ""

    if existing.strip() != authorized_keys.strip():
        luci_call(
            ubus_url,
            ubus_sid,
            "file",
            "write",
            {
                "path": "/etc/dropbear/authorized_keys",
                "data": authorized_keys,
                "mode": 0o600,
            },
            context=context,
            timeout=timeout,
        )
        summary["authorized_keys_changed"] = True

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rpc-url",
        required=True,
        help="GL.iNet JSON-RPC URL (prefer https://<management-ip>/rpc)",
    )
    parser.add_argument(
        "--ubus-url",
        required=True,
        help="LuCI ubus JSON-RPC URL (https://<host>:8443/ubus)",
    )
    parser.add_argument(
        "--password-file",
        type=Path,
        required=True,
        help="File containing the GL.iNet / LuCI root admin password",
    )
    parser.add_argument(
        "--authorized-key-file",
        type=Path,
        action="append",
        dest="authorized_key_files",
        required=True,
        help="SSH public key file to install for Dropbear (repeatable)",
    )
    parser.add_argument(
        "--verify-tls",
        action="store_true",
        help="Verify HTTPS certificates (default: accept private CA / IP certs)",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args(argv)

    try:
        password = _load_password(args.password_file)
        keys = _load_authorized_keys(args.authorized_key_files)
        summary = enable_dropbear(
            rpc_url=args.rpc_url,
            ubus_url=args.ubus_url,
            password=password,
            authorized_keys=keys,
            verify_tls=args.verify_tls,
            timeout=args.timeout,
        )
    except (RpcError, OSError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
