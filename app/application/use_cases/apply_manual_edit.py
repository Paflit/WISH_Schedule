# app/application/use_cases/apply_manual_edit.py
"""
Use-case: ручная корректировка расписания.

Назначение:
- изменить слот / аудиторию / преподавателя для существующей записи
- проверить базовые ограничения (без запуска оптимизатора)
- сохранить изменения в БД
- при необходимости — залогировать изменение

ВАЖНО:
Этот use-case НЕ пересчитывает всё расписание.
Он валидирует только локальные конфликты.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.domain.exceptions import ValidationError
from app.application.dto.schedule_dto import ScheduleEntryDTO


# ------------------------------------------------------------
# Команда редактирования
# ------------------------------------------------------------

@dataclass(frozen=True)
class ApplyManualEditCommand:
    variant_id: int
    schedule_entry_id: int

    new_slot_id: Optional[int] = None
    new_teacher_id: Optional[int] = None
    new_room_id: Optional[int] = None

    lock_after_edit: bool = True
    edited_by: str = "admin"


# ------------------------------------------------------------
# Use-case
# ------------------------------------------------------------

class ApplyManualEditUseCase:
    def __init__(
        self,
        schedule_repo,
        teachers_repo,
        rooms_repo,
        calendar_repo,
    ):
        self._schedule_repo = schedule_repo
        self._teachers_repo = teachers_repo
        self._rooms_repo = rooms_repo
        self._calendar_repo = calendar_repo

    # --------------------------------------------------------

    def execute(self, command: ApplyManualEditCommand) -> ScheduleEntryDTO:
        """
        1) Получаем текущую запись расписания
        2) Применяем изменения
        3) Проверяем конфликты
        4) Сохраняем
        5) Возвращаем обновлённый DTO
        """

        entry = self._schedule_repo.get_entry_by_id(
            command.variant_id,
            command.schedule_entry_id
        )

        if entry is None:
            raise ValidationError("Запись расписания не найдена.")

        updated = entry

        # ----------------------------------------------------
        # Применяем изменения (локально)
        # ----------------------------------------------------
        if command.new_slot_id is not None:
            updated.slot_id = command.new_slot_id

        if command.new_teacher_id is not None:
            updated.teacher_id = command.new_teacher_id

        if command.new_room_id is not None:
            updated.room_id = command.new_room_id

        # ----------------------------------------------------
        # Проверка конфликтов
        # ----------------------------------------------------
        self._validate_no_conflicts(command.variant_id, updated)

        # ----------------------------------------------------
        # Сохранение
        # ----------------------------------------------------
        self._schedule_repo.update_entry(updated)

        if command.lock_after_edit:
            self._schedule_repo.lock_entry(
                variant_id=command.variant_id,
                schedule_entry_id=command.schedule_entry_id,
            )

        # Логирование изменения
        self._schedule_repo.log_edit(
            variant_id=command.variant_id,
            edited_by=command.edited_by,
            action="manual_edit",
            before=entry,
            after=updated,
        )

        return self._schedule_repo.to_dto(updated)

    # --------------------------------------------------------

    def _validate_no_conflicts(self, variant_id: int, entry) -> None:
        """
        Проверяет:
        - группа не занята в этом слоте
        - преподаватель не занят в этом слоте
        - аудитория не занята в этом слоте
        - тип аудитории соответствует дисциплине
        """

        # Конфликт группы
        if self._schedule_repo.exists_group_conflict(
            variant_id=variant_id,
            group_id=entry.group_id,
            slot_id=entry.slot_id,
            exclude_entry_id=entry.id_schedule,
        ):
            raise ValidationError("Группа уже занята в этом слоте.")

        # Конфликт преподавателя
        if self._schedule_repo.exists_teacher_conflict(
            variant_id=variant_id,
            teacher_id=entry.teacher_id,
            slot_id=entry.slot_id,
            exclude_entry_id=entry.id_schedule,
        ):
            raise ValidationError("Преподаватель уже занят в этом слоте.")

        # Конфликт аудитории
        if self._schedule_repo.exists_room_conflict(
            variant_id=variant_id,
            room_id=entry.room_id,
            slot_id=entry.slot_id,
            exclude_entry_id=entry.id_schedule,
        ):
            raise ValidationError("Аудитория уже занята в этом слоте.")

        # Проверка типа аудитории
        curriculum = self._schedule_repo.get_curriculum(entry.curriculum_id)
        room = self._rooms_repo.get_by_id(entry.room_id)

        if curriculum.required_room_type != room.room_type:
            raise ValidationError(
                f"Тип аудитории '{room.room_type}' "
                f"не соответствует требуемому '{curriculum.required_room_type}'."
            )

        # Проверка вместимости
        group = self._schedule_repo.get_group(entry.group_id)
        if room.capacity < group.quantity:
            raise ValidationError(
                f"Вместимость аудитории ({room.capacity}) "
                f"меньше количества студентов ({group.quantity})."
            )