"""ULID generation. misc/docs/11-backend-api.md §2.1: `session_id` and
`run_id` are ULIDs (26 chars, Crockford base32, lexicographically sortable
by creation time). No dependency pulled in for this — it's 128 bits
(48 ms-timestamp + 80 random) formatted with a 32-symbol alphabet, which is
a one-function stdlib job (`time` + `os.urandom`).
"""

from __future__ import annotations

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    ms = int(time.time() * 1000)
    value = (ms << 80) | int.from_bytes(os.urandom(10), "big")
    chars = []
    for _ in range(26):
        value, rem = divmod(value, 32)
        chars.append(_CROCKFORD[rem])
    return "".join(reversed(chars))
