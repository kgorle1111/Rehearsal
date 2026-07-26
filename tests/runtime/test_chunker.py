from rehearsal.voice.chunker import SourceChunker


def _run(tokens: list[str]) -> list[str]:
    chunker = SourceChunker()
    out: list[str] = []
    for tok in tokens:
        out.extend(c.text for c in chunker.push(tok))
    out.extend(c.text for c in chunker.flush())
    return out


def test_terminal_punctuation_followed_by_whitespace_emits() -> None:
    chunks = _run(["Take two tablets daily. ", "Then rest."])
    assert chunks[0] == "Take two tablets daily."
    assert chunks[-1] == "Then rest."


def test_no_cut_without_trailing_whitespace_yet() -> None:
    chunker = SourceChunker()
    out = chunker.push("Take two tablets daily.")  # no trailing space yet
    assert out == []  # must wait to see whether whitespace follows
    out = chunker.flush()
    assert [c.text for c in out] == ["Take two tablets daily."]


def test_never_emits_below_min_chars_mid_stream() -> None:
    chunker = SourceChunker()
    out = chunker.push("Ok. ")  # "Ok." is 3 chars, below MIN_CHARS=12
    assert out == []
    out2 = chunker.flush()
    assert [c.text for c in out2] == ["Ok."]


def test_120_char_fallback_at_clause_boundary() -> None:
    # No terminal punctuation at all; forces the 120-char fallback.
    long_text = (
        "The patient reports intermittent chest pain and shortness of breath "
        "and dizziness when standing quickly and also some nausea and fatigue"
    )
    assert len(long_text) > 120
    chunks = _run([long_text])
    assert len(chunks) >= 2
    assert len(chunks[0]) <= 120


def test_spanish_inverted_openers_never_terminate() -> None:
    chunks = _run(["¿Cuánto tiempo lleva con el dolor? ", "Dígame."])
    assert chunks[0] == "¿Cuánto tiempo lleva con el dolor?"
    assert chunks[0].startswith("¿")  # opener was retained, not split off


def test_flush_emits_short_remainder_below_min_chars() -> None:
    chunker = SourceChunker()
    chunker.push("Hi")  # 2 chars, no terminal punctuation
    out = chunker.flush()
    assert [c.text for c in out] == ["Hi"]  # flush waives the 12-char floor


def test_offsets_are_monotonic_and_non_overlapping() -> None:
    chunker = SourceChunker()
    chunks = []
    for tok in ["Take two tablets. ", "Then rest for an hour. ", "Call if worse."]:
        chunks.extend(chunker.push(tok))
    chunks.extend(chunker.flush())
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert a.end <= b.start


if __name__ == "__main__":
    test_terminal_punctuation_followed_by_whitespace_emits()
    test_no_cut_without_trailing_whitespace_yet()
    test_never_emits_below_min_chars_mid_stream()
    test_120_char_fallback_at_clause_boundary()
    test_spanish_inverted_openers_never_terminate()
    test_flush_emits_short_remainder_below_min_chars()
    test_offsets_are_monotonic_and_non_overlapping()
    print("chunker: all checks passed")
