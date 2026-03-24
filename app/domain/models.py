from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List

@dataclass(frozen=True)
class Teacher:
    """
    Доменная модель преподавателя.

    В UI пользователь задаёт:
    - ФИО
    - набор дисциплин
    - допустимые типы занятий по каждой дисциплине
    - календарь доступности

    Поля max/soft/method_day оставлены как технический задел
    для solver / scoring, даже если в UI они сейчас не редактируются.
    """
    id_teacher: int
    full_name: str
    hard_max_pairs_per_day: int = 6
    soft_max_pairs_per_day: int = 4
    needs_method_day: bool = True


@dataclass(frozen=True)
class StudentGroup:
    id_group: int
    group_name: str
    quantity: int
    year: Optional[int] = None
    education_form: str = "full-time"


@dataclass(frozen=True)
class Subject:
    id_subject: int
    subject_name: str


@dataclass(frozen=True)
class Room:
    id_room: int
    room_number: str
    room_type: str
    capacity: int
    building: Optional[str] = None


# ============================================================
# Calendar
# ============================================================

@dataclass(frozen=True)
class AcademicCalendar:
    id_calendar: int
    academic_year: str
    semester: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    week_type_mode: int = 1
    comment: Optional[str] = None


@dataclass(frozen=True)
class SemesterWeek:
    id_week: int
    calendar_id: int
    week_type: int
    week_number_in_semester: int = 0
    is_study_week: bool = True
    comment: Optional[str] = None


@dataclass(frozen=True)
class TimeSlot:
    id_slot: int
    week_type: int
    day_of_week: int
    pair_number: int
    week_number_in_semester: int = 0
    is_lunch_break: bool = False


# ============================================================
# Curriculum / workload
# ============================================================

@dataclass(frozen=True)
class CurriculumItem:
    """
    Один элемент учебного плана = одна часть дисциплины для группы.

    part_type:
    - lecture
    - practice
    - computer_practice
    - lab
    """
    id_curriculum: int
    group_id: int
    subject_id: int
    part_type: str
    required_room_type: str


@dataclass(frozen=True)
class SemesterPlan:
    """
    План на выбранное полугодие / semester calendar.
    """
    id_plan: int
    curriculum_id: int
    calendar_id: int
    hours_in_semester: int
    credits: Optional[float] = None
    spread_mode: str = "auto_even"
    comment: Optional[str] = None


@dataclass(frozen=True)
class WeeklyLoadPlan:
    """
    Недельный план нагрузки.
    Используем week_id как первичный ориентир.
    """
    id_week_plan: int
    plan_id: int
    week_id: int
    hours_this_week: int
    week_type: Optional[int] = None
    week_number_in_semester: int = 0
    comment: Optional[str] = None


# ============================================================
# Generated event / schedule solution
# ============================================================

@dataclass(frozen=True)
class Event:
    """
    Одно событие генерации = одна учебная пара,
    которую нужно поставить в сетку расписания.
    """
    id_event: int
    curriculum_id: int
    group_id: int
    subject_id: int
    part_type: str
    required_room_type: str

    fixed_week_number: Optional[int] = None
    fixed_week_type: Optional[int] = None


@dataclass(frozen=True)
class SolutionEntry:
    """
    Итог назначения одного события на конкретный слот/преподавателя/аудиторию.
    """
    event_id: int
    slot_id: int
    teacher_id: int
    room_id: int


@dataclass
class Solution:
    """
    Результат solver.
    """
    entries: List[SolutionEntry] = field(default_factory=list)
    objective_value: int = 0
    meta: dict = field(default_factory=dict)