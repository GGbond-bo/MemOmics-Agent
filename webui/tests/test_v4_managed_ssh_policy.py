"""Offline execution-boundary checks for V4 managed OpenSSH route configs."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from memomics.bio_tools import cluster_kernel as kernel
from memomics.bio_tools import cluster_session as session
from memomics.bio_tools import node_state as state
from memomics.bio_tools import remote_cluster as rc


def _keypair(tmp_path: Path) -> Path:
    key = tmp_path / "explicit-key"
    key.write_text("not-read-by-these-tests", encoding="utf-8")
    key.with_suffix(".pub").write_text("ssh-ed25519 AAAATEST memomics", encoding="utf-8")
    return key


def _candidate(key: Path, *, host="target.example", gateway=None):
    value = {
        "host": host, "user": "alice", "port": 2202, "key_path": str(key),
        "workdir": "/work", "job_dir": "/work/jobs", "timeout": 30,
        "scheduler": "auto", "partition": "", "queue": "",
    }
    if gateway:
        value["gateway"] = gateway
    return value


def _managed_options(monkeypatch, tmp_path, *, gateway=False):
    key = _keypair(tmp_path)
    monkeypatch.setattr(rc, "_get_config_path", lambda: tmp_path / "config.yaml")
    # This suite validates argv/proof behavior, not host ACL APIs.  Dedicated
    # ACL tests exercise the checker with stubs; no real key body is opened.
    monkeypatch.setattr(rc, "_catalog_harden_managed_path", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rc, "_catalog_verify_managed_path", lambda *_args, **_kwargs: None)
    candidate = _candidate(key)
    if gateway:
        candidate["gateway"] = {
            "host": "gateway.example", "user": "gate", "port": 2201, "key_path": str(key),
        }
    prepared, failure = rc.prepare_catalog_connection(candidate, require_public_key=False)
    assert failure is None
    # A real catalog match writes this pin before emitting any durable V4
    # route.  The argv suite bypasses Paramiko/network, so materialize the same
    # non-empty regular file explicitly.
    Path(prepared["known_hosts_path"]).write_text(
        "target.example ssh-ed25519 AAAATESTPIN\\n", encoding="utf-8",
    )
    return key, prepared, rc.catalog_ssh_policy_options(prepared)


def test_managed_f_is_first_and_shared_by_remote_kernel_and_node_state(monkeypatch, tmp_path):
    key, prepared, options = _managed_options(monkeypatch, tmp_path, gateway=True)
    assert options[0] == "-F"
    config = Path(options[1])
    assert config.parent.name == ".memomics-catalog-v4"
    assert config.name[:-5] == __import__("hashlib").sha256(config.read_bytes()).hexdigest()

    _prefix, _remaining, digest = rc.validate_catalog_ssh_policy(
        options, host=prepared["host"], user=prepared["user"], port=prepared["port"],
        key=prepared["key"], gateway=prepared.get("gateway"), require_managed=True,
    )
    assert digest == config.stem
    kernel_argv = kernel._ssh_cmd(prepared["host"], prepared["user"], prepared["port"], prepared["key"], options,
                                  catalog_v4_route=True)
    state_argv = state._ssh_prefix(prepared["host"], prepared["user"], prepared["port"], prepared["key"], options,
                                   catalog_v4_route=True)
    assert kernel_argv[:3] == ["ssh", "-F", str(config).replace("\\", "/")]
    assert state_argv[:3] == ["ssh", "-F", str(config).replace("\\", "/")]
    assert "StrictHostKeyChecking=accept-new" not in kernel_argv
    assert "StrictHostKeyChecking=accept-new" not in state_argv


def test_tampered_managed_f_fails_closed_but_legacy_options_stay_unchanged(monkeypatch, tmp_path):
    key, prepared, options = _managed_options(monkeypatch, tmp_path)
    config = Path(options[1])
    config.write_text("Host target.example\n    StrictHostKeyChecking no\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        kernel._ssh_cmd(prepared["host"], prepared["user"], prepared["port"], prepared["key"], options)
    with pytest.raises(RuntimeError):
        state._ssh_prefix(prepared["host"], prepared["user"], prepared["port"], prepared["key"], options)

    legacy = ["-J", "legacy-bastion"]
    assert kernel._ssh_cmd("legacy.example", "alice", 22, str(key), legacy)[-3:] == ["-J", "legacy-bastion", "alice@legacy.example"]
    assert state._ssh_prefix("legacy.example", "alice", 22, str(key), legacy)[-3:] == ["-J", "legacy-bastion", "alice@legacy.example"]


def test_v4_provenance_marker_rejects_a_renamed_route_moved_outside_its_store(monkeypatch, tmp_path):
    """A V4 profile/job snapshot cannot silently become legacy ``-F`` input."""
    key, prepared, options = _managed_options(monkeypatch, tmp_path)
    config = Path(options[1])
    moved = tmp_path / "outside" / "evil.conf"
    moved.parent.mkdir()
    config.replace(moved)

    # The content itself remains untouched, but its durable V4 provenance
    # requires the protected store plus the original content-addressed proof.
    moved_options = ["-F", str(moved)]
    with pytest.raises(RuntimeError):
        rc.validate_catalog_ssh_policy(
            moved_options, host=prepared["host"], user=prepared["user"], port=prepared["port"],
            key=prepared["key"], require_managed=True,
        )
    with pytest.raises(RuntimeError):
        kernel._ssh_cmd(prepared["host"], prepared["user"], prepared["port"], prepared["key"],
                        moved_options, catalog_v4_route=True)
    with pytest.raises(RuntimeError):
        state._ssh_prefix(prepared["host"], prepared["user"], prepared["port"], prepared["key"],
                          moved_options, catalog_v4_route=True)
    with pytest.raises(RuntimeError):
        rc.validate_catalog_ssh_policy(
            [], host=prepared["host"], user=prepared["user"], port=prepared["port"],
            key=prepared["key"], require_managed=True,
        )

    # A non-V4 profile retains its documented, user-owned legacy -F behavior.
    legacy = tmp_path / "legacy.conf"
    legacy.write_text("Host legacy.example\n", encoding="utf-8")
    argv = kernel._ssh_cmd("legacy.example", "alice", 22, str(key), ["-F", str(legacy)])
    assert ["-F", str(legacy)] == argv[-3:-1]


def test_v4_route_provenance_survives_job_and_r_session_snapshot_reentry(monkeypatch):
    marker = rc.CATALOG_V4_SSH_ROUTE_MARKER
    snapshot = rc._connection_snapshot({
        "host": "target.example", "user": "alice", "port": 2202, "key": "C:/managed/key",
        "workdir": "/work", "job_dir": "/work/jobs", "extra_ssh_options": ["-F", "route.conf"],
        "catalog_v4_ssh_route": marker,
    })
    assert snapshot["catalog_v4_ssh_route"] == marker
    assert rc._apply_connection_snapshot({}, snapshot)["catalog_v4_ssh_route"] == marker
    assert state._connection_for_record(snapshot)["catalog_v4_route"] is True
    assert kernel._target_from_job_record(snapshot, {})["catalog_v4_route"] is True

    # cluster_session itself uses the shared snapshot helpers rather than a
    # narrower field whitelist, so a daemon reconnect inherits the same proof.
    monkeypatch.setattr(session, "_node_for", lambda *_args: ({}, "", None))
    restored, _name, error = session._snapshot_node_for_record(
        {}, {**snapshot, "node": "saved-v4"},
    )
    assert error is None
    assert restored["catalog_v4_ssh_route"] == marker


def test_unknown_v4_provenance_is_rejected_for_current_job_and_session_reentry(monkeypatch):
    bad = "v4-managed-route-tampered"
    current = {
        "host": "target.example", "user": "alice", "port": 2202, "key": "C:/managed/key",
        "workdir": "/work", "extra_ssh_options": [], "catalog_v4_ssh_route": bad,
    }
    # Current-profile cache lookup is an execution boundary too: an unknown
    # non-empty marker cannot become a legacy profile just because it lacks a
    # valid managed config yet.
    with pytest.raises(RuntimeError, match="provenance"):
        rc._conn_key(current)
    with pytest.raises(RuntimeError, match="provenance"):
        state._connection_for_record(current)
    with pytest.raises(RuntimeError, match="provenance"):
        kernel._target_from_job_record(current, {})

    # R-session replay overlays the same snapshot helper and therefore fails
    # before constructing a connection from a corrupted durable record.
    monkeypatch.setattr(session, "_node_for", lambda *_args: ({}, "", None))
    with pytest.raises(RuntimeError, match="provenance"):
        session._snapshot_node_for_record({}, {**current, "node": "saved-v4"})


def test_managed_route_rejects_missing_or_symlinked_known_hosts_before_argv(monkeypatch, tmp_path):
    key, prepared, options = _managed_options(monkeypatch, tmp_path)
    known_hosts = Path(prepared["known_hosts_path"])
    known_hosts.unlink()
    with pytest.raises(RuntimeError):
        kernel._ssh_cmd(prepared["host"], prepared["user"], prepared["port"], prepared["key"], options,
                        catalog_v4_route=True)

    known_hosts.write_text("target.example ssh-ed25519 AAAATESTPIN\\n", encoding="utf-8")
    backing = known_hosts.with_name("known_hosts.backing")
    known_hosts.replace(backing)
    try:
        known_hosts.symlink_to(backing.name)
    except OSError:
        pytest.skip("symlink creation is unavailable for this Windows test identity")
    with pytest.raises(RuntimeError):
        state._ssh_prefix(prepared["host"], prepared["user"], prepared["port"], prepared["key"], options,
                          catalog_v4_route=True)


def test_managed_route_rejects_known_hosts_acl_checker_failure_before_argv(monkeypatch, tmp_path):
    key, prepared, options = _managed_options(monkeypatch, tmp_path)
    checked = []

    def reject_tampered_acl(path, *, directory):
        checked.append((Path(path).name, directory))
        if Path(path).name == "known_hosts":
            raise rc._CatalogManagedStorePermissionError("unexpected ACE")

    monkeypatch.setattr(rc, "_catalog_verify_managed_path", reject_tampered_acl)
    with pytest.raises(rc._CatalogManagedStorePermissionError, match="unexpected ACE"):
        kernel._ssh_cmd(prepared["host"], prepared["user"], prepared["port"], prepared["key"], options,
                        catalog_v4_route=True)
    assert ("known_hosts", False) in checked


@pytest.mark.parametrize("tampered_artifact", ["known_hosts", "route_config"])
def test_extra_windows_managed_ace_is_rejected_by_real_execution_verifier_before_subprocess(
        monkeypatch, tmp_path, tampered_artifact):
    if rc.os.name != "nt":
        pytest.skip("Windows DACL verification is platform-specific")
    real_verify = rc._catalog_verify_managed_path
    key, prepared, options = _managed_options(monkeypatch, tmp_path)
    # Restore the real verification-only wrapper.  Stub only the native DACL
    # reader/identity lookup, so this exercises the same path used by argv
    # construction rather than a mocked permission callback.
    monkeypatch.setattr(rc, "_catalog_verify_managed_path", real_verify)
    monkeypatch.setattr(rc, "_catalog_windows_current_sid", lambda: "S-1-5-21-42")
    directory_good = "D:P(A;OICI;FA;;;S-1-5-21-42)(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
    file_good = "D:P(A;;FA;;;S-1-5-21-42)(A;;FA;;;SY)(A;;FA;;;BA)"
    bad = file_good + "(A;;FA;;;WD)"
    route_name = Path(options[1]).name

    def sddl(path):
        clean = directory_good if Path(path).is_dir() else file_good
        artifact_name = Path(path).name
        if artifact_name == ("known_hosts" if tampered_artifact == "known_hosts" else route_name):
            return bad
        return clean

    monkeypatch.setattr(
        rc, "_catalog_windows_sddl",
        sddl,
    )
    subprocess_calls = []
    monkeypatch.setattr(state.subprocess, "run", lambda *_a, **_k: subprocess_calls.append(True))

    result = state.probe(prepared["host"], prepared["user"], prepared["port"], prepared["key"], options,
                         catalog_v4_route=True)
    assert result["ok"] is False
    assert subprocess_calls == []


def test_managed_app_identity_is_revalidated_for_target_and_gateway(monkeypatch, tmp_path):
    if rc.os.name != "nt":
        pytest.skip("Windows DACL verification is platform-specific")
    real_verify = rc._catalog_verify_managed_path
    key, prepared, _options = _managed_options(monkeypatch, tmp_path, gateway=True)
    root = Path(prepared["known_hosts_path"]).parent
    managed_key = root / "id_ed25519"
    managed_key.write_text("private-key-placeholder", encoding="utf-8")
    managed_key.with_suffix(".pub").write_text("ssh-ed25519 AAAATESTPIN\\n", encoding="utf-8")
    prepared["key"] = str(managed_key)
    prepared["gateway"]["key"] = str(managed_key)
    # `_managed_options` temporarily disables verification to construct an
    # offline route.  Regenerate its route, then restore the actual verifier.
    options = rc.catalog_ssh_policy_options(prepared)
    monkeypatch.setattr(rc, "_catalog_verify_managed_path", real_verify)
    monkeypatch.setattr(rc, "_catalog_windows_current_sid", lambda: "S-1-5-21-42")
    directory_good = "D:P(A;OICI;FA;;;S-1-5-21-42)(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
    file_good = "D:P(A;;FA;;;S-1-5-21-42)(A;;FA;;;SY)(A;;FA;;;BA)"
    seen = []
    monkeypatch.setattr(
        rc, "_catalog_windows_sddl",
        lambda path: seen.append(Path(path).name) or (directory_good if Path(path).is_dir() else file_good),
    )

    rc.validate_catalog_ssh_policy(
        options, host=prepared["host"], user=prepared["user"], port=prepared["port"],
        key=prepared["key"], gateway=prepared["gateway"], require_managed=True,
    )
    assert seen.count("id_ed25519") == 2

    subprocess_calls = []
    monkeypatch.setattr(state.subprocess, "run", lambda *_a, **_k: subprocess_calls.append(True))
    monkeypatch.setattr(
        rc, "_catalog_windows_sddl",
        lambda path: (file_good + "(A;;FA;;;WD)") if Path(path).name == "id_ed25519"
        else (directory_good if Path(path).is_dir() else file_good),
    )
    result = state.probe(prepared["host"], prepared["user"], prepared["port"], prepared["key"], options,
                         catalog_v4_route=True)
    assert result["ok"] is False
    assert subprocess_calls == []


def test_managed_app_identity_rejects_missing_or_symlinked_key_before_argv(monkeypatch, tmp_path):
    key, prepared, _options = _managed_options(monkeypatch, tmp_path)
    root = Path(prepared["known_hosts_path"]).parent
    managed_key = root / "id_ed25519"
    managed_key.write_text("private-key-placeholder", encoding="utf-8")
    prepared["key"] = str(managed_key)
    options = rc.catalog_ssh_policy_options(prepared)

    managed_key.unlink()
    with pytest.raises(RuntimeError):
        kernel._ssh_cmd(prepared["host"], prepared["user"], prepared["port"], prepared["key"], options,
                        catalog_v4_route=True)

    managed_key.write_text("private-key-placeholder", encoding="utf-8")
    backing = root / "id_ed25519.backing"
    managed_key.replace(backing)
    try:
        managed_key.symlink_to(backing.name)
    except OSError:
        pytest.skip("symlink creation is unavailable for this Windows test identity")
    with pytest.raises(RuntimeError):
        state._ssh_prefix(prepared["host"], prepared["user"], prepared["port"], prepared["key"], options,
                          catalog_v4_route=True)


def test_queued_job_rejects_unknown_v4_marker_before_upload_run_or_state_probe(monkeypatch):
    bad_record = {
        "host": "target.example", "user": "alice", "port": 2202, "key": "C:/managed/key",
        "extra_opts": [], "workdir": "/work", "catalog_v4_ssh_route": "unknown-marker",
        "need_upload": True, "code": "print(1)", "script": "/work/job.py", "status": "queued",
    }
    subprocess_calls = []
    monkeypatch.setattr(state.subprocess, "run", lambda *_a, **_k: subprocess_calls.append(True))
    with pytest.raises(RuntimeError, match="provenance"):
        state.start_queued_job(dict(bad_record))
    assert subprocess_calls == []

    bad_running = dict(bad_record, need_upload=False)
    with pytest.raises(RuntimeError, match="provenance"):
        state.start_queued_job(bad_running)
    assert subprocess_calls == []

    monkeypatch.setattr(state, "load_jobs", lambda: {"jobs": {"bad": dict(bad_record)}})
    monkeypatch.setattr(state, "node_state", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not probe")))
    with pytest.raises(RuntimeError, match="provenance"):
        state.promote_queued()


def test_managed_f_symlink_alias_is_rejected_before_argv_build(monkeypatch, tmp_path):
    key, prepared, options = _managed_options(monkeypatch, tmp_path)
    config = Path(options[1])
    alias = config.with_name("a" * 64 + ".conf")
    try:
        alias.symlink_to(config.name)
    except OSError:
        pytest.skip("symlink creation is unavailable for this Windows test identity")
    with pytest.raises(RuntimeError):
        kernel._ssh_cmd(prepared["host"], prepared["user"], prepared["port"], prepared["key"], ["-F", str(alias)])


def test_percent_in_explicit_identity_path_is_rejected_before_config_serialization(monkeypatch, tmp_path):
    key = tmp_path / "key%h"
    key.write_text("placeholder", encoding="utf-8")
    key.with_suffix(".pub").write_text("ssh-ed25519 AAAATEST memomics", encoding="utf-8")
    monkeypatch.setattr(rc, "_get_config_path", lambda: tmp_path / "config.yaml")
    monkeypatch.setattr(rc, "_catalog_harden_managed_path", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rc, "_catalog_verify_managed_path", lambda *_args, **_kwargs: None)
    prepared, failure = rc.prepare_catalog_connection(_candidate(key), require_public_key=False)
    assert failure is None
    with pytest.raises(RuntimeError):
        rc.catalog_ssh_policy_options(prepared)


def test_ipv6_scp_uses_bracketed_remote_spec_for_both_transfer_modes(monkeypatch):
    calls = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(rc.subprocess, "run", fake_run)
    conn = SimpleNamespace(
        host="2001:db8::9", user="alice", port=2202, key_path="", timeout=1,
        use_mux=False, catalog_ssh_config_args=[], extra_options=[],
    )
    assert rc._scp_transfer(conn, "local.txt", "/remote/file.txt", upload=True)["ok"] is True
    assert calls[0][-1] == "alice@[2001:db8::9]:/remote/file.txt"
    calls.clear()
    assert rc._scp_transfer(conn, "local.txt", "/remote/file.txt", upload=False)["ok"] is True
    assert calls[0][-2] == "alice@[2001:db8::9]:/remote/file.txt"
