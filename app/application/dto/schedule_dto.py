from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class ScheduleEntryDTO:

    id_schedule: int
    variant_id: int
    curriculum_id: int
    event_id: int

    slot_id: int
    week_number: int
    week_type: int
    day_of_week: int
    pair_number: int

    group_id: int
    group_name: str

    teacher_id: int
    teacher_name: str

    subject_id: int
    subject_name: str
    part_type: str

    room_id: int
    room_number: str

    is_locked: bool = False

    @property
    def display_title(self) -> str:
        parts = [self.subject_name]
        if self.part_type:
            parts.append(f"({self.part_type})")
        return " ".join(p for p in parts if p).strip()

    @property
    def display_subtitle(self) -> str:
        parts = [self.group_name, self.teacher_name, self.room_number]
        return " | ".join(p for p in parts if p).strip()

    @property
    def has_week_binding(self) -> bool:
        return self.week_number > 0 or self.week_type > 0


@dataclass(slots=True)
class ScheduleVariantDTO:
    """
    DTO варианта расписания.
    """

    id_variant: int
    name: str
    objective_score: int = 0
    entries: list[ScheduleEntryDTO] = field(default_factory=list)

    @property
    def entries_count(self) -> int:
        return len(self.entries)

    @property
    def is_empty(self) -> bool:
        return not self.entries


@dataclass(slots=True)
class GenerationResultDTO:
    """
    DTO результата генерации расписания.
    """

    variants: list[ScheduleVariantDTO] = field(default_factory=list)
    message: Optional[str] = None

    @property
    def variants_count(self) -> int:
        return len(self.variants)

    @property
    def is_empty(self) -> bool:
        return not self.variants