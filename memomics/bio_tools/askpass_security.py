"""Stage the V5 SSH ASKPASS binary into an already protected app store.

The shipped helper beside this module is release-hash-bound, but an ordinary
installation directory can grant another local account delete/replace rights
through its parent ACL.  Password routes therefore never execute that sibling
directly.  The route layer copies its reviewed bytes into the existing
app-owned managed store, hardens the resulting file, and launches only that
private, content-addressed copy.

This module deliberately does not know the application's managed-store ACL
implementation.  The caller supplies its verified root plus the exact
hardening/verification callbacks, and must hold that store's lock for the
whole call.  Keeping this narrow avoids a dependency cycle with
``remote_cluster`` while preserving its established Windows DACL policy.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile
from typing import Callable

from memomics.bio_tools import password_ssh


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TEMP_PREFIX = ".memomics-v5-askpass-"


def _safe_temporary(path: Path, root: Path) -> bool:
    """Permit cleanup only for the exact temporary name this call created."""
    return path.parent == root and path.name.startswith(_TEMP_PREFIX) and path.suffix == ".tmp"


def _verify_existing(
    target: Path,
    *,
    expected_sha256: str,
    verify_managed_path: Callable[..., None],
) -> Path:
    """Validate an existing staged helper; never repair it at execution time."""
    verify_managed_path(target, directory=False)
    return password_ssh.verify_askpass_helper(target, expected_sha256=expected_sha256)


def _already_exists(error: OSError) -> bool:
    """Recognize the only safe race outcome from Windows' no-replace link."""
    return isinstance(error, FileExistsError) or getattr(error, "winerror", None) == 183


def stage_verified_askpass_helper(
    managed_root: Path | str,
    *,
    harden_managed_path: Callable[..., None],
    verify_managed_path: Callable[..., None],
    source_path: Path | str | None = None,
    expected_sha256: str | None = None,
) -> Path:
    """Return a private, hash- and ACL-verified V5 ASKPASS executable.

    The caller must already hold the managed-store lock.  If a content-addressed
    target exists, this function only verifies it; it never "repairs" a bad
    target.  New targets are published with a same-directory hard link rather
    than a replacing rename, so an unexpected pre-existing file is never
    overwritten.  The temporary and final names stay within ``managed_root``.
    """
    wanted = str(expected_sha256 or password_ssh.ASKPASS_HELPER_SHA256).lower()
    if not _SHA256_RE.fullmatch(wanted):
        raise password_ssh.PasswordSSHError("password_helper_unavailable")

    root = Path(managed_root)
    source = Path(source_path) if source_path is not None else password_ssh.askpass_helper_path()
    # Verify the release sibling before opening it.  A source replacement in
    # the following read cannot pass the final staged-file hash check.
    password_ssh.verify_askpass_helper(source, expected_sha256=wanted)
    verify_managed_path(root, directory=True)
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise password_ssh.PasswordSSHError("password_helper_unavailable") from exc
    target = root / ("askpass_helper-" + wanted + ".exe")
    if target.parent != root or target.parent.resolve() != resolved_root:
        raise password_ssh.PasswordSSHError("password_helper_unavailable")

    if target.exists() or target.is_symlink():
        return _verify_existing(target, expected_sha256=wanted, verify_managed_path=verify_managed_path)

    temporary: Path | None = None
    target_created = False
    completed = False
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=_TEMP_PREFIX, suffix=".tmp", dir=str(root))
        temporary = Path(temporary_name)
        if not _safe_temporary(temporary, root) or temporary.resolve().parent != resolved_root:
            raise password_ssh.PasswordSSHError("password_helper_unavailable")
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as source_file:
            while True:
                chunk = source_file.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())

        # The new file must be private before it receives its durable name.
        harden_managed_path(temporary, directory=False)
        verify_managed_path(temporary, directory=False)
        password_ssh.verify_askpass_helper(temporary, expected_sha256=wanted)
        try:
            # Same-directory hard-link publication is atomic and never
            # replaces a path that appeared after the initial existence check.
            os.link(temporary, target)
            target_created = True
        except OSError as exc:
            if not _already_exists(exc):
                raise password_ssh.PasswordSSHError("password_helper_unavailable") from exc
            return _verify_existing(target, expected_sha256=wanted, verify_managed_path=verify_managed_path)

        result = _verify_existing(target, expected_sha256=wanted, verify_managed_path=verify_managed_path)
        completed = True
        return result
    except password_ssh.PasswordSSHError:
        raise
    except OSError as exc:
        raise password_ssh.PasswordSSHError("password_helper_unavailable") from exc
    finally:
        # Do not leave a newly published helper behind if a post-publication
        # validation failed.  Never delete a target whose creation lost the
        # race; that target may have pre-existed this call.
        if target_created and not completed:
            try:
                if target.parent == root and target.name == "askpass_helper-" + wanted + ".exe":
                    target.unlink(missing_ok=True)
            except OSError:
                pass
        if temporary is not None:
            try:
                if temporary.exists() and _safe_temporary(temporary, root):
                    temporary.unlink()
            except OSError:
                pass


__all__ = ["stage_verified_askpass_helper"]
