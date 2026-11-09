"""Password-only V5 OpenSSH launch support.

The catalog stores the password in the Windows Credential Manager, never in a
profile/YAML record or a process command line.  Win32 OpenSSH obtains it at
prompt time through the fixed ``askpass_helper.exe``.  This module only puts a
short-lived map of *prompt -> Credential Manager target* in the child process
environment; the map contains no password bytes.

Keep this module independent from :mod:`remote_cluster`: it is also used by
the kernel and job-state paths, where a config must never silently fall back
to an old key-based route after a V5 password profile has been selected.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import time
from typing import Mapping

from memomics.cluster_credentials import CredentialError, CredentialStore


PASSWORD_AUTH_MODE = "catalog_password_v5"
PASSWORD_ROUTE_MARKER = "v5-password-route-1"
_ACCOUNT_RE = re.compile(r"^account-[0-9a-f]{12}$")
_ALIAS_RE = re.compile(r"^memomics-v5-(?:target|gateway)-[0-9a-f]{32}$")
_USER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MAX_MAP_ENTRIES = 2
_HELPER_NAME = "askpass_helper.exe"

# Updated by the release build after compiling askpass_helper.cs.  Keeping the
# expected value in reviewed Python source means a replaced helper is rejected
# before any password-only OpenSSH process is launched.
ASKPASS_HELPER_SHA256 = "cc5c87a35ee092e318956f20e0ddd24ab4ec09e861491198603777748eac32cf"


class PasswordSSHError(RuntimeError):
    """A non-secret failure suitable for catalog/API translation."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PasswordSSHRuntime:
    """One short-lived process environment plus non-secret revisions."""

    env: dict[str, str]
    target_alias: str
    target_account_id: str
    target_revision: int
    gateway_alias: str = ""
    gateway_account_id: str = ""
    gateway_revision: int | None = None

    @property
    def revisions(self) -> dict[str, int]:
        result = {self.target_account_id: self.target_revision}
        if self.gateway_account_id and self.gateway_revision is not None:
            result[self.gateway_account_id] = self.gateway_revision
        return result


def password_route_required(value: object) -> bool:
    return value == PASSWORD_ROUTE_MARKER


def is_password_profile(value: Mapping[str, object] | object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return (
        value.get("auth_mode") == PASSWORD_AUTH_MODE
        and password_route_required(value.get("catalog_v5_ssh_route"))
    )


def _validate_account(value: object) -> str:
    account_id = str(value or "")
    if not _ACCOUNT_RE.fullmatch(account_id):
        raise PasswordSSHError("credential_account_invalid")
    return account_id


def _validate_alias(value: object) -> str:
    alias = str(value or "")
    if not _ALIAS_RE.fullmatch(alias):
        raise PasswordSSHError("password_route_invalid")
    return alias


def _validate_user(value: object) -> str:
    user = str(value or "")
    if not _USER_RE.fullmatch(user):
        raise PasswordSSHError("password_route_invalid")
    return user


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            return True
        return bool(getattr(info, "st_file_attributes", 0) & 0x0400)
    except OSError:
        return True


def _regular_file_under(path: Path, root: Path) -> bool:
    """Reject reparse points along the helper/System32 path chain."""
    try:
        raw_path = Path(os.path.abspath(str(path)))
        raw_root = Path(os.path.abspath(str(root)))
        current = raw_path
        while True:
            if _is_reparse_or_symlink(current):
                return False
            if current == raw_root:
                break
            parent = current.parent
            if parent == current:
                return False
            current = parent
        canonical_root = root.resolve(strict=True)
        canonical_path = path.resolve(strict=True)
        if canonical_path.parent != canonical_root or _is_reparse_or_symlink(canonical_path):
            return False
        if not stat.S_ISREG(canonical_path.lstat().st_mode):
            return False
        current = canonical_root
        # The helper sibling tree and System32/OpenSSH directory must both be
        # ordinary directories.  Walking only to the caller-provided root
        # avoids treating an unrelated installation root as trusted.
        while True:
            if _is_reparse_or_symlink(current) or not stat.S_ISDIR(current.lstat().st_mode):
                return False
            parent = current.parent
            if parent == current:
                break
            current = parent
        return True
    except OSError:
        return False


def askpass_helper_path() -> Path:
    return Path(__file__).with_name(_HELPER_NAME)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_askpass_helper(path: Path | None = None, *, expected_sha256: str | None = None) -> Path:
    """Return the fixed helper only when its local release hash still matches."""
    helper = Path(path) if path is not None else askpass_helper_path()
    wanted = expected_sha256 if expected_sha256 is not None else ASKPASS_HELPER_SHA256
    if os.name != "nt" or not re.fullmatch(r"[0-9a-f]{64}", str(wanted or "")):
        raise PasswordSSHError("password_helper_unavailable")
    try:
        if not helper.is_absolute() or not _regular_file_under(helper, helper.parent):
            raise PasswordSSHError("password_helper_unavailable")
        if _sha256_file(helper) != wanted:
            raise PasswordSSHError("password_helper_unavailable")
    except PasswordSSHError:
        raise
    except OSError as exc:
        raise PasswordSSHError("password_helper_unavailable") from exc
    return helper


def system_openssh_executable(name: str) -> Path:
    """Find the OS-owned Win32 OpenSSH client without trusting PATH/env."""
    if os.name != "nt" or name not in {"ssh.exe", "scp.exe"}:
        raise PasswordSSHError("password_ssh_unavailable")
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
        if not length or length >= len(buffer):
            raise OSError("GetSystemDirectoryW failed")
        system_dir = Path(buffer.value)
        executable = system_dir / "OpenSSH" / name
        # The executable must be the regular file in the fixed System32 tree,
        # not a junction/symlink supplied through PATH or WINDIR.
        openssh_dir = system_dir / "OpenSSH"
        if (not system_dir.is_dir() or _is_reparse_or_symlink(system_dir)
                or not _regular_file_under(executable, openssh_dir)):
            raise OSError("OpenSSH executable is unavailable")
        return executable
    except Exception as exc:
        raise PasswordSSHError("password_ssh_unavailable") from exc


def _encode_prompt_map(entries: list[tuple[str, str]]) -> str:
    if not 1 <= len(entries) <= _MAX_MAP_ENTRIES:
        raise PasswordSSHError("password_route_invalid")
    raw = bytearray([len(entries)])
    seen: set[str] = set()
    try:
        for prompt, target in entries:
            if not isinstance(prompt, str) or not prompt or prompt in seen:
                raise PasswordSSHError("password_route_invalid")
            seen.add(prompt)
            for text in (prompt, target):
                encoded = text.encode("utf-8", "strict")
                if not 1 <= len(encoded) <= 4096:
                    raise PasswordSSHError("password_route_invalid")
                raw.extend(len(encoded).to_bytes(2, "little"))
                raw.extend(encoded)
        return base64.urlsafe_b64encode(bytes(raw)).decode("ascii").rstrip("=")
    finally:
        for index in range(len(raw)):
            raw[index] = 0


def _prompt(user: str, alias: str) -> str:
    return "%s@%s's password:" % (_validate_user(user), _validate_alias(alias))


def _credential_binding(store: CredentialStore, account_id: str) -> tuple[str, int]:
    try:
        record = store.get(account_id)
    except CredentialError as exc:
        raise PasswordSSHError(exc.code) from exc
    except Exception as exc:
        raise PasswordSSHError("credential_store_unavailable") from exc
    if record is None:
        raise PasswordSSHError("credential_missing")
    try:
        revision = int(record.revision)
    except Exception as exc:
        raise PasswordSSHError("credential_store_unavailable") from exc
    if revision < 1:
        raise PasswordSSHError("credential_store_unavailable")
    # Drop the object immediately: callers need only the non-secret revision;
    # the helper later reads the actual password from Credential Manager.
    del record
    try:
        target = store.target_for(account_id)
    except CredentialError as exc:
        raise PasswordSSHError(exc.code) from exc
    except Exception as exc:
        raise PasswordSSHError("credential_store_unavailable") from exc
    return target, revision


def build_password_runtime(
    store: CredentialStore,
    *,
    target_account_id: object,
    target_user: object,
    target_alias: object,
    gateway_account_id: object = "",
    gateway_user: object = "",
    gateway_alias: object = "",
    include_target: bool = True,
    include_gateway: bool = True,
    helper_path: Path | None = None,
    helper_sha256: str | None = None,
    base_environ: Mapping[str, str] | None = None,
    now: float | None = None,
) -> PasswordSSHRuntime:
    """Create one password-only SSH_ASKPASS environment.

    ``include_target=False`` is reserved for the controlled V5 host-key TOFU
    probe.  That probe's generated SSH config disables every target auth
    method, so no target Credential Manager target is mapped or released.

    The product caller must supply a helper staged into its protected managed
    store.  Falling back to the executable beside this module would make an
    inherited, install-directory ACL part of the password-auth trust boundary.
    """
    if helper_path is None:
        raise PasswordSSHError("password_helper_unavailable")
    target_account = _validate_account(target_account_id)
    target_alias_text = _validate_alias(target_alias)
    target_user_text = _validate_user(target_user)
    gateway_account = str(gateway_account_id or "")
    gateway_alias_text = str(gateway_alias or "")
    gateway_user_text = str(gateway_user or "")
    if bool(gateway_account) != bool(gateway_alias_text) or bool(gateway_account) != bool(gateway_user_text):
        raise PasswordSSHError("password_route_invalid")
    if gateway_account:
        gateway_account = _validate_account(gateway_account)
        gateway_alias_text = _validate_alias(gateway_alias_text)
        gateway_user_text = _validate_user(gateway_user_text)
    target_binding: tuple[str, int] | None = None
    gateway_binding: tuple[str, int] | None = None
    if include_target:
        target_binding = _credential_binding(store, target_account)
    if gateway_account and include_gateway:
        gateway_binding = _credential_binding(store, gateway_account)
    if not include_target and not (gateway_account and include_gateway):
        # Direct trust probes never need askpass.  Keep this explicit rather
        # than serializing an invalid zero-entry helper map.
        entries: list[tuple[str, str]] = []
    else:
        entries = []
        if include_target:
            assert target_binding is not None
            entries.append((_prompt(target_user_text, target_alias_text), target_binding[0]))
        if gateway_account and include_gateway:
            assert gateway_binding is not None
            entries.append((_prompt(gateway_user_text, gateway_alias_text), gateway_binding[0]))

    target_revision = target_binding[1] if target_binding is not None else 0
    gateway_revision = gateway_binding[1] if gateway_binding is not None else None
    if entries:
        helper = verify_askpass_helper(helper_path, expected_sha256=helper_sha256)
        encoded_map = _encode_prompt_map(entries)
    else:
        # No auth path can consume this helper during a direct trust probe.
        # Still use the fixed helper path if it is configured so an unexpected
        # interactive prompt fails closed rather than falling back to a GUI.
        helper = verify_askpass_helper(helper_path, expected_sha256=helper_sha256)
        encoded_map = ""

    env = dict(base_environ if base_environ is not None else os.environ)
    # The generated V5 config independently disables IdentityAgent, but do
    # not carry an inherited agent socket into any password-only child process.
    for key in ("SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", "SSH_AUTH_SOCK", "DISPLAY",
                "MEMOMICS_ASKPASS_EXPIRES_UNIX", "MEMOMICS_ASKPASS_MAP"):
        env.pop(key, None)
    expires = int(time.time() if now is None else now) + 90
    env.update({
        "SSH_ASKPASS": str(helper),
        "SSH_ASKPASS_REQUIRE": "force",
        "DISPLAY": "memomics-v5",
        "MEMOMICS_ASKPASS_EXPIRES_UNIX": str(expires),
        "MEMOMICS_ASKPASS_MAP": encoded_map,
    })
    return PasswordSSHRuntime(
        env=env, target_alias=target_alias_text, target_account_id=target_account,
        target_revision=target_revision, gateway_alias=gateway_alias_text,
        gateway_account_id=gateway_account, gateway_revision=gateway_revision,
    )


__all__ = [
    "ASKPASS_HELPER_SHA256", "PASSWORD_AUTH_MODE", "PASSWORD_ROUTE_MARKER", "PasswordSSHError",
    "PasswordSSHRuntime", "askpass_helper_path", "build_password_runtime", "is_password_profile",
    "password_route_required", "system_openssh_executable", "verify_askpass_helper",
]
