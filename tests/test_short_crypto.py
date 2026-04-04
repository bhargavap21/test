from pm_latency.domain.short_crypto import (
    align_window_start,
    build_event_slug,
    candidate_window_starts,
    parse_event_slug,
    window_seconds_from_label,
)


def test_window_seconds_from_label():
    assert window_seconds_from_label("5m") == 300
    assert window_seconds_from_label("15m") == 900


def test_align_window_start():
    # On boundary: unchanged
    assert align_window_start(1775065500, 900) == 1775065500
    assert align_window_start(1775065500, 300) == 1775065500
    # Off boundary: floor to window
    assert align_window_start(1775065510, 900) == 1775065500
    assert align_window_start(1775065510, 300) == 1775065500
    assert align_window_start(1775065605, 300) == 1775065500


def test_candidate_window_starts():
    ts = 1775065500
    assert candidate_window_starts(ts, 900) == [
        1775064600,
        1775065500,
        1775066400,
        1775067300,
    ]


def test_build_and_parse_slug_roundtrip():
    slug = build_event_slug("btc", 900, 1775064600)
    assert slug == "btc-updown-15m-1775064600"
    assert parse_event_slug(slug) == ("btc", 900, 1775064600)

    slug5 = build_event_slug("eth", 300, 1775065200)
    assert slug5 == "eth-updown-5m-1775065200"
    assert parse_event_slug(slug5) == ("eth", 300, 1775065200)


def test_parse_rejects_other_slugs():
    assert parse_event_slug("random-market") is None
    assert parse_event_slug("") is None
