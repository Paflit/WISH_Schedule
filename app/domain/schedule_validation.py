from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


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

    pairs_by_day: dict[int, list[int]] = defaultdict(list)
    for entry in relevant_entries:
        day = int(getattr(entry, "day_of_week", 0) or 0)
        pair = int(getattr(entry, "pair_number", 0) or 0)
        if day > 0 and pair > 0:
            pairs_by_day[day].append(pair)

    for day, pairs in pairs_by_day.items():
        unique_pairs = sorted(set(pairs))
        if len(unique_pairs) < int(limits.min_pairs_per_day) or len(unique_pairs) > int(limits.max_pairs_per_day):
            errors.append(
                f"Нарушена дневная нагрузка: группа id={int(group_id)}, неделя {int(week_type)}, день {int(day)}."
            )
        if unique_pairs and unique_pairs != list(range(unique_pairs[0], unique_pairs[-1] + 1)):
            errors.append(
                f"Обнаружено окно у студентов: группа id={int(group_id)}, неделя {int(week_type)}, день {int(day)}."
            )

    return errors
