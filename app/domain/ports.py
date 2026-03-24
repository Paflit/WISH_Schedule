from __future__ import annotations

from typing import Protocol, Dict, Tuple, Optional, List

from app.domain.models import (
    Teacher,
    StudentGroup,
    Subject,
    Room,
    AcademicCalendar,
    SemesterWeek,
    TimeSlot,
    CurriculumItem,
    SemesterPlan,
    WeeklyLoadPlan,
    Event,
    Solution,
)

class TeachersRepositoryPort(Protocol):
    def list_all(self) -> List[Teacher]:
        ...

    def get_teacher_part_matrix(self) -> Dict[Tuple[int, int, str], bool]:
        """
        Матрица допуска преподавателя по дисциплине и типу занятия:
        (teacher_id, subject_id, part_type) -> bool
        """
        ...

    def get_availability_matrix(self, calendar_id: int) -> Dict[Tuple[int, int], bool]:
        """
        Доступность преподавателя по слотам:
        (teacher_id, slot_id) -> is_available
        """
        ...


# ============================================================
# Groups / Subjects / Rooms
# ============================================================

class GroupsRepositoryPort(Protocol):
    def list_all(self) -> List[StudentGroup]:
        ...


class SubjectsRepositoryPort(Protocol):
    def list_all(self) -> List[Subject]:
        ...


class RoomsRepositoryPort(Protocol):
    def list_all(self) -> List[Room]:
        ...


# ============================================================
# Calendar
# ============================================================

class CalendarRepositoryPort(Protocol):
    def list_all(self) -> List[AcademicCalendar]:
        ...

    def get_calendar(self, calendar_id: int) -> Optional[AcademicCalendar]:
        ...

    def list_time_slots(self, calendar_id: int) -> List[TimeSlot]:
        ...


# ============================================================
# Curriculum
# ============================================================

class CurriculumRepositoryPort(Protocol):
    def list_curriculum_items(self, calendar_id: int) -> List[CurriculumItem]:
        """
        Совместимый метод для старых частей системы.
        Возвращает только те CurriculumItem, которые участвуют
        в выбранном полугодии.
        """
        ...

    def get_semester_plans(self, calendar_id: int):
        """
        Возвращает semester plans выбранного полугодия.
        Допускается возврат объектов с доступом через точку
        (например, SimpleNamespace) либо явных SemesterPlan.
        """
        ...

    def get_curriculum_items_for_plans(self, plans_or_calendar_id):
        """
        Возвращает словарь:
            {curriculum_id: curriculum_item}
        где curriculum_item имеет поля:
        - id_curriculum
        - group_id
        - subject_id
        - part_type
        - required_room_type
        """
        ...

    def get_weekly_plans(self, calendar_id: int):
        """
        Возвращает weekly load plan выбранного полугодия.
        """
        ...

    def get_hours_for_curriculum(self, calendar_id: int) -> Dict[int, int]:
        """
        {curriculum_id: hours_in_semester}
        """
        ...


# ============================================================
# Schedule variants
# ============================================================

class ScheduleRepositoryPort(Protocol):
    def create_variant(
        self,
        calendar_id: int,
        rule_profile_key: str,
        name: str,
        objective_score: int,
        created_by: str,
    ) -> int:
        ...

    def save_solution_entries(self, variant_id: int, solution_entries) -> None:
        ...

    def get_variant_dto(self, variant_id: int):
        ...

    def list_variants(self, calendar_id: Optional[int] = None):
        ...

    def list_locks_for_calendar(self, calendar_id: int):
        ...


# ============================================================
# Event builder
# ============================================================

class EventBuilderPort(Protocol):
    def build_events(
        self,
        calendar_id: int,
        hours_per_pair: int,
        locks: Optional[list] = None,
    ) -> List[Event]:
        ...


# ============================================================
# Rule profiles
# ============================================================

class RuleProfilesPort(Protocol):
    def get(self, key: str):
        ...

    def list_keys(self) -> List[str]:
        ...


# ============================================================
# Solver
# ============================================================

class ScheduleSolverPort(Protocol):
    def solve(
        self,
        teachers: List[Teacher],
        groups: List[StudentGroup],
        rooms: List[Room],
        slots: List[TimeSlot],
        curriculum,
        events: List[Event],
        teacher_subjects: Dict[Tuple[int, int, str], bool],
        teacher_availability: Dict[Tuple[int, int], bool],
        rules,
        k_solutions: int = 1,
        time_limit_seconds: int = 1200,
        random_seed: Optional[int] = None,
        locks: Optional[list] = None,
    ) -> List[Solution]:
        ...