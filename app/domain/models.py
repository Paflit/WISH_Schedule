# app/domain/models.py
"""
Domain models (чистые сущности предметной области).

ВАЖНО:
- Это НЕ ORM-модели.
- Это НЕ DTO.
- Это чистые dataclass, описывающие бизнес-сущности.
- Они используются в:
    - event_builder
    - solver
    - domain/scoring
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List


# ============================================================
# Справочники
# ============================================================

@dataclass
class Teacher:
    id_teacher: int
    full_name: str
    hard_max_pairs_per_day: int = 6
    soft_max_pairs_per_day: int = 4
    needs_method_day: bool = True


@dataclass
class StudentGroup:
    id_group: int
    group_name: str
    quantity: int
    education_form: str = "full-time"


@dataclass
class Subject:
    id_subject: int
    subject_name: str


@dataclass
class Room:
    id_room: int
    room_number: str
    room_type: str
    capacity: int
    building: Optional[str] = None


# ============================================================
# Календарь
# ============================================================

@dataclass
class AcademicCalendar:
    id_calendar: int
    academic_year: str
    semester: int
    week_type_mode: bool


@dataclass
class SemesterWeek:
    id_week: int
    calendar_id: int
    week_number_in_semester: int
    week_type: int
    is_study_week: bool


@dataclass
class TimeSlot:
    id_slot: int
    week_number_in_semester: int
    week_type: int
    day_of_week: int
    pair_number: int
    is_lunch_break: bool = False


# ============================================================
# Учебный план
# ============================================================

@dataclass
class CurriculumItem:
    id_curriculum: int
    group_id: int
    subject_id: int
    part_type: str              # lecture/practice/lab
    required_room_type: str


@dataclass
class CurriculumSemesterPlan:
    id_plan: int
    curriculum_id: int
    calendar_id: int
    hours_in_semester: int
    spread_mode: str = "auto_even"


@dataclass
class WeeklyLoadPlan:
    plan_id: int
    week_number_in_semester: int
    hours_this_week: int


# ============================================================
# Событие (Event) — единица оптимизации
# ============================================================

@dataclass
class Event:
    """
    Одно занятие (одна пара), которое нужно разместить.
    """
    id_event: int
    curriculum_id: int
    group_id: int
    subject_id: int
    part_type: str
    required_room_type: str

    fixed_week_number: Optional[int] = None
    fixed_week_type: Optional[int] = None


# ============================================================
# Результат оптимизации
# ============================================================

@dataclass
class SolutionEntry:
    event_id: int
    slot_id: int
    teacher_id: int
    room_id: int


@dataclass
class Solution:
    entries: List[SolutionEntry]
    objective_value: int


# ============================================================
# Метрики (для UI/аналитики)
# ============================================================

@dataclass
class ScheduleMetrics:
    total_penalty: int

    student_gaps: int
    teacher_gaps: int

    student_overloads: int
    teacher_overloads: int

    method_day_violations: int

    lecture_late_penalty: int