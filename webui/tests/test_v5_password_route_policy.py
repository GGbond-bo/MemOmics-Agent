"""Offline security and propagation checks for the V5 password SSH route."""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from memomics.cluster_credentials import MemoryCredentialStore
from memomics.bio_tools import cluster_kernel as kernel
from memomics.bio_tools import node_state
from memomics.bio_tools import password_ssh
from memomics.bio_tools import remote_cluster as rc
from memomics.bio_tools import askpass_security


TARGET_ACCOUNT = "account-0123456789ab"
GATEWAY_ACCOUNT = "account-fedcba987654"


def _profile(*, gateway: bool = False) -> dict:
    profile = {
        "host": "target.example", "user": "alice", "port": 2202, "key": "",
        "workdir": "/work", "job_dir": "/work/jobs", "timeout": 30,
        "scheduler": "auto", "partition": "", "queue": "",
        "auth_mode": rc.CATALOG_V5_PASSWORD_AUTH_MODE,
        "catalog_account_id": TARGET_ACCOUNT,
        "catalog_v5_ssh_route": rc.CATALOG_V5_SSH_ROUTE_MARKER,
        "catalog_v5_target_alias": "memomics-v5-target-" + "a" * 32,
        "catalog_v5_gateway_alias": "",
        "extra_ssh_options": ["-F", "C:/controlled/route.conf"],
    }
    if gateway:
        profile.update({
            "gateway_account_id": GATEWAY_ACCOUNT,
            "catalog_v5_gateway_alias": "memomics-v5-gateway-" + "a" * 32,
            "catalog_v5_gateway_host": "gateway.example",
            "catalog_v5_gateway_user": "gate",
            "catalog_v5_gateway_port": 2201,
        })
    return profile


def _decode_map(value: str) -> list[tuple[str, str]]:
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    count = raw[0]
    offset = 1
    out = []
    for _ in range(count):
        values = []
        for _part in range(2):
            size = int.from_bytes(raw[offset:offset + 2], "little")
            offset += 2
            values.append(raw[offset:offset + size].decode("utf-8"))
            offset += size
        out.append((values[0], values[1]))
    assert offset == len(raw)
    return out


def test_password_runtime_requires_an_explicit_staged_helper():
    """A new product call cannot silently execute the install-tree sibling."""
    with pytest.raises(password_ssh.PasswordSSHError, match="password_helper_unavailable"):
        password_ssh.build_password_runtime(
            MemoryCredentialStore(), target_account_id=TARGET_ACCOUNT, target_user="alice",
            target_alias="memomics-v5-target-" + "a" * 32,
        )


def test_askpass_staging_is_content_addressed_and_never_repairs_a_bad_target(tmp_path):
    """Exercise staging without SSH, Credential Manager, or a real user home."""
    root = tmp_path / "managed"
    root.mkdir()
    source = tmp_path / "released-helper.exe"
    source.write_bytes(b"reviewed helper bytes\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    calls = []

    def harden(path, *, directory):
        calls.append(("harden", Path(path), directory))
        assert directory is False and Path(path).is_file()

    def verify(path, *, directory):
        calls.append(("verify", Path(path), directory))
        assert Path(path).is_dir() if directory else Path(path).is_file()

    staged = askpass_security.stage_verified_askpass_helper(
        root, source_path=source, expected_sha256=digest,
        harden_managed_path=harden, verify_managed_path=verify,
    )
    assert staged.parent == root
    assert staged.name == "askpass_helper-" + digest + ".exe"
    assert staged.read_bytes() == source.read_bytes()
    # The temporary is hardened before its no-replace hard-link publication;
    # the staged name is the same secured file object.
    assert any(kind == "harden" and path.parent == root and not directory
               for kind, path, directory in calls)
    assert not list(root.glob(".memomics-v5-askpass-*.tmp"))

    calls.clear()
    assert askpass_security.stage_verified_askpass_helper(
        root, source_path=source, expected_sha256=digest,
        harden_managed_path=harden, verify_managed_path=verify,
    ) == staged
    assert not any(kind == "harden" for kind, _path, _directory in calls)

    # An existing target with a wrong hash is evidence of tampering.  Do not
    # overwrite it from the install tree, even though the source remains good.
    staged.write_bytes(b"tampered")
    with pytest.raises(password_ssh.PasswordSSHError, match="password_helper_unavailable"):
        askpass_security.stage_verified_askpass_helper(
            root, source_path=source, expected_sha256=digest,
            harden_managed_path=harden, verify_managed_path=verify,
        )
    assert staged.read_bytes() == b"tampered"


def test_askpass_staging_link_failure_never_leaks_temp_or_replaces_target(tmp_path, monkeypatch):
    root = tmp_path / "managed"
    root.mkdir()
    source = tmp_path / "released-helper.exe"
    source.write_bytes(b"reviewed helper bytes\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    target = root / ("askpass_helper-" + digest + ".exe")

    def harden(path, *, directory):
        assert directory is False and Path(path).is_file()

    def verify(path, *, directory):
        assert Path(path).is_dir() if directory else Path(path).is_file()

    def reject_link(_source, _target):
        raise OSError(5, "injected link failure")

    monkeypatch.setattr(askpass_security.os, "link", reject_link)
    with pytest.raises(password_ssh.PasswordSSHError, match="password_helper_unavailable"):
        askpass_security.stage_verified_askpass_helper(
            root, source_path=source, expected_sha256=digest,
            harden_managed_path=harden, verify_managed_path=verify,
        )
    assert not target.exists()
    assert not list(root.glob(".memomics-v5-askpass-*.tmp"))


@pytest.mark.skipif(rc.os.name != "nt", reason="Windows DACL staging is platform-specific")
def test_askpass_staging_uses_real_managed_store_dacl_in_isolation(tmp_path):
    """Exercise the production ACL callbacks without creating an app-home store."""
    root = tmp_path / "managed"
    root.mkdir()
    rc._catalog_harden_managed_path(root, directory=True)
    staged = askpass_security.stage_verified_askpass_helper(
        root,
        harden_managed_path=rc._catalog_harden_managed_path,
        verify_managed_path=rc._catalog_verify_managed_path,
    )
    rc._catalog_verify_managed_path(root, directory=True)
    rc._catalog_verify_managed_path(staged, directory=False)
    assert staged.read_bytes() == password_ssh.askpass_helper_path().read_bytes()


def test_password_runtime_maps_alias_prompts_to_targets_not_passwords():
    store = MemoryCredentialStore()
    store.put(TARGET_ACCOUNT, "target-secret")
    store.put(GATEWAY_ACCOUNT, "gateway-secret")
    runtime = password_ssh.build_password_runtime(
        store, target_account_id=TARGET_ACCOUNT, target_user="alice",
        target_alias="memomics-v5-target-" + "a" * 32,
        gateway_account_id=GATEWAY_ACCOUNT, gateway_user="gate",
        gateway_alias="memomics-v5-gateway-" + "a" * 32,
        helper_path=password_ssh.askpass_helper_path(),
        helper_sha256=password_ssh.ASKPASS_HELPER_SHA256,
        base_environ={"SAFE_PARENT_VALUE": "kept", "SSH_AUTH_SOCK": "inherited-agent"},
    )
    entries = _decode_map(runtime.env["MEMOMICS_ASKPASS_MAP"])
    assert len(entries) == 2
    assert {target for _prompt, target in entries} == {
        store.target_for(TARGET_ACCOUNT), store.target_for(GATEWAY_ACCOUNT),
    }
    assert all("secret" not in value for pair in entries for value in pair)
    assert runtime.revisions == {TARGET_ACCOUNT: 1, GATEWAY_ACCOUNT: 1}
    assert runtime.env["SAFE_PARENT_VALUE"] == "kept"
    assert "SSH_AUTH_SOCK" not in runtime.env


def test_target_trust_route_excludes_target_password_but_keeps_gateway_route():
    candidate = {
        "host": "target.example", "user": "alice", "port": 2202,
        "account_id": TARGET_ACCOUNT, "gateway": {
            "host": "gateway.example", "user": "gate", "port": 2201,
            "account_id": GATEWAY_ACCOUNT,
        },
    }
    _digest, rendered = rc._catalog_v5_ssh_route_config_bytes(candidate, trust_endpoint="target")
    text = rendered.decode("utf-8")
    assert "Host memomics-v5-target-" in text
    assert "    PasswordAuthentication no" in text
    assert "    PreferredAuthentications none" in text
    assert "    ProxyJump memomics-v5-gateway-" in text
    # Gateway remains the only authentication-capable hop for target TOFU.
    assert text.count("    PasswordAuthentication yes") == 1

    store = MemoryCredentialStore()
    store.put(TARGET_ACCOUNT, "target-secret")
    store.put(GATEWAY_ACCOUNT, "gateway-secret")
    runtime = password_ssh.build_password_runtime(
        store, target_account_id=TARGET_ACCOUNT, target_user="alice",
        target_alias="memomics-v5-target-" + "a" * 32,
        gateway_account_id=GATEWAY_ACCOUNT, gateway_user="gate",
        gateway_alias="memomics-v5-gateway-" + "a" * 32,
        include_target=False, include_gateway=True,
        helper_path=password_ssh.askpass_helper_path(),
        helper_sha256=password_ssh.ASKPASS_HELPER_SHA256,
    )
    entries = _decode_map(runtime.env["MEMOMICS_ASKPASS_MAP"])
    assert runtime.target_revision == 0
    assert runtime.gateway_revision == 1
    assert len(entries) == 1
    assert entries[0][1] == store.target_for(GATEWAY_ACCOUNT)


def test_normal_v5_config_disables_key_agent_and_keyboard_fallbacks_on_every_hop():
    candidate = {
        "host": "target.example", "user": "alice", "port": 2202,
        "account_id": TARGET_ACCOUNT, "gateway": {
            "host": "gateway.example", "user": "gate", "port": 2201,
            "account_id": GATEWAY_ACCOUNT,
        },
    }
    _digest, rendered = rc._catalog_v5_ssh_route_config_bytes(candidate)
    text = rendered.decode("utf-8")
    # Both the target and the ProxyJump child get their own fixed section;
    # command-line flags alone would not constrain the child process.
    for directive in (
        "    PubkeyAuthentication no",
        "    PasswordAuthentication yes",
        "    KbdInteractiveAuthentication no",
        "    PreferredAuthentications password",
        "    NumberOfPasswordPrompts 1",
        "    StrictHostKeyChecking yes",
        "    IdentityAgent none",
        "    IdentitiesOnly yes",
    ):
        assert text.count(directive) == 2


def test_cached_v5_connection_rechecks_credential_on_password_change_and_delete(monkeypatch):
    """A cached non-mux connection object cannot retain old authentication."""
    store = MemoryCredentialStore()
    store.put(TARGET_ACCOUNT, "first-secret")
    requests = []

    def fresh_runtime(_profile):
        record = store.get(TARGET_ACCOUNT)
        if record is None:
            raise password_ssh.PasswordSSHError("credential_missing")
        requests.append(record.revision)
        return ({}, ["-F", "C:/controlled/route.conf"], SimpleNamespace(
            target_alias="memomics-v5-target-" + "c" * 32,
            env={"MEMOMICS_TEST_REVISION": str(record.revision)},
        ))

    monkeypatch.setattr(rc, "catalog_v5_process_runtime", fresh_runtime)
    connection_class = rc._make_conn_class()
    connection = object.__new__(connection_class)
    connection._v5_profile = _profile()
    connection.user = "alice"

    _argv1, runtime1 = connection._v5_command()
    store.put(TARGET_ACCOUNT, "changed-secret")
    _argv2, runtime2 = connection._v5_command()
    store.delete(TARGET_ACCOUNT)
    with pytest.raises(password_ssh.PasswordSSHError, match="credential_missing"):
        connection._v5_command()

    assert requests == [1, 2]
    assert runtime1.env["MEMOMICS_TEST_REVISION"] == "1"
    assert runtime2.env["MEMOMICS_TEST_REVISION"] == "2"


def test_v5_kernel_argv_uses_fixed_ssh_and_no_key_or_interactive_fallback(monkeypatch):
    runtime = SimpleNamespace(target_alias="memomics-v5-target-" + "b" * 32,
                              env={"ASKPASS": "fresh"})
    monkeypatch.setattr(rc, "catalog_v5_process_runtime", lambda _profile: ({}, ["-F", "C:/controlled/route.conf"], runtime))
    monkeypatch.setattr(rc._password_ssh, "system_openssh_executable", lambda name: Path("C:/Windows/System32/OpenSSH") / name)

    argv, env = kernel._v5_ssh_invocation("target.example", "alice", 2202, "", [], _profile())

    assert argv[:3] == ["C:\\Windows\\System32\\OpenSSH\\ssh.exe", "-F", "C:/controlled/route.conf"]
    assert ["-o", "BatchMode=no"] == argv[3:5]
    assert "-i" not in argv
    assert not any("kbdinteractive" in item.lower() or "identityagent" in item.lower() for item in argv)
    assert argv[-1] == "alice@" + runtime.target_alias
    assert env == runtime.env


def test_v5_job_snapshot_restores_route_without_key_or_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(node_state, "_home", lambda: str(tmp_path))
    profile = _profile(gateway=True)
    record = node_state.register_job("42", catalog_v5_route=True, **profile)
    connection = node_state._connection_for_record(record)
    assert connection["catalog_v5_route"] is True
    assert connection["catalog_v5_profile"]["catalog_account_id"] == TARGET_ACCOUNT
    assert connection["catalog_v5_profile"]["gateway_account_id"] == GATEWAY_ACCOUNT
    assert connection["key"] == ""
    saved = (tmp_path / "cluster_jobs.json").read_text(encoding="utf-8")
    assert "target-secret" not in saved and "gateway-secret" not in saved
    assert "catalog_password_v5" in saved
