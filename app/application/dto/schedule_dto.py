# app/application/dto/schedule_dto.py
"""
DTO для передачи данных расписания между слоями.

Назначение:
- Presentation (GUI) НЕ должна работать с ORM-моделями.
- Domain сущности тоже не должны утекать в UI напрямую.
- Поэтому UseCase возвращает DTO-структуры.

DTO — это "плоские" dataclass без бизнес-логики.

Важно:
- ScheduleEntryDTO теперь содержит id_schedule — реальный идентификатор записи
  из таблицы ScheduleEntries.
- event_id сохранён для совместимости со старой логикой и местами, где он уже
  используется как ссылка на источник/событие генерации.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ------------------------------------------------------------
# Справочные DTO
# ------------------------------------------------------------

@dataclass(frozen=True)
class TeacherDTO:
    id_teacher: int
    full_name: str


@dataclass(frozen=True)
class GroupDTO:
    id_group: int
    group_name: str


@dataclass(frozen=True)
class RoomDTO:
    id_room: int
    room_number: str
    room_type: str


@dataclass(frozen=True)
class SubjectDTO:
    id_subject: int
    subject_name: str


# ------------------------------------------------------------
# Расписание
# ------------------------------------------------------------

@dataclass(frozen=True)
class ScheduleEntryDTO:
    """
    Одна запись расписания (одна сохранённая строка в ScheduleEntries).

    Ключевые поля:
    - id_schedule: реальный PK записи расписания в БД
    - variant_id: вариант, к которому относится запись
    - curriculum_id: ссылка на CurriculumItems
    - event_id: логический идентификатор события/источника, не заменяет id_schedule
    - slot_id: фактический слот, куда поставлено занятие
    """
    id_schedule: int
    variant_id: int

    # Ссылка на учебный план
    curriculum_id: int

    # Для совместимости со старой логикой
    event_id: int

    # Фактическая привязка
    slot_id: int

    # Позиция в сетке расписания
    week_number: int
    week_type: int
    day_of_week: int
    pair_number: int

    # Группа
    group_id: int
    group_name: str

    # Преподаватель
    teacher_id: int
    teacher_name: str

    # Предмет
    subject_id: int
    subject_name: str
    part_type: str

    # Аудитория
    room_id: int
    room_number: str

    # Признаки
    is_locked: bool = False


@dataclass(frozen=True)
class ScheduleVariantDTO:
    """
    Один вариант расписания.
    """
    id_variant: int
    name: str
    objective_score: int
    entries: List[ScheduleEntryDTO] = field(default_factory=list)


# ------------------------------------------------------------
# Метрики для UI
# ------------------------------------------------------------

@dataclass(frozen=True)
class ScheduleMetricsDTO:
    """
    Метрики варианта для отображения в GUI.
    """
    total_penalty: int

    student_gaps: int
    teacher_gaps: int

    student_overloads: int
    teacher_overloads: int

    method_day_violations: int

    lecture_late_penalty: int


@dataclass(frozen=True)
class GenerationResultDTO:
    """
    Результат генерации (несколько вариантов).
    """
    variants: List[ScheduleVariantDTO] = field(default_factory=list)