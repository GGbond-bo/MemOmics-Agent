"""Offline invariants for V5 catalog password storage.

These tests use only the injected in-memory store; they never enumerate the
Windows credential vault or create an SSH process.
"""
from __future__ import annotations

import pytest

from memomics.cluster_credentials import CredentialError, CredentialRecord, MemoryCredentialStore


ACCOUNT = "account-0123456789ab"


def test_restore_after_delete_moves_past_original_revision():
    store = MemoryCredentialStore()
    original = store.put(ACCOUNT, "first-secret")
    assert original.revision == 1
    removed = store.delete(ACCOUNT)
    assert removed == original

    # This mirrors an API transaction that deleted the Windows credential,
    # then rolled it back because the catalog/YAML phase failed.  Reusing 1
    # would let a concurrent Phase-2 compare succeed incorrectly.
    restored = store.restore(ACCOUNT, removed)
    assert restored is not None
    assert restored.revision == 2
    assert store.get(ACCOUNT) == restored


def test_restore_wins_over_current_revision_and_rejects_overflow():
    store = MemoryCredentialStore()
    stored = store.put(ACCOUNT, "current-secret")
    assert stored.revision == 1
    restored = store.restore(ACCOUNT, CredentialRecord(password="rollback-secret", revision=7))
    assert restored is not None and restored.revision == 8
    assert store.get(ACCOUNT) == restored

    with pytest.raises(CredentialError, match="credential_store_unavailable"):
        store.restore(ACCOUNT, CredentialRecord(password="x", revision=0x7FFFFFFFFFFFFFFF))
