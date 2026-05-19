from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from app.application.dto.schedule_dto import ScheduleEntryDTO
from app.domain.schedule_validation import GroupScheduleLimits, validate_group_week_entries
from app.domain.exceptions import ValidationError


@dataclass(frozen=True)
class ApplyManualEditCommand:
    """
    Команда ручного редактирования одной записи расписания.

    Редактирование всегда идёт по id_schedule.
    Любое поле можно не передавать — тогда останется текущее значение.
    """

    variant_id: int
    schedule_entry_id: int

    new_slot_id: Optional[int] = None
    new_teacher_id: Optional[int] = None
    new_room_id: Optional[int] = None
    new_group_id: Optional[int] = None
    new_curriculum_id: Optional[int] = None

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
        if self.new_curriculum_id is not None and int(self.new_curriculum_id) <= 0:
            raise ValidationError("new_curriculum_id должен быть положительным числом.")


@dataclass(frozen=True)
class ApplyManualEditResult:
    before: ScheduleEntryDTO
    after: ScheduleEntryDTO
    changed: bool


@dataclass(frozen=True)
class CreateManualEntryCommand:
    variant_id: int
    event_id: int
    curriculum_id: int
    slot_id: int
    group_id: int
    teacher_id: int
    room_id: int
    edited_by: str = "manual_editor"
    comment: Optional[str] = None
    lock_after_edit: bool = True

    def __post_init__(self) -> None:
        if int(self.variant_id) <= 0:
            raise ValidationError("variant_id должен быть положительным числом.")
        if int(self.event_id) <= 0:
            raise ValidationError("event_id должен быть положительным числом.")
        if int(self.curriculum_id) <= 0:
            raise ValidationError("curriculum_id должен быть положительным числом.")
        if int(self.slot_id) <= 0:
            raise ValidationError("slot_id должен быть положительным числом.")
        if int(self.group_id) <= 0:
            raise ValidationError("group_id должен быть положительным числом.")
        if int(self.teacher_id) <= 0:
            raise ValidationError("teacher_id должен быть положительным числом.")
        if int(self.room_id) <= 0:
            raise ValidationError("room_id должен быть положительным числом.")


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
    CREATE_ACTION_NAME = "manual_create"

    def __init__(
        self,
        schedule_repo,
        teachers_repo=None,
        groups_repo=None,
        rooms_repo=None,
        calendar_repo=None,
        rules=None,
    ):
        self._schedule_repo = schedule_repo
        self._teachers_repo = teachers_repo
        self._groups_repo = groups_repo
        self._rooms_repo = rooms_repo
        self._calendar_repo = calendar_repo
        self._rules = rules

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

    def _resolve_curriculum_metadata(
        self,
        curriculum_id: int,
        fallback_subject_id: int,
        fallback_subject_name: str,
        fallback_part_type: str,
    ) -> tuple[int, str, str]:
        getter = getattr(self._schedule_repo, "get_curriculum", None)
        if getter is None:
            return fallback_subject_id, fallback_subject_name, fallback_part_type
        curriculum = getter(int(curriculum_id))
        if curriculum is None:
            return fallback_subject_id, fallback_subject_name, fallback_part_type

        subject_id = self._positive_int(getattr(curriculum, "subject_id", 0), fallback_subject_id)
        part_type = str(getattr(curriculum, "part_type", fallback_part_type) or fallback_part_type)
        subject_name = fallback_subject_name
        session_factory = getattr(self._schedule_repo, "_session_factory", None)
        if subject_id > 0 and session_factory is not None:
            with session_factory() as conn:
                row = conn.execute(
                    "SELECT subject_name FROM Subjects WHERE id_subject=?",
                    (int(subject_id),),
                ).fetchone()
            if row is not None:
                subject_name = str(row[0] or subject_name)
        return subject_id, subject_name, part_type

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
        new_curriculum_id = (
            int(command.new_curriculum_id)
            if command.new_curriculum_id is not None
            else int(original.curriculum_id)
        )
        subject_id, subject_name, part_type = self._resolve_curriculum_metadata(
            new_curriculum_id,
            int(original.subject_id),
            str(original.subject_name),
            str(original.part_type),
        )

        return replace(
            original,
            curriculum_id=new_curriculum_id,
            event_id=0 if new_curriculum_id != int(original.curriculum_id) else int(original.event_id),
            subject_id=subject_id,
            subject_name=subject_name,
            part_type=part_type,
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

        if int(after.curriculum_id) != int(before.curriculum_id):
            getter = getattr(self._schedule_repo, "get_curriculum", None)
            curriculum = getter(int(after.curriculum_id)) if getter is not None else None
            if curriculum is None:
                raise ValidationError("Выбранная дисциплина учебного плана не найдена.")
            if int(getattr(curriculum, "group_id", 0) or 0) != int(after.group_id):
                raise ValidationError("Выбранная дисциплина не относится к текущей группе.")

    def _validate_conflicts(self, entry: ScheduleEntryDTO) -> None:
        variant_id = int(entry.variant_id)
        exclude_entry_id = int(entry.id_schedule)

        if self._schedule_repo.exists_group_conflict(
            variant_id=variant_id,
            group_id=int(entry.group_id),
            slot_id=int(entry.slot_id),
            exclude_entry_id=exclude_entry_id,
            allow_same_event_id=int(entry.event_id) if int(entry.event_id) > 0 else None,
        ):
            raise ValidationError(
                "Конфликт расписания: у группы уже есть занятие в этот слот."
            )

        if self._schedule_repo.exists_teacher_conflict(
            variant_id=variant_id,
            teacher_id=int(entry.teacher_id),
            slot_id=int(entry.slot_id),
            exclude_entry_id=exclude_entry_id,
            allow_same_event_id=int(entry.event_id) if int(entry.event_id) > 0 else None,
        ):
            raise ValidationError(
                "Конфликт расписания: преподаватель уже занят в этот слот."
            )

        if self._schedule_repo.exists_room_conflict(
            variant_id=variant_id,
            room_id=int(entry.room_id),
            slot_id=int(entry.slot_id),
            exclude_entry_id=exclude_entry_id,
            allow_same_event_id=int(entry.event_id) if int(entry.event_id) > 0 else None,
        ):
            raise ValidationError(
                "Конфликт расписания: аудитория уже занята в этот слот."
            )

    def _validate_group_schedule_rules(
        self,
        before: ScheduleEntryDTO,
        after: ScheduleEntryDTO,
    ) -> None:
        variant_entries = list(self._schedule_repo.list_entries(int(after.variant_id)) or [])

        adjusted_entries: list[ScheduleEntryDTO] = []
        for entry in variant_entries:
            if int(entry.id_schedule) == int(before.id_schedule):
                adjusted_entries.append(after)
            else:
                adjusted_entries.append(entry)

        affected_groups = {int(before.group_id), int(after.group_id)}
        affected_week_types = {int(before.week_type), int(after.week_type)}

        limits = GroupScheduleLimits.from_rules(self._rules)

        for group_id in affected_groups:
            if int(group_id) <= 0:
                continue
            for week_type in affected_week_types:
                if int(week_type) <= 0:
                    continue

                errors = validate_group_week_entries(
                    adjusted_entries,
                    group_id=int(group_id),
                    week_type=int(week_type),
                    limits=limits,
                )
                if errors:
                    raise ValidationError(errors[0])

    @staticmethod
    def _is_changed(before: ScheduleEntryDTO, after: ScheduleEntryDTO) -> bool:
        tracked_fields = (
            "slot_id",
            "teacher_id",
            "room_id",
            "group_id",
            "curriculum_id",
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

    def create_entry(self, command: CreateManualEntryCommand) -> ScheduleEntryDTO:
        slot_day_of_week = 0
        slot_pair_number = 0
        slot_week_number = 0
        slot_week_type = 0
        if self._calendar_repo is not None:
            variant = self._schedule_repo.get_variant(int(command.variant_id))
            calendar_id = int(getattr(variant, "calendar_id", 0) or 0) if variant is not None else 0
            if calendar_id > 0:
                for slot in self._calendar_repo.list_time_slots(calendar_id):
                    if int(getattr(slot, "id_slot", 0) or 0) != int(command.slot_id):
                        continue
                    slot_day_of_week = int(getattr(slot, "day_of_week", 0) or 0)
                    slot_pair_number = int(getattr(slot, "pair_number", 0) or 0)
                    slot_week_number = int(getattr(slot, "week_number_in_semester", 0) or 0)
                    slot_week_type = int(getattr(slot, "week_type", 0) or 0)
                    break

        draft_entry = ScheduleEntryDTO(
            id_schedule=0,
            variant_id=int(command.variant_id),
            curriculum_id=int(command.curriculum_id),
            event_id=int(command.event_id),
            slot_id=int(command.slot_id),
            week_number=slot_week_number,
            week_type=slot_week_type,
            day_of_week=slot_day_of_week,
            pair_number=slot_pair_number,
            group_id=int(command.group_id),
            group_name=self._resolve_group_name(int(command.group_id), ""),
            teacher_id=int(command.teacher_id),
            teacher_name=self._resolve_teacher_name(int(command.teacher_id), ""),
            subject_id=0,
            subject_name="",
            part_type="",
            room_id=int(command.room_id),
            room_number=self._resolve_room_name(int(command.room_id), ""),
            is_locked=bool(command.lock_after_edit),
        )

        self._validate_basic_consistency(draft_entry, draft_entry)
        self._validate_conflicts(draft_entry)

        schedule_entry_id = self._schedule_repo.create_entry(draft_entry)
        if command.lock_after_edit:
            self._schedule_repo.lock_entry(
                variant_id=int(command.variant_id),
                schedule_entry_id=int(schedule_entry_id),
                comment=command.comment,
            )

        refreshed = self._schedule_repo.get_entry_by_id(
            int(command.variant_id),
            int(schedule_entry_id),
        )
        if refreshed is None:
            raise ValidationError(
                f"После создания не удалось перечитать запись id={schedule_entry_id}."
            )

        self._schedule_repo.log_edit(
            variant_id=int(command.variant_id),
            edited_by=str(command.edited_by or "manual_editor"),
            action=self.CREATE_ACTION_NAME,
            before=None,
            after=refreshed,
            comment=command.comment,
        )
        return refreshed
