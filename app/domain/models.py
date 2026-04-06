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
    """
    Доменная модель аудитории.

    room_type: основной (приоритетный) тип аудитории.
        Нужен для обратной совместимости и для существующей логики,
        где ожидается один главный тип.

    room_types: полный набор поддерживаемых типов аудитории.
        Это поле используется для корректной работы с аудиториями,
        которые одновременно подходят под несколько типологий
        (например, lecture + lab + computer).
    """
    id_room: int
    room_number: str
    room_type: str
    capacity: int
    building: Optional[str] = None
    room_types: tuple[str, ...] = field(default_factory=tuple)

    @staticmethod
    def parse_room_types(room: Optional['Room']) -> set[str]:
        """
        Парсит типы аудитории из объекта Room.
        
        Поддержка актуальной модели аудитории:
        - сначала читаем room.room_types;
        - если его нет или оно пустое, откатываемся к legacy room.room_type.
        """
        if room is None:
            return set()

        # Сначала пробуем room_types
        raw_room_types = getattr(room, "room_types", None)
        if raw_room_types:
            result = {
                str(x).strip().lower()
                for x in raw_room_types
                if str(x).strip()
            }
            if result:
                return result

        # Откатываемся на room_type
        raw_room_type = getattr(room, "room_type", None)
        if not raw_room_type:
            return set()

        return {
            x.strip().lower()
            for x in str(raw_room_type).split(",")
            if x.strip()
        }

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


@dataclass(frozen=True)
class CurriculumItem:
    id_curriculum: int
    group_id: int
    subject_id: int
    part_type: str
    required_room_type: str


@dataclass(frozen=True)
class SemesterPlan:
    id_plan: int
    curriculum_id: int
    calendar_id: int
    hours_in_semester: int
    credits: Optional[float] = None
    spread_mode: str = "auto_even"
    comment: Optional[str] = None


@dataclass(frozen=True)
class WeeklyLoadPlan:
    id_week_plan: int
    plan_id: int
    week_id: int
    hours_this_week: int
    week_type: Optional[int] = None
    week_number_in_semester: int = 0
    comment: Optional[str] = None


@dataclass(frozen=True)
class Event:
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
    event_id: int
    slot_id: int
    teacher_id: int
    room_id: int


@dataclass
class Solution:
    entries: List[SolutionEntry] = field(default_factory=list)
    objective_value: int = 0
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ScheduleMetrics:
    total_penalty: int
    student_gaps: int
    teacher_gaps: int
    student_overloads: int
    teacher_overloads: int
    method_day_violations: int
    lecture_late_penalty: int