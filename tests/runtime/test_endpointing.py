from rehearsal.voice.endpointing import Endpointer, EndpointEvent, EndpointPolicy, EndpointState

FRAME_MS = 20


def _feed(
    ep: Endpointer, p_values: list[float], rms: list[float] | None = None
) -> list[EndpointEvent | None]:
    out = []
    for i, p in enumerate(p_values):
        r = rms[i] if rms else None
        out.append(ep.push(p, r))
    return out


def test_onset_after_three_voiced_frames() -> None:
    ep = Endpointer(EndpointPolicy())
    events = _feed(ep, [0.9, 0.9, 0.9])
    assert events == [None, None, EndpointEvent.ONSET]
    assert ep.state is EndpointState.SPEAKING


def test_hysteresis_dead_zone_does_not_flip_state() -> None:
    ep = Endpointer(EndpointPolicy())
    _feed(ep, [0.9, 0.9, 0.9])  # onset -> speaking
    # a frame in (silence_threshold, speech_threshold) keeps prior classification
    events = _feed(ep, [0.45])
    assert ep.state is EndpointState.SPEAKING
    assert events == [None]


def test_default_hangover_closes_capture() -> None:
    policy = EndpointPolicy()
    ep = Endpointer(policy, frame_ms=FRAME_MS)
    _feed(ep, [0.9, 0.9, 0.9])  # onset, utterance ~2000ms in duration below
    # push voiced frames until utterance duration is between 1200 and 4000ms
    n_more_voiced = 60  # 60*20ms = 1200ms, total utterance ~1260ms
    _feed(ep, [0.9] * n_more_voiced)
    n_hangover_frames = policy.hangover_ms // FRAME_MS
    events = _feed(ep, [0.1] * n_hangover_frames)
    assert EndpointEvent.CAPTURE_ENDED in events
    assert ep.state is EndpointState.CLOSED


def test_short_utterance_uses_hangover_short() -> None:
    policy = EndpointPolicy()
    ep = Endpointer(policy, frame_ms=FRAME_MS)
    _feed(ep, [0.9, 0.9, 0.9])  # onset
    _feed(ep, [0.9] * 10)  # utterance now 260ms: above min_utterance_ms, still < 1200ms
    n_short = policy.hangover_short_ms // FRAME_MS  # total silent ticks needed to close
    events = _feed(ep, [0.1])  # tick 1: this frame *is* the transition into hangover
    assert EndpointEvent.CAPTURE_ENDED not in events
    events = _feed(ep, [0.1] * (n_short - 2))  # ticks 2..(n_short - 1): still short
    assert EndpointEvent.CAPTURE_ENDED not in events
    events = _feed(ep, [0.1])  # tick n_short: closes
    assert EndpointEvent.CAPTURE_ENDED in events


def test_long_utterance_with_falling_energy_uses_hangover_long() -> None:
    policy = EndpointPolicy()
    ep = Endpointer(policy, frame_ms=FRAME_MS)
    _feed(ep, [0.9, 0.9, 0.9], rms=[1.0, 1.0, 1.0])
    # push well past 4000ms of speech with high, then falling, trailing energy
    n_high = 200  # 200*20 = 4000ms -> total utterance so far > 4000ms after onset
    _feed(ep, [0.9] * n_high, rms=[1.0] * n_high)
    n_falling = 400 // FRAME_MS + 2
    _feed(ep, [0.9] * n_falling, rms=[0.1] * n_falling)  # trailing energy drops
    events = _feed(ep, [0.1])  # tick 1: enters hangover with falling-energy history
    assert ep.state is EndpointState.HANGOVER
    n_long = policy.hangover_long_ms // FRAME_MS
    events = _feed(ep, [0.1] * (n_long - 2))  # ticks 2..(n_long - 1): still short
    assert EndpointEvent.CAPTURE_ENDED not in events
    events = _feed(ep, [0.1])  # tick n_long: closes
    assert EndpointEvent.CAPTURE_ENDED in events


def test_cough_below_min_utterance_is_discarded_silently() -> None:
    policy = EndpointPolicy()
    ep = Endpointer(policy, frame_ms=FRAME_MS)
    _feed(ep, [0.9, 0.9, 0.9])  # onset, ~60ms utterance, below min_utterance_ms=250
    n_short_hangover_frames = policy.hangover_short_ms // FRAME_MS
    events = _feed(ep, [0.1] * n_short_hangover_frames)
    assert EndpointEvent.CAPTURE_ENDED not in events
    assert ep.state is EndpointState.LISTENING  # discarded, back to listening


def test_retraction_within_grace_window() -> None:
    policy = EndpointPolicy()
    ep = Endpointer(policy, frame_ms=FRAME_MS)
    _feed(ep, [0.9, 0.9, 0.9])
    n_short_hangover_frames = policy.hangover_short_ms // FRAME_MS
    _feed(ep, [0.1] * n_short_hangover_frames)  # closes (short utterance would discard...)
    # bump utterance above min first so it actually closes instead of discarding
    ep2 = Endpointer(policy, frame_ms=FRAME_MS)
    _feed(ep2, [0.9] * 20)  # 400ms voiced, above min_utterance_ms(250) once onset accounted
    _feed(ep2, [0.1] * (policy.hangover_short_ms // FRAME_MS))
    assert ep2.state is EndpointState.CLOSED
    events = _feed(ep2, [0.9])  # resumes immediately, well within grace
    assert events == [EndpointEvent.RETRACTED]
    state_after_retraction: EndpointState = ep2.state
    assert state_after_retraction is EndpointState.SPEAKING


def test_no_retraction_after_grace_expires() -> None:
    policy = EndpointPolicy()
    ep = Endpointer(policy, frame_ms=FRAME_MS)
    _feed(ep, [0.9] * 20)
    _feed(ep, [0.1] * (policy.hangover_short_ms // FRAME_MS))
    assert ep.state is EndpointState.CLOSED
    n_grace_frames = policy.resume_grace_ms // FRAME_MS
    _feed(ep, [0.0] * (n_grace_frames + 5))  # let grace expire while silent
    events = _feed(ep, [0.9])
    assert events == [None]
    assert ep.state is EndpointState.CLOSED  # stays closed; this is the next turn's problem


def test_truncated_at_capture_max_ms() -> None:
    policy = EndpointPolicy(capture_max_ms=200)  # small cap for a fast test
    ep = Endpointer(policy, frame_ms=FRAME_MS)
    # exactly enough continuous voiced frames to hit the cap, no further
    # frames after truncation (a real trainee stops once cut off).
    events = _feed(ep, [0.9] * 10)
    assert EndpointEvent.CAPTURE_ENDED_TRUNCATED in events
    assert ep.state is EndpointState.CLOSED


if __name__ == "__main__":
    test_onset_after_three_voiced_frames()
    test_hysteresis_dead_zone_does_not_flip_state()
    test_default_hangover_closes_capture()
    test_short_utterance_uses_hangover_short()
    test_long_utterance_with_falling_energy_uses_hangover_long()
    test_cough_below_min_utterance_is_discarded_silently()
    test_retraction_within_grace_window()
    test_no_retraction_after_grace_expires()
    test_truncated_at_capture_max_ms()
    print("endpointing: all checks passed")
