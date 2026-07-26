"""Token stream -> speakable chunks. misc/docs/05-voice-pipeline.md §6.1.

Deterministic; no model involved. Emission rule, in order:

1. Terminal punctuation (`. ! ? ¡ ¿ … : ;`) followed by whitespace -> emit.
2. No terminal punctuation for 120 characters -> emit at the last clause
   boundary (", ", " y ", " o ", " pero ", " que ", " and ", " but ", " so "),
   else at the last word boundary.
3. Never emit a chunk shorter than 12 characters unless it is the flush.
4. Spanish inverted openers (`¿`, `¡`) never terminate a chunk — they open one.
"""

from __future__ import annotations

from dataclasses import dataclass

_TERMINAL = frozenset(".!?¡¿…:;")
_OPENERS = frozenset("¿¡")  # rule 4: these never trigger a cut, despite being in _TERMINAL
_CLAUSE_MARKERS: tuple[str, ...] = (", ", " y ", " o ", " pero ", " que ", " and ", " but ", " so ")
MAX_CHARS = 120
MIN_CHARS = 12


@dataclass(frozen=True, slots=True)
class Chunk:
    text: str
    start: int
    end: int


class SourceChunker:
    def __init__(self) -> None:
        self._buf: str = ""
        self._base_offset: int = 0

    def push(self, token_text: str) -> list[Chunk]:
        self._buf += token_text
        return self._drain(final=False)

    def flush(self) -> list[Chunk]:
        chunks = self._drain(final=True)
        if self._buf:
            chunks.append(self._cut(len(self._buf)))
        return chunks

    def _drain(self, *, final: bool) -> list[Chunk]:
        out: list[Chunk] = []
        while True:
            cut_at = self._terminal_cut(final=final)
            if cut_at is None and len(self._buf) > MAX_CHARS:
                cut_at = self._fallback_cut()
            if cut_at is None:
                return out
            out.append(self._cut(cut_at))

    def _terminal_cut(self, *, final: bool) -> int | None:
        buf = self._buf
        i = MIN_CHARS  # rule 3: never consider a cut shorter than MIN_CHARS here
        while i <= len(buf):
            ch = buf[i - 1]
            if ch in _TERMINAL and ch not in _OPENERS:
                if i < len(buf):
                    if buf[i].isspace():
                        return i
                elif final:
                    return i
            i += 1
        return None

    def _fallback_cut(self) -> int | None:
        window = self._buf[:MAX_CHARS]
        best: int | None = None
        for marker in _CLAUSE_MARKERS:
            idx = window.rfind(marker)
            if idx == -1:
                continue
            candidate = idx + len(marker.rstrip())
            if candidate >= MIN_CHARS and (best is None or candidate > best):
                best = candidate
        if best is not None:
            return best
        idx = window.rfind(" ")
        if idx >= MIN_CHARS:
            return idx
        return MAX_CHARS  # forced cut: no boundary in the window at all

    def _cut(self, at: int) -> Chunk:
        text = self._buf[:at]
        start = self._base_offset
        end = start + len(text)
        remainder = self._buf[at:]
        stripped_len = len(remainder) - len(remainder.lstrip())
        self._buf = remainder.lstrip()
        self._base_offset = end + stripped_len
        return Chunk(text=text.strip(), start=start, end=end)
