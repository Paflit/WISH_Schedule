from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from app.application.dto.schedule_dto import ScheduleEntryDTO
from app.domain.exceptions import ValidationError


@dataclass(frozen=True)
class ApplyManualEditCommand:
    """
    Команда ручного редактирования одной записи расписания.

    Редактирование всегда идёт по id_schedule, а не по event_id.
    Любое поле можно не передавать — тогда останется текущее значение.
    """

    variant_id: int
    schedule_entry_id: int

    new_slot_id: Optional[int] = None
    new_teacher_id: Optional[int] = None
    new_room_id: Optional[int] = None
    new_group_id: Optional[int] = None

    edited_by: str = "manual_editor"
    comment: Optional[str] = None
    lock_after_edit: bool = True

    def __post_init__(self) -> None:
        if int(self.variant_id) <= 0:
            raise ValidationError("variant_id должен быть положительным числом.")
        if int(self.schedule_entry_id) <= 0:
            raise ValidationError("schedule_entry_id должен быть положительным числом.")
        if self.new_slot_id is not None and int(self.new_slot_id) <= 0:
            raise ValidationError("new_slot_id должен быть положительным числом.")
        if self.new_teacher_id is not None and int(self.new_teacher_id) <= 0:
            raise ValidationError("new_teacher_id должен быть положительным числом.")
        if self.new_room_id is not None and int(self.new_room_id) <= 0:
            raise ValidationError("new_room_id должен быть положительным числом.")
        if self.new_group_id is not None and int(self.new_group_id) <= 0:
            raise ValidationError("new_group_id должен быть положительным числом.")


@dataclass(frozen=True)
class ApplyManualEditResult:
    before: ScheduleEntryDTO
    after: ScheduleEntryDTO
    changed: bool


class ApplyManualEditUseCase:
    """
    Ручное редактирование записи готового варианта расписания.

    Гарантии:
    - редактирование идёт по id_schedule;
    - исходный DTO не мутируется;
    - перед сохранением проверяются конфликты:
        * у группы,
        * у преподавателя,
        * у аудитории;
    - после успешной правки изменение логируется;
    - при необходимости запись блокируется.
    """

    ACTION_NAME = "manual_edit"

    def __init__(
        self,
        schedule_repo,
        teachers_repo=None,
        groups_repo=None,
        rooms_repo=None,
        calendar_repo=None,
    ):
        self._schedule_repo = schedule_repo
        self._teachers_repo = teachers_repo
        self._groups_repo = groups_repo
        self._rooms_repo = rooms_repo
        self._calendar_repo = calendar_repo

    @staticmethod
    def _positive_int(value, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)

    def _load_entry(self, variant_id: int, schedule_entry_id: int) -> ScheduleEntryDTO:
        entry = self._schedule_repo.get_entry_by_id(variant_id, schedule_entry_id)
        if entry is None:
            raise ValidationError(
                f"Запись расписания id={schedule_entry_id} в варианте id={variant_id} не найдена."
            )
        return entry

    def _resolve_teacher_name(self, teacher_id: int, fallback: str) -> str:
        if self._teachers_repo is None:
            return fallback
        teacher = self._teachers_repo.get_by_id(teacher_id)
        return getattr(teacher, "full_name", fallback) if teacher is not None else fallback

    def _resolve_group_name(self, group_id: int, fallback: str) -> str:
        if self._groups_repo is None:
            return fallback
        group = self._groups_repo.get_by_id(group_id)
        return getattr(group, "group_name", fallback) if group is not None else fallback

    def _resolve_room_name(self, room_id: int, fallback: str) -> str:
        if self._rooms_repo is None:
            return fallback
        room = self._rooms_repo.get_by_id(room_id)
        return getattr(room, "room_number", fallback) if room is not None else fallback

    def _build_updated_entry(
        self,
        original: ScheduleEntryDTO,
        command: ApplyManualEditCommand,
    ) -> ScheduleEntryDTO:
        new_slot_id = (
            int(command.new_slot_id)
            if command.new_slot_id is not None
            else int(original.slot_id)
        )
        new_teacher_id = (
            int(command.new_teacher_id)
            if command.new_teacher_id is not None
            else int(original.teacher_id)
        )
        new_room_id = (
            int(command.new_room_id)
            if command.new_room_id is not None
            else int(original.room_id)
        )
        new_group_id = (
            int(command.new_group_id)
            if command.new_group_id is not None
            else int(original.group_id)
        )

        return replace(
            original,
            slot_id=new_slot_id,
            teacher_id=new_teacher_id,
            teacher_name=self._resolve_teacher_name(new_teacher_id, original.teacher_name),
            room_id=new_room_id,
            room_number=self._resolve_room_name(new_room_id, original.room_number),
            group_id=new_group_id,
            group_name=self._resolve_group_name(new_group_id, original.group_name),
            is_locked=bool(command.lock_after_edit or original.is_locked),
        )

    def _validate_basic_consistency(
        self,
        before: ScheduleEntryDTO,
        after: ScheduleEntryDTO,
    ) -> None:
        if int(after.variant_id) != int(before.variant_id):
            raise ValidationError("Нельзя перенести запись в другой вариант расписания.")

        if int(after.id_schedule) != int(before.id_schedule):
            raise ValidationError("Нельзя менять id_schedule записи расписания.")

        if int(after.curriculum_id) <= 0:
            raise ValidationError("У записи отсутствует curriculum_id.")

        if int(after.slot_id) <= 0:
            raise ValidationError("Не указан корректный слот.")
        if int(after.teacher_id) <= 0:
            raise ValidationError("Не указан корректный преподаватель.")
        if int(after.room_id) <= 0:
            raise ValidationError("Не указана корректная аудитория.")
        if int(after.group_id) <= 0:
            raise ValidationError("Не указана корректная группа.")

    def _validate_conflicts(self, entry: ScheduleEntryDTO) -> None:
        variant_id = int(entry.variant_id)
        exclude_entry_id = int(entry.id_schedule)

        if self._schedule_repo.exists_group_conflict(
            variant_id=variant_id,
            group_id=int(entry.group_id),
            slot_id=int(entry.slot_id),
            exclude_entry_id=exclude_entry_id,
        ):
            raise ValidationError(
                "Конфликт расписания: у группы уже есть занятие в этот слот."
            )

        if self._schedule_repo.exists_teacher_conflict(
            variant_id=variant_id,
            teacher_id=int(entry.teacher_id),
            slot_id=int(entry.slot_id),
            exclude_entry_id=exclude_entry_id,
        ):
            raise ValidationError(
                "Конфликт расписания: преподаватель уже занят в этот слот."
            )

        if self._schedule_repo.exists_room_conflict(
            variant_id=variant_id,
            room_id=int(entry.room_id),
            slot_id=int(entry.slot_id),
            exclude_entry_id=exclude_entry_id,
        ):
            raise ValidationError(
                "Конфликт расписания: аудитория уже занята в этот слот."
            )

    @staticmethod
    def _is_changed(before: ScheduleEntryDTO, after: ScheduleEntryDTO) -> bool:
        tracked_fields = (
            "slot_id",
            "teacher_id",
            "room_id",
            "group_id",
            "is_locked",
        )
        return any(getattr(before, f) != getattr(after, f) for f in tracked_fields)

    def execute(self, command: ApplyManualEditCommand) -> ApplyManualEditResult:
        before = self._load_entry(
            variant_id=int(command.variant_id),
            schedule_entry_id=int(command.schedule_entry_id),
        )

        after = self._build_updated_entry(before, command)
        self._validate_basic_consistency(before, after)

        changed = self._is_changed(before, after)
        if not changed:
            return ApplyManualEditResult(before=before, after=after, changed=False)

        self._validate_conflicts(after)

        self._schedule_repo.update_entry(after)

        if command.lock_after_edit:
            self._schedule_repo.lock_entry(
                variant_id=int(after.variant_id),
                schedule_entry_id=int(after.id_schedule),
                comment=command.comment,
            )

        refreshed = self._schedule_repo.get_entry_by_id(
            int(after.variant_id),
            int(after.id_schedule),
        )
        if refreshed is None:
            raise ValidationError(
                f"После сохранения не удалось перечитать запись id={after.id_schedule}."
            )

        self._schedule_repo.log_edit(
            variant_id=int(after.variant_id),
            edited_by=str(command.edited_by or "manual_editor"),
            action=self.ACTION_NAME,
            before=before,
            after=refreshed,
            comment=command.comment,
        )

        return ApplyManualEditResult(before=before, after=refreshed, changed=True)