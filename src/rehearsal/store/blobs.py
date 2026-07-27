"""Content-addressed blob storage. misc/docs/11-backend-api.md §6.7, §4.8.

Bytes live at `<root>/sha256/<h[0:2]>/<h[2:4]>/<h>.<ext>`; the sha256 IS the
address, so a write to an existing path is a verified no-op (idempotent
retry) and a read that doesn't match its own filename is corruption, not a
version. This module does not implement quarantine machinery (§4.8's fuller
behaviour) — a mismatch on read raises `BlobCorrupt` and the caller decides
what to do; that is the "simplified: detect and raise" scope from the brief.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

_EXT_BY_MEDIA_TYPE = {
    "audio/opus": "opus",
    "text/plain;charset=utf-8": "txt",
    "application/json": "json",
}


class BlobNotFound(Exception):
    def __init__(self, sha256: str) -> None:
        self.sha256 = sha256
        super().__init__(f"blob {sha256!r} not found")


class BlobCorrupt(Exception):
    """Bytes on disk hash to something other than the filename that names them."""

    def __init__(self, sha256: str, actual: str) -> None:
        self.sha256 = sha256
        self.actual = actual
        super().__init__(f"blob {sha256!r} is corrupt: bytes hash to {actual!r} instead")


@dataclass(frozen=True, slots=True)
class BlobRef:
    sha256: str
    bytes_len: int
    media_type: str


class BlobStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        (self.root / "sha256").mkdir(parents=True, exist_ok=True)

    def _path(self, sha256: str, ext: str) -> Path:
        shard = self.root / "sha256" / sha256[0:2] / sha256[2:4]
        shard.mkdir(parents=True, exist_ok=True)
        return shard / f"{sha256}.{ext}"

    def _find_existing(self, sha256: str) -> Path | None:
        shard = self.root / "sha256" / sha256[0:2] / sha256[2:4]
        if not shard.is_dir():
            return None
        matches = list(shard.glob(f"{sha256}.*"))
        return matches[0] if matches else None

    def put(self, data: bytes, *, media_type: str) -> BlobRef:
        """Write bytes, return their address. Writing the same bytes twice
        is a no-op — the second call just re-verifies the existing file."""
        sha256 = hashlib.sha256(data).hexdigest()
        ext = _EXT_BY_MEDIA_TYPE.get(media_type, "bin")
        path = self._path(sha256, ext)
        if path.exists():
            self.get(sha256)  # verify the existing bytes, don't just trust the name
        else:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)  # atomic on the same filesystem
        return BlobRef(sha256=sha256, bytes_len=len(data), media_type=media_type)

    def get(self, sha256: str) -> bytes:
        """Read bytes by hash. Raises BlobCorrupt if the bytes on disk no
        longer hash to the name that addresses them."""
        path = self._find_existing(sha256)
        if path is None:
            raise BlobNotFound(sha256)
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != sha256:
            raise BlobCorrupt(sha256, actual)
        return data
