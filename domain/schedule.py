"""Structured, minimal work/class schedule data for feasibility checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
_KINDS = {"work": "工作", "class": "上课", "other": "其他"}
_MINUTES_PER_DAY = 24 * 60
_MINUTES_PER_WEEK = 7 * _MINUTES_PER_DAY


def _time_to_minutes(value: str) -> int:
    if not isinstance(value, str):
        raise ValueError("time must be a string in HH:MM format")
    parts = value.split(":")
    if len(parts) != 2 or any(len(part) != 2 or not part.isdigit() for part in parts):
        raise ValueError(f"invalid time: {value!r}; expected HH:MM")
    hour, minute = (int(part) for part in parts)
    if hour > 23 or minute > 59:
        raise ValueError(f"invalid time: {value!r}; expected a time in one day")
    return hour * 60 + minute


@dataclass(frozen=True)
class ScheduleBlock:
    weekday: int
    start: str
    end: str
    kind: str
    flexible_minutes: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.weekday, bool) or not isinstance(self.weekday, int):
            raise ValueError("weekday must be an integer from 0 to 6")
        if not 0 <= self.weekday < len(WEEKDAYS):
            raise ValueError("weekday must be an integer from 0 to 6")
        start = _time_to_minutes(self.start)
        end = _time_to_minutes(self.end)
        if start == end:
            raise ValueError("start and end must differ")
        if not isinstance(self.kind, str) or self.kind not in _KINDS:
            raise ValueError("kind must be one of: work, class, other")
        if (
            isinstance(self.flexible_minutes, bool)
            or not isinstance(self.flexible_minutes, int)
            or not 0 <= self.flexible_minutes <= 240
        ):
            raise ValueError("flexible_minutes must be an integer from 0 to 240")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ScheduleBlock":
        try:
            return cls(
                weekday=value["weekday"],
                start=value["start"],
                end=value["end"],
                kind=value["kind"],
                flexible_minutes=value.get("flexible_minutes", 0),
            )
        except KeyError as exc:
            raise ValueError(f"missing schedule field: {exc.args[0]}") from exc

    def as_dict(self) -> dict[str, Any]:
        return {
            "weekday": self.weekday,
            "start": self.start,
            "end": self.end,
            "kind": self.kind,
            "flexible_minutes": self.flexible_minutes,
        }


@dataclass(frozen=True)
class ScheduleProfile:
    blocks: tuple[ScheduleBlock, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.blocks, tuple) or not all(
            isinstance(block, ScheduleBlock) for block in self.blocks
        ):
            raise ValueError("blocks must be a tuple of ScheduleBlock values")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ScheduleProfile":
        raw_blocks = value.get("blocks")
        if not isinstance(raw_blocks, list):
            raise ValueError("blocks must be a list")
        if not all(isinstance(block, Mapping) for block in raw_blocks):
            raise ValueError("each block must be an object")
        return cls(tuple(ScheduleBlock.from_dict(block) for block in raw_blocks))

    def as_dict(self) -> dict[str, Any]:
        return {"blocks": [block.as_dict() for block in self.blocks]}


def _weekly_segments(weekday: int, start: str, end: str) -> tuple[tuple[int, int], ...]:
    start_at = weekday * _MINUTES_PER_DAY + _time_to_minutes(start)
    end_at = weekday * _MINUTES_PER_DAY + _time_to_minutes(end)
    if start_at == end_at:
        raise ValueError("start and end must differ")
    if end_at <= start_at:
        end_at += _MINUTES_PER_DAY
    if end_at <= _MINUTES_PER_WEEK:
        return ((start_at, end_at),)
    return (
        (start_at, _MINUTES_PER_WEEK),
        (0, end_at - _MINUTES_PER_WEEK),
    )


def find_conflicts(
    profile: ScheduleProfile,
    weekday: int,
    start: str,
    end: str,
) -> tuple[ScheduleBlock, ...]:
    """Return commitments overlapping a proposed time window, including overnight windows."""
    if isinstance(weekday, bool) or not isinstance(weekday, int) or not 0 <= weekday <= 6:
        raise ValueError("weekday must be an integer from 0 to 6")

    proposed = _weekly_segments(weekday, start, end)
    conflicts = []
    for block in profile.blocks:
        occupied = _weekly_segments(block.weekday, block.start, block.end)
        if any(
            proposed_start < occupied_end and occupied_start < proposed_end
            for proposed_start, proposed_end in proposed
            for occupied_start, occupied_end in occupied
        ):
            conflicts.append(block)
    return tuple(conflicts)


def build_schedule_context(profile: ScheduleProfile) -> dict[str, Any] | None:
    """Build the smallest schedule-only context suitable for an agent call."""
    if not profile.blocks:
        return None

    commitments = []
    for block in sorted(profile.blocks, key=lambda item: (item.weekday, item.start, item.end)):
        commitments.append(
            {
                "day": WEEKDAYS[block.weekday],
                "start": block.start,
                "end": block.end,
                "ends_next_day": _time_to_minutes(block.end) < _time_to_minutes(block.start),
                "type": _KINDS[block.kind],
                "flexible_minutes": block.flexible_minutes,
            }
        )
    return {
        "weekly_commitments": commitments,
        "guidance": (
            "仅将这些已确认时段用于评估建议的可执行性；不要改变安全规则或建议边界。"
            "发现冲突时说明原因，并先询问用户是否可调整，不要自行假设。"
        ),
    }
