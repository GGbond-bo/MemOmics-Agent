"""Execution-boundary tests for V5 password-only SCP transfers.

The suite is deliberately offline: it replaces the native executable with a
small ``subprocess.run`` spy and never reads the Windows credential vault.
"""
from __future__ import annotations

from types import SimpleNamespace

from memomics.bio_tools import remote_cluster as rc
from memomics.bio_tools import password_ssh


def test_released_askpass_helper_is_present_and_hash_bound():
    """A V5 launch cannot silently use a substituted helper executable."""
    helper = password_ssh.askpass_helper_path()
    assert helper.is_file()
    assert password_ssh._sha256_file(helper) == password_ssh.ASKPASS_HELPER_SHA256
    assert password_ssh.verify_askpass_helper() == helper


def test_v5_scp_sftp_fallback_rebuilds_bounded_askpass_runtime(monkeypatch):
    """The legacy ``-O`` retry must not inherit a stale SFTP password map."""
    process_calls = []

    class V5Connection:
        catalog_v5_ssh_route = rc.CATALOG_V5_SSH_ROUTE_MARKER
        user = "alice"
        timeout = 1

        def __init__(self):
            self.runtime_requests = 0

        def _v5_scp_base(self):
            self.runtime_requests += 1
            number = self.runtime_requests
            return (
                ["C:/Windows/System32/OpenSSH/scp.exe", "-F", "C:/controlled/%d.conf" % number],
                SimpleNamespace(target_alias="memomics-v5-target-%032d" % number,
                                env={"MEMOMICS_V5_RUNTIME": str(number)}),
            )

    conn = V5Connection()

    def fake_run(argv, **kwargs):
        process_calls.append((list(argv), dict(kwargs.get("env") or {})))
        if len(process_calls) == 1:
            return SimpleNamespace(returncode=255, stdout="", stderr="sftp subsystem unavailable")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(rc.subprocess, "run", fake_run)

    result = rc._scp_transfer(conn, "local.txt", "/remote/file.txt", upload=True)

    assert result == {"ok": True, "cmd_mode": "legacy"}
    assert conn.runtime_requests == 2
    assert process_calls[0][1]["MEMOMICS_V5_RUNTIME"] == "1"
    assert process_calls[1][1]["MEMOMICS_V5_RUNTIME"] == "2"
    assert "-O" not in process_calls[0][0]
    assert "-O" in process_calls[1][0]
    assert process_calls[0][0][-1].startswith("alice@memomics-v5-target-")
    assert process_calls[1][0][-1].startswith("alice@memomics-v5-target-")
    assert process_calls[0][0][-1] != process_calls[1][0][-1]
