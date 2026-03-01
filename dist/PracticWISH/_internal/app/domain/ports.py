# app/domain/ports.py
"""
Domain Ports (абстракции).

Здесь описываются интерфейсы (контракты), через которые
application слой взаимодействует с инфраструктурой.

Зачем это нужно:
- application и domain НЕ зависят от SQLite
- можно заменить БД (Postgres, API, mock)
- можно тестировать use-cases без реальной БД
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional

from app.domain.models import (
    Teacher,
    StudentGroup,
    Subject,
    Room,
    TimeSlot,
    CurriculumItem,
    Event,
    Solution,
)
from app.application.dto.schedule_dto import ScheduleVariantDTO


# ============================================================
# Teachers
# ============================================================

class TeachersRepositoryPort(ABC):

    @abstractmethod
    def list_all(self) -> List[Teacher]:
        pass

    @abstractmethod
    def get_teacher_subject_matrix(self) -> Dict[Tuple[int, int], bool]:
        """
        Возвращает dict[(teacher_id, subject_id)] -> True
        """
        pass

    @abstractmethod
    def get_availability_matrix(self, calendar_id: int) -> Dict[Tuple[int, int], bool]:
        """
        dict[(teacher_id, slot_id)] -> is_available
        """
        pass


# ============================================================
# Groups
# ============================================================

class GroupsRepositoryPort(ABC):

    @abstractmethod
    def list_all(self) -> List[StudentGroup]:
        pass


# ============================================================
# Subjects
# ============================================================

class SubjectsRepositoryPort(ABC):

    @abstractmethod
    def list_all(self) -> List[Subject]:
        pass


# ============================================================
# Rooms
# ============================================================

class RoomsRepositoryPort(ABC):

    @abstractmethod
    def list_all(self) -> List[Room]:
        pass

    @abstractmethod
    def get_by_id(self, room_id: int) -> Optional[Room]:
        pass


# ============================================================
# Calendar
# ============================================================

class CalendarRepositoryPort(ABC):

    @abstractmethod
    def get_calendar(self, calendar_id: int):
        pass

    @abstractmethod
    def list_time_slots(self, calendar_id: int) -> List[TimeSlot]:
        pass


# ============================================================
# Curriculum
# ============================================================

class CurriculumRepositoryPort(ABC):

    @abstractmethod
    def list_curriculum_items(self, calendar_id: int) -> List[CurriculumItem]:
        pass

    @abstractmethod
    def build_events(
        self,
        calendar_id: int,
        hours_per_pair: int,
    ) -> List[Event]:
        """
        Возвращает список Event для оптимизации.
        """
        pass


# ============================================================
# Schedule
# ============================================================

class ScheduleRepositoryPort(ABC):

    @abstractmethod
    def create_variant(
        self,
        calendar_id: int,
        rule_profile_key: str,
        name: str,
        objective_score: int,
        created_by: str,
    ) -> int:
        pass

    @abstractmethod
    def save_solution_entries(
        self,
        variant_id: int,
        solution_entries: List,
    ) -> None:
        pass

    @abstractmethod
    def get_variant_dto(self, variant_id: int) -> ScheduleVariantDTO:
        pass

    @abstractmethod
    def list_locks_for_calendar(self, calendar_id: int):
        pass


# ============================================================
# Solver
# ============================================================

class ScheduleSolverPort(ABC):

    @abstractmethod
    def solve(
        self,
        teachers: List[Teacher],
        groups: List[StudentGroup],
        rooms: List[Room],
        slots: List[TimeSlot],
        curriculum: Dict[int, CurriculumItem],
        events: List[Event],
        teacher_subjects: Dict[Tuple[int, int], bool],
        teacher_availability: Dict[Tuple[int, int], bool],
        rules,
        k_solutions: int,
        time_limit_seconds: int,
        random_seed: int,
        locks=None,
    ) -> List[Solution]:
        pass