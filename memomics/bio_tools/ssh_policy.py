"""Shared verifier for app-owned V4 OpenSSH ``-F`` route configs.

The catalog writes these configs under one protected MemOmics-home directory.
Every independent SSH entry point calls this module before using a stored
snapshot so a replaced config cannot silently retarget a job, kernel, or poll.
Legacy SSH option lists without a managed ``-F`` continue through their old
paths unchanged.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path


class ManagedSSHPolicyError(RuntimeError):
    """A V4 managed SSH route cannot prove its integrity or target pin."""


_CONFIG_NAME_RE = re.compile(r"^[0-9a-f]{64}\.conf$")
_GATEWAY_ALIAS_RE = re.compile(r"^memomics-v4-gateway-[0-9a-f]{32}$")
_DIRECTIVES = {
    "HostName", "User", "Port", "BatchMode", "StrictHostKeyChecking",
    "UserKnownHostsFile", "IdentitiesOnly", "IdentityFile", "ProxyJump",
}


def _normal_path(value) -> str:
    return os.path.abspath(str(value or "")).replace("\\", "/")


def _quoted(value) -> str:
    text = str(value or "").replace("\\", "/")
    if "\x00" in text or "\n" in text or "\r" in text or "%" in text:
        raise ManagedSSHPolicyError("managed SSH policy contains an unsafe value")
    return '"%s"' % text.replace('"', '\\"')


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        return bool(getattr(path.stat(), "st_file_attributes", 0) & 0x0400)
    except OSError:
        return True


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(os.path.normpath(str(right)))


def _read_sections(data: bytes) -> dict[str, dict[str, str]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ManagedSSHPolicyError("managed SSH config is not UTF-8") from exc
    if not text.endswith("\n") or "\r" in text:
        raise ManagedSSHPolicyError("managed SSH config layout is invalid")
    sections: dict[str, dict[str, str]] = {}
    current = None
    for line in text.splitlines():
        if not line:
            continue
        if line.startswith("Host "):
            alias = line[5:]
            if not alias or alias in sections or any(ch.isspace() for ch in alias):
                raise ManagedSSHPolicyError("managed SSH config host section is invalid")
            sections[alias] = {}
            current = sections[alias]
            continue
        if current is None or not line.startswith("    ") or line.startswith("     "):
            raise ManagedSSHPolicyError("managed SSH config layout is invalid")
        try:
            key, value = line.strip().split(" ", 1)
        except ValueError as exc:
            raise ManagedSSHPolicyError("managed SSH config directive is invalid") from exc
        if key not in _DIRECTIVES or not value or key in current:
            raise ManagedSSHPolicyError("managed SSH config directive is invalid")
        current[key] = value
    if not sections:
        raise ManagedSSHPolicyError("managed SSH config has no host section")
    return sections


def _assert_endpoint(section: dict[str, str], *, host: str, user: str, port: int,
                     key_path: str, known_hosts_path: str, allow_proxy: bool) -> None:
    expected = {
        "HostName": _quoted(host), "User": _quoted(user), "Port": str(int(port)),
        "BatchMode": "yes", "StrictHostKeyChecking": "yes",
        "UserKnownHostsFile": _quoted(_normal_path(known_hosts_path)),
        "IdentitiesOnly": "yes", "IdentityFile": _quoted(_normal_path(key_path)),
    }
    for key, value in expected.items():
        if section.get(key) != value:
            raise ManagedSSHPolicyError("managed SSH route pin does not match its snapshot")
    has_proxy = "ProxyJump" in section
    if has_proxy != bool(allow_proxy):
        raise ManagedSSHPolicyError("managed SSH route policy is invalid")


def split_and_validate_managed_options(options, *, managed_root, expected_host: str,
                                       expected_user: str, expected_port: int,
                                       expected_key: str, expected_gateway=None,
                                       permission_checker=None,
                                       require_managed: bool = False) -> tuple[list[str], list[str], str]:
    """Verify and split a generated ``-F`` route from ordinary SSH options.

    Returns ``(prefix, remaining, digest)``.  ``prefix`` is empty for legacy
    option lists.  A managed-path ``-F`` can never silently downgrade to the
    legacy path: any malformed/missing/tampered proof raises instead.
    """
    values = [str(item) for item in (options or [])]
    raw_root = Path(managed_root)
    root = raw_root.resolve()
    prefix: list[str] = []
    remaining: list[str] = []
    index = 0
    while index < len(values):
        value = values[index]
        if value == "-F":
            # ``<sha256>.conf`` is reserved for generated V4 routes.  A
            # durable job/profile snapshot may outlive a move or deletion of
            # the catalog directory, but it must never reinterpret that
            # snapshot as an arbitrary legacy ``-F`` config merely because
            # its parent is no longer the expected managed root.  Retain
            # ordinary legacy ``-F`` support for non-reserved filenames.
            if index + 1 >= len(values):
                raise ManagedSSHPolicyError("SSH config option is incomplete")
            raw_path = values[index + 1]
            try:
                raw = Path(raw_path)
                canonical = Path(os.path.abspath(str(raw)))
                path = canonical.resolve()
                managed = _same_path(canonical.parent, root)
                reserved_name = bool(_CONFIG_NAME_RE.fullmatch(canonical.name))
            except Exception:
                managed = False
                reserved_name = False
            if managed or reserved_name:
                if not raw_root.is_dir() or _is_reparse_or_symlink(raw_root):
                    raise ManagedSSHPolicyError("managed SSH route root is invalid")
                if not managed:
                    raise ManagedSSHPolicyError("managed SSH route path is outside its protected store")
                if (not canonical.is_absolute() or _is_reparse_or_symlink(canonical)
                        or not _same_path(path, canonical)):
                    raise ManagedSSHPolicyError("managed SSH route path is invalid")
                if prefix:
                    raise ManagedSSHPolicyError("multiple managed SSH route configs are not allowed")
                if not _CONFIG_NAME_RE.fullmatch(path.name) or not path.is_file():
                    raise ManagedSSHPolicyError("managed SSH route config is unavailable")
                # StrictHostKeyChecking only has its intended meaning if the
                # concrete pin file is still the protected app-owned regular
                # file.  Checking the path text in the route config alone
                # would allow a later replacement/symlink/permission change to
                # influence every normal job/kernel/scp re-entry.
                known_hosts = root / "known_hosts"
                try:
                    known_hosts_ok = (known_hosts.is_file()
                                      and not _is_reparse_or_symlink(known_hosts)
                                      and known_hosts.stat().st_size > 0)
                except OSError:
                    known_hosts_ok = False
                if not known_hosts_ok:
                    raise ManagedSSHPolicyError("managed SSH known-hosts pin is unavailable")
                if permission_checker is not None:
                    permission_checker(root, True)
                    permission_checker(path, False)
                    permission_checker(known_hosts, False)
                try:
                    data = path.read_bytes()
                except OSError as exc:
                    raise ManagedSSHPolicyError("managed SSH route config is unavailable") from exc
                digest = hashlib.sha256(data).hexdigest()
                if path.name != digest + ".conf":
                    raise ManagedSSHPolicyError("managed SSH route config failed integrity validation")
                sections = _read_sections(data)
                target = sections.get(str(expected_host))
                if target is None:
                    raise ManagedSSHPolicyError("managed SSH route target is unavailable")
                _assert_endpoint(
                    target, host=str(expected_host), user=str(expected_user), port=int(expected_port),
                    key_path=str(expected_key), known_hosts_path=str(root / "known_hosts"),
                    allow_proxy="ProxyJump" in target,
                )
                # A V4 route may intentionally use an external explicit key.
                # Only the one app-owned identity under the protected root is
                # additionally subject to managed-artifact revalidation.
                managed_key = root / "id_ed25519"
                managed_identity = _quoted(_normal_path(managed_key))

                def _verify_app_identity(section: dict[str, str]) -> None:
                    if section.get("IdentityFile") != managed_identity:
                        return
                    try:
                        key_ok = (managed_key.is_file()
                                  and not _is_reparse_or_symlink(managed_key)
                                  and managed_key.stat().st_size > 0)
                    except OSError:
                        key_ok = False
                    if not key_ok:
                        raise ManagedSSHPolicyError("managed SSH identity is unavailable")
                    if permission_checker is not None:
                        permission_checker(managed_key, False)

                _verify_app_identity(target)
                proxy = target.get("ProxyJump")
                if proxy:
                    if not _GATEWAY_ALIAS_RE.fullmatch(proxy) or proxy not in sections:
                        raise ManagedSSHPolicyError("managed SSH gateway policy is invalid")
                    gateway = sections[proxy]
                    if expected_gateway is not None:
                        _assert_endpoint(
                            gateway, host=str(expected_gateway["host"]), user=str(expected_gateway["user"]),
                            port=int(expected_gateway["port"]), key_path=str(expected_gateway["key"]),
                            known_hosts_path=str(root / "known_hosts"), allow_proxy=False,
                        )
                    else:
                        required = {"HostName", "User", "Port", "BatchMode", "StrictHostKeyChecking",
                                    "UserKnownHostsFile", "IdentitiesOnly", "IdentityFile"}
                        if set(gateway) != required:
                            raise ManagedSSHPolicyError("managed SSH gateway policy is invalid")
                    _verify_app_identity(gateway)
                elif expected_gateway is not None:
                    raise ManagedSSHPolicyError("managed SSH gateway proof is missing")
                expected_sections = 2 if proxy else 1
                if len(sections) != expected_sections:
                    raise ManagedSSHPolicyError("managed SSH config contains an unexpected host")
                prefix = ["-F", str(canonical).replace("\\", "/")]
                index += 2
                continue
        remaining.append(value)
        index += 1
    if prefix and remaining:
        raise ManagedSSHPolicyError("managed SSH routes cannot carry extra SSH options")
    if require_managed and not prefix:
        # This explicit, persistent profile/job-snapshot provenance bit is
        # what distinguishes a V4 route from a historical user-supplied
        # legacy ``-F`` option.  Do not let a renamed/moved V4 snapshot
        # downgrade to that legacy path.
        raise ManagedSSHPolicyError("managed SSH route proof is missing")
    return prefix, remaining, (prefix[1].rsplit("/", 1)[-1][:-5] if prefix else "")
