from apps.events.signing import sign, verify


def test_round_trip():
    h = sign(b'{"id":"evt_1"}', "s", timestamp=1000)
    assert verify(b'{"id":"evt_1"}', h, "s", now=1010)


def test_tampered_body_or_wrong_secret_fails():
    h = sign(b"a", "s", timestamp=1000)
    assert not verify(b"b", h, "s", now=1000)
    assert not verify(b"a", h, "other", now=1000)


def test_replay_outside_tolerance_fails():
    h = sign(b"a", "s", timestamp=1000)
    assert not verify(b"a", h, "s", tolerance=300, now=1301)


def test_garbage_header_fails():
    assert not verify(b"a", "nonsense", "s")
