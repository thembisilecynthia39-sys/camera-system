from __future__ import annotations
"""Helpers for selecting standby cameras for the active capture pool."""


from dataclasses import dataclass


@dataclass(frozen=True)
class SourcePoolEntry:
    source_id: int
    device_path: str
    ignored: bool
    connected: bool = True


def choose_standby_source_id(
    entries: list[SourcePoolEntry],
    active_source_ids: set[int],
    excluded_source_id: int | None = None,
) -> int | None:
    """Choose the next ignored, connected source that is not active."""
    for entry in sorted(entries, key=lambda item: item.source_id):
        if entry.source_id == excluded_source_id:
            continue
        if entry.source_id in active_source_ids:
            continue
        if not entry.connected or not entry.device_path:
            continue
        if entry.ignored:
            return entry.source_id
    return None


def rebalance_active_source_ids(entries: list[SourcePoolEntry], max_active: int) -> set[int]:
    """Select active sources for startup, preserving current active state first."""
    if max_active < 1:
        return set()

    connected = sorted(
        (entry for entry in entries if entry.connected and entry.device_path),
        key=lambda item: item.source_id,
    )
    selected: list[int] = []

    for entry in connected:
        if not entry.ignored and len(selected) < max_active:
            selected.append(entry.source_id)

    for entry in connected:
        if entry.ignored and len(selected) < max_active:
            selected.append(entry.source_id)

    return set(selected)
