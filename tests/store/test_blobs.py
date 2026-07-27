"""Content-addressed blob store round-trip and corruption detection."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from rehearsal.store.blobs import BlobCorrupt, BlobNotFound, BlobStore


def test_put_then_get_round_trips_bytes(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    data = b"hola mundo"
    ref = store.put(data, media_type="text/plain;charset=utf-8")
    assert ref.sha256 == hashlib.sha256(data).hexdigest()
    assert ref.bytes_len == len(data)
    assert store.get(ref.sha256) == data


def test_put_same_bytes_twice_is_idempotent(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    data = b"repeat me"
    ref1 = store.put(data, media_type="application/json")
    ref2 = store.put(data, media_type="application/json")
    assert ref1 == ref2
    assert store.get(ref1.sha256) == data


def test_get_unknown_hash_raises_not_found(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    with pytest.raises(BlobNotFound):
        store.get("0" * 64)


def test_get_detects_corrupted_bytes_on_disk(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    ref = store.put(b"original", media_type="text/plain;charset=utf-8")
    shard = tmp_path / "sha256" / ref.sha256[0:2] / ref.sha256[2:4]
    path = next(shard.glob(f"{ref.sha256}.*"))
    path.write_bytes(b"tampered")  # bytes no longer hash to the filename

    with pytest.raises(BlobCorrupt):
        store.get(ref.sha256)


def test_blob_dir_and_file_use_owner_only_permissions(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    ref = store.put(b"secret speech", media_type="audio/opus")
    shard = tmp_path / "sha256" / ref.sha256[0:2] / ref.sha256[2:4]
    assert (shard.stat().st_mode & 0o777) == 0o700
    path = next(shard.glob(f"{ref.sha256}.*"))
    assert (path.stat().st_mode & 0o777) == 0o600
