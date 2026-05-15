from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class GroupScheduleLimits:
    min_pairs_per_day: int = 2
    max_pairs_per_day: int = 5
    max_active_days_per_week: int = 5

    @classmethod
    def from_rules(cls, rules) -> "GroupScheduleLimits":
        return cls(
            min_pairs_per_day=max(0, int(getattr(rules, "min_pairs_students_per_day", 2) or 2)),
            max_pairs_per_day=max(1, int(getattr(rules, "max_pairs_students_per_day", 5) or 5)),
            max_active_days_per_week=5,
        )


def _detect_subgroup_kind(subject_name: str) -> str:
    name = str(subject_name or "").strip().lower()
    if not name:
        return "none"
    if re.search(r"п\s*/\s*гр\.?\s*1", name):
        return "subgroup_1"
    if re.search(r"п\s*/\s*гр\.?\s*2", name):
        return "subgroup_2"
    if re.search(r"(?:^|[\s(\[\{])1\s*п\s*г\b", name):
        return "subgroup_1"
    if re.search(r"(?:^|[\s(\[\{])2\s*п\s*г\b", name):
        return "subgroup_2"
    if re.search(r"подгрупп\w*\s*1", name):
        return "subgroup_1"
    if re.search(r"подгрупп\w*\s*2", name):
        return "subgroup_2"
    return "none"


def validate_group_week_entries(
    entries: list,
    *,
    group_id: int,
    week_type: int,
    limits: GroupScheduleLimits,
) -> list[str]:
    relevant_entries = [
        e for e in entries
        if int(getattr(e, "group_id", 0) or 0) == int(group_id)
        and int(getattr(e, "week_type", 0) or 0) == int(week_type)
    ]

    active_days = sorted({int(getattr(e, "day_of_week", 0) or 0) for e in relevant_entries})
    errors: list[str] = []
    if len(active_days) > int(limits.max_active_days_per_week):
        errors.append(
            f"Превышено число учебных дней: группа id={int(group_id)}, неделя {int(week_type)}."
        )

    pairs_by_day: dict[int, set[int]] = defaultdict(set)
    common_pairs_by_day: dict[int, set[int]] = defaultdict(set)
    subgroup_pairs_by_day: dict[tuple[int, str], set[int]] = defaultdict(set)
    for entry in relevant_entries:
        day = int(getattr(entry, "day_of_week", 0) or 0)
        pair = int(getattr(entry, "pair_number", 0) or 0)
        if day > 0 and pair > 0:
            pairs_by_day[day].add(pair)
            subgroup_kind = _detect_subgroup_kind(str(getattr(entry, "subject_name", "") or ""))
            if subgroup_kind == "none":
                common_pairs_by_day[day].add(pair)
            else:
                subgroup_pairs_by_day[(day, subgroup_kind)].add(pair)

    for day, pairs in pairs_by_day.items():
        half_load = 2 * len(common_pairs_by_day.get(day, set()))
        half_load += len(subgroup_pairs_by_day.get((day, "subgroup_1"), set()))
        half_load += len(subgroup_pairs_by_day.get((day, "subgroup_2"), set()))
        if half_load < 2 * int(limits.min_pairs_per_day) or half_load > 2 * int(limits.max_pairs_per_day):
            errors.append(
                f"Нарушена дневная нагрузка: группа id={int(group_id)}, неделя {int(week_type)}, день {int(day)}."
            )
        for subgroup_kind in ("subgroup_1", "subgroup_2"):
            trajectory_pairs = sorted(
                common_pairs_by_day.get(day, set())
                | subgroup_pairs_by_day.get((day, subgroup_kind), set())
            )
            if trajectory_pairs and trajectory_pairs != list(range(trajectory_pairs[0], trajectory_pairs[-1] + 1)):
                errors.append(
                    f"Обнаружено окно у студентов: группа id={int(group_id)}, неделя {int(week_type)}, день {int(day)}, {subgroup_kind}."
                )

    return errors
