"""Windows Credential Manager storage for V5 cluster-account passwords.

Only a server-owned catalog account id identifies a secret.  Credentials never
enter the SQLite catalog, YAML, HTTP response, command-line arguments, or
process environment.  The Generic Credential target is additionally bound to
the resolved application data root so a development/test installation cannot
read the live installation's account credentials.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import re
import struct
import threading
from typing import Protocol


_TARGET_PREFIX = "MemOmics/cluster/v5/"
_ACCOUNT_ID_RE = re.compile(r"^account-[0-9a-f]{12}$")
_NAMESPACE_RE = re.compile(r"^[0-9a-f]{32}$")
_MAGIC = b"MMCV1\x00"
_MAX_BLOB_SIZE = 5 * 512  # CRED_MAX_CREDENTIAL_BLOB_SIZE
_MAX_PASSWORD_CHARACTERS = 1024
_ERROR_NOT_FOUND = 1168
_TARGET_LOCKS_GUARD = threading.RLock()
_TARGET_LOCKS: dict[str, threading.RLock] = {}


class CredentialError(RuntimeError):
    """A safe, credential-free error code suitable for API translation."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, repr=False)
class CredentialRecord:
    """Internal-only password plus durable non-secret revision metadata."""

    password: str = field(repr=False)
    revision: int

    def __repr__(self) -> str:
        return "CredentialRecord(password=<redacted>, revision=%d)" % self.revision


class CredentialStore(Protocol):
    """Minimal injectable storage interface used by the catalog HTTP router."""

    def get(self, account_id: str) -> CredentialRecord | None: ...
    def put(self, account_id: str, password: str) -> CredentialRecord: ...
    def delete(self, account_id: str) -> CredentialRecord | None: ...
    def restore(self, account_id: str, record: CredentialRecord | None) -> CredentialRecord | None: ...
    def state(self, account_id: str) -> str: ...
    def target_for(self, account_id: str) -> str: ...


def validate_password(value: object) -> str:
    """Validate without stripping: leading/trailing spaces can be real secrets."""
    if not isinstance(value, str) or not value:
        raise CredentialError("credential_password_required")
    if len(value) > _MAX_PASSWORD_CHARACTERS:
        raise CredentialError("credential_password_too_long")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise CredentialError("credential_password_invalid")
    return value


def namespace_for_app_home(app_home: str | os.PathLike[str]) -> str:
    """Stable non-secret namespace for one resolved data root."""
    try:
        normalized = os.path.normcase(os.path.normpath(str(Path(app_home).resolve(strict=False))))
    except Exception as exc:
        raise CredentialError("credential_store_unavailable") from exc
    return hashlib.sha256(normalized.encode("utf-8", "surrogatepass")).hexdigest()[:32]


def validate_target(target: object) -> str:
    """Reject arbitrary Credential Manager targets before every native read."""
    if not isinstance(target, str) or not target.startswith(_TARGET_PREFIX):
        raise CredentialError("credential_target_invalid")
    pieces = target.split("/")
    if len(pieces) != 5 or pieces[:3] != ["MemOmics", "cluster", "v5"]:
        raise CredentialError("credential_target_invalid")
    if not _NAMESPACE_RE.fullmatch(pieces[3]) or not _ACCOUNT_ID_RE.fullmatch(pieces[4]):
        raise CredentialError("credential_target_invalid")
    return target


def _account_id(value: object) -> str:
    account_id = str(value or "")
    if not _ACCOUNT_ID_RE.fullmatch(account_id):
        raise CredentialError("credential_account_invalid")
    return account_id


def _namespace_lock(namespace: str) -> threading.RLock:
    """Serialize native read/revision/write sequences across store instances."""
    with _TARGET_LOCKS_GUARD:
        lock = _TARGET_LOCKS.get(namespace)
        if lock is None:
            lock = threading.RLock()
            _TARGET_LOCKS[namespace] = lock
        return lock


def _encode_record(password: str, revision: int) -> bytearray:
    password = validate_password(password)
    if not isinstance(revision, int) or revision < 1 or revision > 0x7FFFFFFFFFFFFFFF:
        raise CredentialError("credential_store_unavailable")
    payload = bytearray(_MAGIC + struct.pack("<Q", revision) + password.encode("utf-8", "strict"))
    if len(payload) > _MAX_BLOB_SIZE:
        for index in range(len(payload)):
            payload[index] = 0
        raise CredentialError("credential_password_too_long")
    return payload


def _decode_record(payload: bytes | bytearray) -> CredentialRecord:
    if len(payload) <= len(_MAGIC) + 8 or not bytes(payload).startswith(_MAGIC):
        raise CredentialError("credential_store_unavailable")
    revision = struct.unpack("<Q", bytes(payload[len(_MAGIC):len(_MAGIC) + 8]))[0]
    if revision < 1:
        raise CredentialError("credential_store_unavailable")
    try:
        password = bytes(payload[len(_MAGIC) + 8:]).decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise CredentialError("credential_store_unavailable") from exc
    validate_password(password)
    return CredentialRecord(password=password, revision=revision)


class MemoryCredentialStore:
    """Test-only injectable store; no secret is ever serialized by this class."""

    def __init__(self, namespace: str = "0" * 32):
        if not _NAMESPACE_RE.fullmatch(namespace):
            raise ValueError("invalid test credential namespace")
        self.namespace = namespace
        self._records: dict[str, CredentialRecord] = {}
        self._lock = _namespace_lock("memory-" + namespace)

    def target_for(self, account_id: str) -> str:
        return validate_target(_TARGET_PREFIX + self.namespace + "/" + _account_id(account_id))

    def get(self, account_id: str) -> CredentialRecord | None:
        target = self.target_for(account_id)
        with self._lock:
            return self._records.get(target)

    def put(self, account_id: str, password: str) -> CredentialRecord:
        target = self.target_for(account_id)
        password = validate_password(password)
        with self._lock:
            prior = self._records.get(target)
            record = CredentialRecord(password=password, revision=(prior.revision + 1 if prior else 1))
            self._records[target] = record
            return record

    def delete(self, account_id: str) -> CredentialRecord | None:
        target = self.target_for(account_id)
        with self._lock:
            return self._records.pop(target, None)

    def restore(self, account_id: str, record: CredentialRecord | None) -> CredentialRecord | None:
        if record is None:
            self.delete(account_id)
            return None
        target = self.target_for(account_id)
        # A restore is part of an API rollback, not a normal "put".  Its
        # revision must move forward even when a concurrent delete made the
        # target absent: otherwise a Phase-1 probe that observed revision 1
        # could accept a delete+rollback that recreated revision 1 as if its
        # credential had never changed.
        password = validate_password(record.password)
        if not isinstance(record.revision, int) or record.revision < 1:
            raise CredentialError("credential_store_unavailable")
        with self._lock:
            previous = self._records.get(target)
            revision = max(previous.revision if previous else 0, record.revision) + 1
            if revision > 0x7FFFFFFFFFFFFFFF:
                raise CredentialError("credential_store_unavailable")
            restored = CredentialRecord(password=password, revision=revision)
            self._records[target] = restored
            return restored

    def state(self, account_id: str) -> str:
        return "configured" if self.get(account_id) is not None else "missing"


if os.name == "nt":
    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


    class _CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR), ("LastWritten", _FILETIME), ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD), ("Attributes", wintypes.LPVOID),
            ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
        ]


    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _advapi32.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
    _advapi32.CredReadW.restype = wintypes.BOOL
    _advapi32.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
    _advapi32.CredWriteW.restype = wintypes.BOOL
    _advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    _advapi32.CredDeleteW.restype = wintypes.BOOL
    _advapi32.CredFree.argtypes = [wintypes.LPVOID]
    _advapi32.CredFree.restype = None
    _CRED_TYPE_GENERIC = 1
    _CRED_PERSIST_LOCAL_MACHINE = 2


class CredentialManagerStore:
    """Windows Credential Manager Generic Credential implementation."""

    def __init__(self, app_home: str | os.PathLike[str]):
        if os.name != "nt":
            raise CredentialError("credential_store_unavailable")
        self.namespace = namespace_for_app_home(app_home)
        self._lock = _namespace_lock(self.namespace)

    def target_for(self, account_id: str) -> str:
        return validate_target(_TARGET_PREFIX + self.namespace + "/" + _account_id(account_id))

    def _read_target(self, target: str) -> CredentialRecord | None:
        target = validate_target(target)
        pointer = ctypes.POINTER(_CREDENTIALW)()
        if not _advapi32.CredReadW(target, _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == _ERROR_NOT_FOUND:
                return None
            raise CredentialError("credential_store_unavailable")
        payload = bytearray()
        try:
            credential = pointer.contents
            if int(credential.Type) != _CRED_TYPE_GENERIC or int(credential.CredentialBlobSize) > _MAX_BLOB_SIZE:
                raise CredentialError("credential_store_unavailable")
            if credential.CredentialBlobSize:
                if not bool(credential.CredentialBlob):
                    raise CredentialError("credential_store_unavailable")
                payload.extend(ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize))
            return _decode_record(payload)
        finally:
            for index in range(len(payload)):
                payload[index] = 0
            _advapi32.CredFree(pointer)

    def get(self, account_id: str) -> CredentialRecord | None:
        with self._lock:
            return self._read_target(self.target_for(account_id))

    def _write_target(self, target: str, password: str, revision: int) -> CredentialRecord:
        target = validate_target(target)
        payload = _encode_record(password, revision)
        blob = (ctypes.c_ubyte * len(payload)).from_buffer(payload)
        credential = _CREDENTIALW()
        credential.Type = _CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.CredentialBlobSize = len(payload)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = ""
        try:
            if not _advapi32.CredWriteW(ctypes.byref(credential), 0):
                raise CredentialError("credential_store_unavailable")
            return CredentialRecord(password=password, revision=revision)
        finally:
            for index in range(len(payload)):
                payload[index] = 0

    def put(self, account_id: str, password: str) -> CredentialRecord:
        target = self.target_for(account_id)
        password = validate_password(password)
        with self._lock:
            previous = self._read_target(target)
            revision = previous.revision + 1 if previous else 1
            return self._write_target(target, password, revision)

    def delete(self, account_id: str) -> CredentialRecord | None:
        target = self.target_for(account_id)
        with self._lock:
            previous = self._read_target(target)
            if previous is None:
                return None
            if not _advapi32.CredDeleteW(target, _CRED_TYPE_GENERIC, 0):
                raise CredentialError("credential_store_unavailable")
            return previous

    def restore(self, account_id: str, record: CredentialRecord | None) -> CredentialRecord | None:
        if record is None:
            self.delete(account_id)
            return None
        target = self.target_for(account_id)
        password = validate_password(record.password)
        if not isinstance(record.revision, int) or record.revision < 1:
            raise CredentialError("credential_store_unavailable")
        # A rollback must move monotonically past the removed record even
        # when the target is currently absent.  Calling put() after delete()
        # would restart at 1 and could fool an in-flight Phase-2 revision
        # check that had also observed 1 before the delete+rollback race.
        with self._lock:
            current = self._read_target(target)
            revision = max(current.revision if current else 0, record.revision) + 1
            if revision > 0x7FFFFFFFFFFFFFFF:
                raise CredentialError("credential_store_unavailable")
            return self._write_target(target, password, revision)

    def state(self, account_id: str) -> str:
        return "configured" if self.get(account_id) is not None else "missing"


__all__ = [
    "CredentialError", "CredentialManagerStore", "CredentialRecord", "CredentialStore",
    "MemoryCredentialStore", "namespace_for_app_home", "validate_password", "validate_target",
]
