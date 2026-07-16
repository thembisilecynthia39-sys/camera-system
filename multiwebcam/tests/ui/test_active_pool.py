"""Tests for active/standby camera pool selection."""

from multiwebcam.ui.active_pool import SourcePoolEntry, choose_standby_source_id, rebalance_active_source_ids


def test_choose_standby_fills_1234_when_234_active_and_4_closes():
    entries = [
        SourcePoolEntry(1, "/dev/video0", ignored=True),
        SourcePoolEntry(2, "/dev/video2", ignored=False),
        SourcePoolEntry(3, "/dev/video4", ignored=False),
        SourcePoolEntry(4, "/dev/video6", ignored=True),
    ]

    standby = choose_standby_source_id(
        entries,
        active_source_ids={2, 3},
        excluded_source_id=4,
    )

    assert standby == 1


def test_choose_standby_fills_4_when_213_active_and_one_closes():
    entries = [
        SourcePoolEntry(1, "/dev/video0", ignored=False),
        SourcePoolEntry(2, "/dev/video2", ignored=False),
        SourcePoolEntry(3, "/dev/video4", ignored=True),
        SourcePoolEntry(4, "/dev/video6", ignored=True),
    ]

    standby = choose_standby_source_id(
        entries,
        active_source_ids={1, 2},
        excluded_source_id=3,
    )

    assert standby == 4


def test_choose_standby_skips_disconnected_and_active_sources():
    entries = [
        SourcePoolEntry(1, "/dev/video0", ignored=True),
        SourcePoolEntry(2, "/dev/video2", ignored=True),
        SourcePoolEntry(3, "", ignored=True, connected=False),
    ]

    standby = choose_standby_source_id(entries, active_source_ids={1})

    assert standby == 2


def test_rebalance_preserves_three_active_sources():
    entries = [
        SourcePoolEntry(0, "/dev/video0", ignored=False),
        SourcePoolEntry(1, "/dev/video2", ignored=False),
        SourcePoolEntry(2, "/dev/video4", ignored=False),
        SourcePoolEntry(3, "/dev/video6", ignored=True),
    ]

    active = rebalance_active_source_ids(entries, max_active=3)

    assert active == {0, 1, 2}


def test_rebalance_fills_from_standby_when_active_source_missing():
    entries = [
        SourcePoolEntry(0, "/dev/video0", ignored=False),
        SourcePoolEntry(1, "/dev/video2", ignored=False),
        SourcePoolEntry(2, "", ignored=False, connected=False),
        SourcePoolEntry(3, "/dev/video6", ignored=True),
    ]

    active = rebalance_active_source_ids(entries, max_active=3)

    assert active == {0, 1, 3}


def test_rebalance_caps_to_three_active_sources():
    entries = [
        SourcePoolEntry(0, "/dev/video0", ignored=False),
        SourcePoolEntry(1, "/dev/video2", ignored=False),
        SourcePoolEntry(2, "/dev/video4", ignored=False),
        SourcePoolEntry(3, "/dev/video6", ignored=False),
    ]

    active = rebalance_active_source_ids(entries, max_active=3)

    assert active == {0, 1, 2}
