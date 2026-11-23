"""Unit tests for scripts/glinet_enable_dropbear.py."""

from __future__ import annotations

import hashlib
import io
import json
import ssl
import urllib.error
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def test_ssl_context_verify_modes(glinet_mod: ModuleType) -> None:
    verified = glinet_mod._ssl_context(True)
    unverified = glinet_mod._ssl_context(False)
    assert isinstance(verified, ssl.SSLContext)
    assert unverified.verify_mode == ssl.CERT_NONE
    assert unverified.check_hostname is False


def test_load_password_and_keys(glinet_mod: ModuleType, tmp_path: Path) -> None:
    password_file = tmp_path / "password"
    password_file.write_text(" secret-pass \n", encoding="utf-8")
    assert glinet_mod._load_password(password_file) == "secret-pass"

    key_a = tmp_path / "a.pub"
    key_b = tmp_path / "b.pub"
    key_a.write_text("ssh-ed25519 AAAA one\n", encoding="utf-8")
    key_b.write_text("ssh-ed25519 BBBB two\n", encoding="utf-8")
    assert glinet_mod._load_authorized_keys([key_a, key_b]) == (
        "ssh-ed25519 AAAA one\nssh-ed25519 BBBB two\n"
    )


def test_load_password_empty(glinet_mod: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "empty"
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(glinet_mod.RpcError, match="password file is empty"):
        glinet_mod._load_password(path)


def test_load_authorized_keys_empty_file(glinet_mod: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "empty.pub"
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(glinet_mod.RpcError, match="authorized key file is empty"):
        glinet_mod._load_authorized_keys([path])


def test_load_authorized_keys_requires_at_least_one(glinet_mod: ModuleType) -> None:
    with pytest.raises(glinet_mod.RpcError, match="no authorized key files"):
        glinet_mod._load_authorized_keys([])


def test_http_json_success(glinet_mod: ModuleType) -> None:
    payload = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    fake_resp = MagicMock()
    fake_resp.__enter__.return_value = io.BytesIO(json.dumps(payload).encode())
    fake_resp.__exit__.return_value = False
    with patch.object(glinet_mod.urllib.request, "urlopen", return_value=fake_resp) as urlopen:
        body = glinet_mod._http_json(
            "https://192.168.0.247/rpc",
            {"jsonrpc": "2.0", "id": 1, "method": "challenge", "params": {}},
            context=glinet_mod._ssl_context(False),
            timeout=5,
        )
    assert body == payload
    assert urlopen.called


def test_http_json_http_error(glinet_mod: ModuleType) -> None:
    err = urllib.error.HTTPError(
        "https://example/rpc",
        403,
        "Forbidden",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(b"denied"),
    )
    with patch.object(glinet_mod.urllib.request, "urlopen", side_effect=err):
        with pytest.raises(glinet_mod.RpcError, match="HTTP 403"):
            glinet_mod._http_json(
                "https://example/rpc",
                {"jsonrpc": "2.0", "id": 1, "method": "challenge", "params": {}},
                context=glinet_mod._ssl_context(False),
                timeout=5,
            )


def test_http_json_url_error(glinet_mod: ModuleType) -> None:
    with patch.object(
        glinet_mod.urllib.request,
        "urlopen",
        side_effect=urllib.error.URLError("timed out"),
    ):
        with pytest.raises(glinet_mod.RpcError, match="request failed"):
            glinet_mod._http_json(
                "https://example/rpc",
                {"jsonrpc": "2.0", "id": 1, "method": "challenge", "params": {}},
                context=glinet_mod._ssl_context(False),
                timeout=5,
            )


def test_http_json_non_object(glinet_mod: ModuleType) -> None:
    fake_resp = MagicMock()
    fake_resp.__enter__.return_value = io.BytesIO(b"[1,2,3]")
    fake_resp.__exit__.return_value = False
    with patch.object(glinet_mod.urllib.request, "urlopen", return_value=fake_resp):
        with pytest.raises(glinet_mod.RpcError, match="non-object JSON"):
            glinet_mod._http_json(
                "https://example/rpc",
                {"jsonrpc": "2.0", "id": 1, "method": "challenge", "params": {}},
                context=glinet_mod._ssl_context(False),
                timeout=5,
            )


def test_glinet_login_success(glinet_mod: ModuleType) -> None:
    challenge = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"alg": 5, "salt": "abcSalt", "nonce": "nonce123"},
    }
    login = {"jsonrpc": "2.0", "id": 2, "result": {"sid": "session-token"}}
    openssl = SimpleNamespace(returncode=0, stdout=b"$5$abcSalt$crypt\n", stderr=b"")

    with (
        patch.object(glinet_mod, "_http_json", side_effect=[challenge, login]) as http_json,
        patch.object(glinet_mod.subprocess, "run", return_value=openssl) as run,
    ):
        sid = glinet_mod.glinet_login(
            "https://192.168.0.247/rpc",
            "pw",
            context=glinet_mod._ssl_context(False),
            timeout=5,
        )

    assert sid == "session-token"
    expected_hash = hashlib.sha256(b"root:$5$abcSalt$crypt:nonce123").hexdigest()
    assert http_json.call_args_list[1].args[1]["params"]["hash"] == expected_hash
    assert run.call_args.args[0][:3] == ["openssl", "passwd", "-5"]


def test_glinet_login_bad_challenge(glinet_mod: ModuleType) -> None:
    with patch.object(glinet_mod, "_http_json", return_value={"result": {"alg": "x"}}):
        with pytest.raises(glinet_mod.RpcError, match="unexpected challenge"):
            glinet_mod.glinet_login(
                "https://example/rpc",
                "pw",
                context=glinet_mod._ssl_context(False),
                timeout=5,
            )


def test_glinet_login_unsupported_alg(glinet_mod: ModuleType) -> None:
    with patch.object(
        glinet_mod,
        "_http_json",
        return_value={"result": {"alg": 9, "salt": "s", "nonce": "n"}},
    ):
        with pytest.raises(glinet_mod.RpcError, match="unsupported challenge.alg"):
            glinet_mod.glinet_login(
                "https://example/rpc",
                "pw",
                context=glinet_mod._ssl_context(False),
                timeout=5,
            )


def test_glinet_login_openssl_failure(glinet_mod: ModuleType) -> None:
    challenge = {"result": {"alg": 5, "salt": "s", "nonce": "n"}}
    openssl = SimpleNamespace(returncode=1, stdout=b"", stderr=b"bad salt")
    with (
        patch.object(glinet_mod, "_http_json", return_value=challenge),
        patch.object(glinet_mod.subprocess, "run", return_value=openssl),
    ):
        with pytest.raises(glinet_mod.RpcError, match="openssl passwd failed"):
            glinet_mod.glinet_login(
                "https://example/rpc",
                "pw",
                context=glinet_mod._ssl_context(False),
                timeout=5,
            )


def test_glinet_login_missing_sid(glinet_mod: ModuleType) -> None:
    challenge = {"result": {"alg": 5, "salt": "s", "nonce": "n"}}
    openssl = SimpleNamespace(returncode=0, stdout=b"$5$s$x\n", stderr=b"")
    with (
        patch.object(glinet_mod, "_http_json", side_effect=[challenge, {"result": {}}]),
        patch.object(glinet_mod.subprocess, "run", return_value=openssl),
    ):
        with pytest.raises(glinet_mod.RpcError, match="login failed"):
            glinet_mod.glinet_login(
                "https://example/rpc",
                "pw",
                context=glinet_mod._ssl_context(False),
                timeout=5,
            )


def test_glinet_call_success(glinet_mod: ModuleType) -> None:
    with patch.object(
        glinet_mod,
        "_http_json",
        return_value={"result": {"ssh_enabled": False}},
    ):
        result = glinet_mod.glinet_call(
            "https://example/rpc",
            "sid",
            "local-access",
            "get_config",
            None,
            context=glinet_mod._ssl_context(False),
            timeout=5,
            req_id=3,
        )
    assert result == {"ssh_enabled": False}


def test_glinet_call_error(glinet_mod: ModuleType) -> None:
    with patch.object(
        glinet_mod,
        "_http_json",
        return_value={"error": {"code": -32601, "message": "Method not found"}},
    ):
        with pytest.raises(glinet_mod.RpcError, match="local-access.get_config error"):
            glinet_mod.glinet_call(
                "https://example/rpc",
                "sid",
                "local-access",
                "get_config",
                {},
                context=glinet_mod._ssl_context(False),
                timeout=5,
                req_id=3,
            )


def test_luci_login_and_call(glinet_mod: ModuleType) -> None:
    login_body = {
        "result": [0, {"ubus_rpc_session": "ubus-sid"}],
    }
    call_body = {"result": [0, {"data": "ssh-ed25519 AAAA\n"}]}
    with patch.object(glinet_mod, "_http_json", side_effect=[login_body, call_body]):
        sid = glinet_mod.luci_login(
            "https://192.168.0.247:8443/ubus",
            "pw",
            context=glinet_mod._ssl_context(False),
            timeout=5,
        )
        data = glinet_mod.luci_call(
            "https://192.168.0.247:8443/ubus",
            sid,
            "file",
            "read",
            {"path": "/etc/dropbear/authorized_keys"},
            context=glinet_mod._ssl_context(False),
            timeout=5,
        )
    assert sid == "ubus-sid"
    assert data == {"data": "ssh-ed25519 AAAA\n"}


def test_luci_login_failure(glinet_mod: ModuleType) -> None:
    with patch.object(glinet_mod, "_http_json", return_value={"result": [6]}):
        with pytest.raises(glinet_mod.RpcError, match="LuCI ubus login failed"):
            glinet_mod.luci_login(
                "https://example/ubus",
                "pw",
                context=glinet_mod._ssl_context(False),
                timeout=5,
            )


def test_luci_login_missing_session(glinet_mod: ModuleType) -> None:
    with patch.object(glinet_mod, "_http_json", return_value={"result": [0, {}]}):
        with pytest.raises(glinet_mod.RpcError, match="missing session"):
            glinet_mod.luci_login(
                "https://example/ubus",
                "pw",
                context=glinet_mod._ssl_context(False),
                timeout=5,
            )


def test_luci_call_status_error(glinet_mod: ModuleType) -> None:
    with patch.object(glinet_mod, "_http_json", return_value={"result": [6]}):
        with pytest.raises(glinet_mod.RpcError, match="status 6"):
            glinet_mod.luci_call(
                "https://example/ubus",
                "sid",
                "file",
                "read",
                {"path": "/etc/dropbear/authorized_keys"},
                context=glinet_mod._ssl_context(False),
                timeout=5,
            )


def test_luci_call_rpc_error(glinet_mod: ModuleType) -> None:
    with patch.object(
        glinet_mod,
        "_http_json",
        return_value={"error": {"code": -32002, "message": "Access denied"}},
    ):
        with pytest.raises(glinet_mod.RpcError, match="ubus file.write error"):
            glinet_mod.luci_call(
                "https://example/ubus",
                "sid",
                "file",
                "write",
                {"path": "/etc/dropbear/authorized_keys", "data": "x"},
                context=glinet_mod._ssl_context(False),
                timeout=5,
            )


def test_luci_call_unexpected_result(glinet_mod: ModuleType) -> None:
    with patch.object(glinet_mod, "_http_json", return_value={"result": "nope"}):
        with pytest.raises(glinet_mod.RpcError, match="unexpected result"):
            glinet_mod.luci_call(
                "https://example/ubus",
                "sid",
                "file",
                "read",
                {},
                context=glinet_mod._ssl_context(False),
                timeout=5,
            )


def _local_access_cfg(**overrides: Any) -> dict[str, Any]:
    cfg = {
        "http_port": 80,
        "https_port": 443,
        "redirect_https": True,
        "session_timeout": 10800,
        "ssh_enabled": False,
        "ssh_port": 22,
        "luci_http_port": 8080,
        "luci_https_port": 8443,
        "luci_redirect_https": True,
    }
    cfg.update(overrides)
    return cfg


def test_enable_dropbear_enables_and_writes_keys(glinet_mod: ModuleType) -> None:
    keys = "ssh-ed25519 AAAA test\n"
    calls: list[tuple[str, str]] = []

    def glinet_call_side_effect(
        _rpc_url: str,
        _sid: str,
        module: str,
        method: str,
        params: dict[str, Any] | None,
        **_kwargs: Any,
    ) -> Any:
        calls.append((module, method))
        if method == "get_config":
            # first get disabled, second get enabled
            if calls.count(("local-access", "get_config")) == 1:
                return _local_access_cfg(ssh_enabled=False)
            return _local_access_cfg(ssh_enabled=True)
        if method == "set_config":
            assert params is not None
            assert params["ssh_enabled"] is True
            assert params["ssh_port"] == 22
            return []
        raise AssertionError(f"unexpected call {module}.{method}")

    def luci_call_side_effect(
        _ubus_url: str,
        _sid: str,
        obj: str,
        method: str,
        params: dict[str, Any] | None,
        **_kwargs: Any,
    ) -> Any:
        calls.append((obj, method))
        if method == "read":
            raise glinet_mod.RpcError("missing")
        if method == "write":
            assert params is not None
            assert params["path"] == "/etc/dropbear/authorized_keys"
            assert params["data"] == keys
            assert params["mode"] == 0o600
            return None
        raise AssertionError(f"unexpected ubus {obj}.{method}")

    with (
        patch.object(glinet_mod, "glinet_login", return_value="gl-sid"),
        patch.object(glinet_mod, "glinet_call", side_effect=glinet_call_side_effect),
        patch.object(glinet_mod, "luci_login", return_value="ubus-sid"),
        patch.object(glinet_mod, "luci_call", side_effect=luci_call_side_effect),
    ):
        summary = glinet_mod.enable_dropbear(
            rpc_url="https://192.168.0.247/rpc",
            ubus_url="https://192.168.0.247:8443/ubus",
            password="pw",
            authorized_keys=keys,
            verify_tls=False,
            timeout=5,
        )

    assert summary["dropbear_enable_changed"] is True
    assert summary["authorized_keys_changed"] is True
    assert summary["ssh_enabled_before"] is False
    assert summary["ssh_enabled_after"] is True
    assert ("local-access", "set_config") in calls
    assert ("file", "write") in calls


def test_enable_dropbear_skips_when_already_configured(glinet_mod: ModuleType) -> None:
    keys = "ssh-ed25519 AAAA test\n"
    set_config_calls = 0
    write_calls = 0

    def glinet_call_side_effect(
        *_args: Any,
        **kwargs: Any,
    ) -> Any:
        nonlocal set_config_calls
        method = kwargs.get("method")
        # signature uses positional method
        method = _args[3] if len(_args) >= 4 else method
        if method == "get_config":
            return _local_access_cfg(ssh_enabled=True)
        if method == "set_config":
            set_config_calls += 1
            return []
        raise AssertionError(method)

    def luci_call_side_effect(
        *_args: Any,
        **_kwargs: Any,
    ) -> Any:
        nonlocal write_calls
        method = _args[3]
        if method == "read":
            return {"data": keys}
        if method == "write":
            write_calls += 1
            return None
        raise AssertionError(method)

    with (
        patch.object(glinet_mod, "glinet_login", return_value="gl-sid"),
        patch.object(glinet_mod, "glinet_call", side_effect=glinet_call_side_effect),
        patch.object(glinet_mod, "luci_login", return_value="ubus-sid"),
        patch.object(glinet_mod, "luci_call", side_effect=luci_call_side_effect),
    ):
        summary = glinet_mod.enable_dropbear(
            rpc_url="https://192.168.0.247/rpc",
            ubus_url="https://192.168.0.247:8443/ubus",
            password="pw",
            authorized_keys=keys,
            verify_tls=False,
            timeout=5,
        )

    assert summary["dropbear_enable_changed"] is False
    assert summary["authorized_keys_changed"] is False
    assert set_config_calls == 0
    assert write_calls == 0


def test_enable_dropbear_rejects_non_dict_config(glinet_mod: ModuleType) -> None:
    with (
        patch.object(glinet_mod, "glinet_login", return_value="gl-sid"),
        patch.object(glinet_mod, "glinet_call", return_value=["nope"]),
    ):
        with pytest.raises(glinet_mod.RpcError, match="get_config unexpected"):
            glinet_mod.enable_dropbear(
                rpc_url="https://example/rpc",
                ubus_url="https://example/ubus",
                password="pw",
                authorized_keys="ssh-ed25519 AAAA\n",
                verify_tls=False,
                timeout=5,
            )


def test_enable_dropbear_writes_when_read_returns_non_dict(glinet_mod: ModuleType) -> None:
    keys = "ssh-ed25519 AAAA test\n"
    writes = 0

    def glinet_call_side_effect(*_args: Any, **_kwargs: Any) -> Any:
        method = _args[3]
        if method == "get_config":
            return _local_access_cfg(ssh_enabled=True)
        raise AssertionError(method)

    def luci_call_side_effect(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal writes
        method = _args[3]
        if method == "read":
            return None
        if method == "write":
            writes += 1
            return None
        raise AssertionError(method)

    with (
        patch.object(glinet_mod, "glinet_login", return_value="gl-sid"),
        patch.object(glinet_mod, "glinet_call", side_effect=glinet_call_side_effect),
        patch.object(glinet_mod, "luci_login", return_value="ubus-sid"),
        patch.object(glinet_mod, "luci_call", side_effect=luci_call_side_effect),
    ):
        summary = glinet_mod.enable_dropbear(
            rpc_url="https://example/rpc",
            ubus_url="https://example/ubus",
            password="pw",
            authorized_keys=keys,
            verify_tls=True,
            timeout=5,
        )

    assert summary["authorized_keys_changed"] is True
    assert writes == 1


def test_main_success(glinet_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    password_file = tmp_path / "password"
    key_file = tmp_path / "id_ed25519.pub"
    password_file.write_text("pw\n", encoding="utf-8")
    key_file.write_text("ssh-ed25519 AAAA\n", encoding="utf-8")
    summary = {
        "authorized_keys_changed": False,
        "authorized_keys_path": "/etc/dropbear/authorized_keys",
        "dropbear_enable_changed": True,
        "ssh_enabled_after": True,
        "ssh_enabled_before": False,
    }
    with patch.object(glinet_mod, "enable_dropbear", return_value=summary):
        rc = glinet_mod.main(
            [
                "--rpc-url",
                "https://192.168.0.247/rpc",
                "--ubus-url",
                "https://192.168.0.247:8443/ubus",
                "--password-file",
                str(password_file),
                "--authorized-key-file",
                str(key_file),
            ]
        )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dropbear_enable_changed"] is True


def test_main_failure(glinet_mod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    password_file = tmp_path / "password"
    key_file = tmp_path / "id_ed25519.pub"
    password_file.write_text("pw\n", encoding="utf-8")
    key_file.write_text("ssh-ed25519 AAAA\n", encoding="utf-8")
    with patch.object(glinet_mod, "enable_dropbear", side_effect=glinet_mod.RpcError("boom")):
        rc = glinet_mod.main(
            [
                "--rpc-url",
                "https://192.168.0.247/rpc",
                "--ubus-url",
                "https://192.168.0.247:8443/ubus",
                "--password-file",
                str(password_file),
                "--authorized-key-file",
                str(key_file),
            ]
        )
    assert rc == 1
    assert "error: boom" in capsys.readouterr().err
