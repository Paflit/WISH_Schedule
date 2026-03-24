from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from app.application.use_cases.apply_manual_edit import (
    ApplyManualEditCommand,
    ApplyManualEditUseCase,
)
from app.application.dto.schedule_dto import ScheduleEntryDTO, ScheduleVariantDTO


@dataclass(frozen=True)
class EditorCellItem:
    """
    Данные одной записи, отображаемой в ячейке сетки.
    """

    id_schedule: int
    variant_id: int
    slot_id: int
    day_of_week: int
    pair_number: int
    week_number: int
    week_type: int

    group_id: int
    group_name: str

    teacher_id: int
    teacher_name: str

    subject_id: int
    subject_name: str
    part_type: str

    room_id: int
    room_number: str

    is_locked: bool

    @classmethod
    def from_dto(cls, dto: ScheduleEntryDTO) -> "EditorCellItem":
        return cls(
            id_schedule=int(dto.id_schedule),
            variant_id=int(dto.variant_id),
            slot_id=int(dto.slot_id),
            day_of_week=int(dto.day_of_week),
            pair_number=int(dto.pair_number),
            week_number=int(dto.week_number),
            week_type=int(dto.week_type),
            group_id=int(dto.group_id),
            group_name=str(dto.group_name),
            teacher_id=int(dto.teacher_id),
            teacher_name=str(dto.teacher_name),
            subject_id=int(dto.subject_id),
            subject_name=str(dto.subject_name),
            part_type=str(dto.part_type),
            room_id=int(dto.room_id),
            room_number=str(dto.room_number),
            is_locked=bool(dto.is_locked),
        )

    @property
    def title(self) -> str:
        if self.part_type:
            return f"{self.subject_name} ({self.part_type})"
        return self.subject_name

    @property
    def subtitle(self) -> str:
        parts = [self.group_name, self.teacher_name, self.room_number]
        return " | ".join(p for p in parts if p).strip()


class EditorViewModel(QObject):
    """
    ViewModel экрана ручного редактирования расписания.

    Принципы:
    - работаем только с id_schedule;
    - источник истины — БД / repository через use case;
    - после редактирования перечитываем вариант заново, а не мутируем локальное состояние;
    - VM не должен редактировать по event_id.
    """

    variantLoaded = pyqtSignal(object)
    entrySelected = pyqtSignal(object)
    editApplied = pyqtSignal(object)
    infoChanged = pyqtSignal(str)
    errorChanged = pyqtSignal(str)

    def __init__(self, schedule_repo, apply_manual_edit_uc: ApplyManualEditUseCase):
        super().__init__()
        self._schedule_repo = schedule_repo
        self._apply_manual_edit_uc = apply_manual_edit_uc

        self._variant_id: Optional[int] = None
        self._variant: Optional[ScheduleVariantDTO] = None
        self._selected_entry: Optional[ScheduleEntryDTO] = None

    # ---------------------------------------------------------
    # Public state
    # ---------------------------------------------------------
    @property
    def current_variant_id(self) -> Optional[int]:
        return self._variant_id

    @property
    def current_variant(self) -> Optional[ScheduleVariantDTO]:
        return self._variant

    @property
    def selected_entry(self) -> Optional[ScheduleEntryDTO]:
        return self._selected_entry

    # ---------------------------------------------------------
    # Load / refresh
    # ---------------------------------------------------------
    def load_variant(self, variant_id: int) -> Optional[ScheduleVariantDTO]:
        variant_id = int(variant_id)
        if variant_id <= 0:
            self._set_error("Некорректный id варианта расписания.")
            return None

        try:
            variant = self._schedule_repo.get_variant_dto(variant_id)
        except Exception as exc:
            self._set_error(f"Не удалось загрузить вариант расписания: {exc}")
            return None

        self._variant_id = variant_id
        self._variant = variant
        self._selected_entry = None

        self.errorChanged.emit("")
        self.infoChanged.emit(
            f"Загружен вариант '{variant.name}', записей: {len(variant.entries)}"
        )
        self.variantLoaded.emit(variant)
        return variant

    def refresh(self) -> Optional[ScheduleVariantDTO]:
        if self._variant_id is None:
            self._set_error("Сначала нужно выбрать вариант расписания.")
            return None
        return self.load_variant(int(self._variant_id))

    # ---------------------------------------------------------
    # Read helpers for UI
    # ---------------------------------------------------------
    def get_entries(self) -> list[ScheduleEntryDTO]:
        if self._variant is None:
            return []
        return list(self._variant.entries)

    def get_cell_items(
        self,
        *,
        day_of_week: Optional[int] = None,
        pair_number: Optional[int] = None,
        week_number: Optional[int] = None,
        week_type: Optional[int] = None,
    ) -> list[EditorCellItem]:
        entries = self.get_entries()
        filtered: list[EditorCellItem] = []

        for e in entries:
            if day_of_week is not None and int(e.day_of_week) != int(day_of_week):
                continue
            if pair_number is not None and int(e.pair_number) != int(pair_number):
                continue
            if week_number is not None and int(e.week_number) != int(week_number):
                continue
            if week_type is not None and int(e.week_type) != int(week_type):
                continue

            filtered.append(EditorCellItem.from_dto(e))

        return filtered

    def get_entry_by_schedule_id(self, schedule_entry_id: int) -> Optional[ScheduleEntryDTO]:
        schedule_entry_id = int(schedule_entry_id)
        if schedule_entry_id <= 0:
            return None

        if self._variant is None:
            return None

        for entry in self._variant.entries:
            if int(entry.id_schedule) == schedule_entry_id:
                return entry
        return None

    def select_entry(self, schedule_entry_id: int) -> Optional[ScheduleEntryDTO]:
        entry = self.get_entry_by_schedule_id(schedule_entry_id)
        if entry is None:
            self._set_error(
                f"Не удалось найти запись расписания id={int(schedule_entry_id)}."
            )
            return None

        self._selected_entry = entry
        self.errorChanged.emit("")
        self.infoChanged.emit(
            f"Выбрана запись id={entry.id_schedule}: {entry.subject_name} / {entry.group_name}"
        )
        self.entrySelected.emit(entry)
        return entry

    # ---------------------------------------------------------
    # Edit operations
    # ---------------------------------------------------------
    def apply_edit(
        self,
        *,
        schedule_entry_id: int,
        new_slot_id: Optional[int] = None,
        new_teacher_id: Optional[int] = None,
        new_room_id: Optional[int] = None,
        new_group_id: Optional[int] = None,
        comment: Optional[str] = None,
        edited_by: str = "manual_editor",
        lock_after_edit: bool = True,
    ) -> Optional[ScheduleEntryDTO]:
        if self._variant_id is None:
            self._set_error("Сначала нужно загрузить вариант расписания.")
            return None

        try:
            command = ApplyManualEditCommand(
                variant_id=int(self._variant_id),
                schedule_entry_id=int(schedule_entry_id),
                new_slot_id=int(new_slot_id) if new_slot_id is not None else None,
                new_teacher_id=int(new_teacher_id) if new_teacher_id is not None else None,
                new_room_id=int(new_room_id) if new_room_id is not None else None,
                new_group_id=int(new_group_id) if new_group_id is not None else None,
                edited_by=str(edited_by or "manual_editor"),
                comment=comment,
                lock_after_edit=bool(lock_after_edit),
            )
            result = self._apply_manual_edit_uc.execute(command)
        except Exception as exc:
            self._set_error(str(exc))
            return None

        # После правки перечитываем вариант полностью из БД
        refreshed = self.load_variant(int(self._variant_id))
        if refreshed is None:
            self._set_error("Правка сохранена, но вариант не удалось перезагрузить.")
            return None

        updated_entry = self.get_entry_by_schedule_id(int(schedule_entry_id))
        if updated_entry is None:
            # fallback на after из use case
            updated_entry = result.after

        if result.changed:
            self.infoChanged.emit(
                f"Изменения сохранены для записи id={int(schedule_entry_id)}."
            )
        else:
            self.infoChanged.emit(
                f"Изменений для записи id={int(schedule_entry_id)} не было."
            )

        self._selected_entry = updated_entry
        self.errorChanged.emit("")
        self.editApplied.emit(updated_entry)
        self.entrySelected.emit(updated_entry)
        return updated_entry

    def move_entry_to_slot(
        self,
        schedule_entry_id: int,
        slot_id: int,
        *,
        comment: Optional[str] = None,
        edited_by: str = "manual_editor",
        lock_after_edit: bool = True,
    ) -> Optional[ScheduleEntryDTO]:
        return self.apply_edit(
            schedule_entry_id=int(schedule_entry_id),
            new_slot_id=int(slot_id),
            comment=comment,
            edited_by=edited_by,
            lock_after_edit=lock_after_edit,
        )

    def change_entry_teacher(
        self,
        schedule_entry_id: int,
        teacher_id: int,
        *,
        comment: Optional[str] = None,
        edited_by: str = "manual_editor",
        lock_after_edit: bool = True,
    ) -> Optional[ScheduleEntryDTO]:
        return self.apply_edit(
            schedule_entry_id=int(schedule_entry_id),
            new_teacher_id=int(teacher_id),
            comment=comment,
            edited_by=edited_by,
            lock_after_edit=lock_after_edit,
        )

    def change_entry_room(
        self,
        schedule_entry_id: int,
        room_id: int,
        *,
        comment: Optional[str] = None,
        edited_by: str = "manual_editor",
        lock_after_edit: bool = True,
    ) -> Optional[ScheduleEntryDTO]:
        return self.apply_edit(
            schedule_entry_id=int(schedule_entry_id),
            new_room_id=int(room_id),
            comment=comment,
            edited_by=edited_by,
            lock_after_edit=lock_after_edit,
        )

    def change_entry_group(
        self,
        schedule_entry_id: int,
        group_id: int,
        *,
        comment: Optional[str] = None,
        edited_by: str = "manual_editor",
        lock_after_edit: bool = True,
    ) -> Optional[ScheduleEntryDTO]:
        return self.apply_edit(
            schedule_entry_id=int(schedule_entry_id),
            new_group_id=int(group_id),
            comment=comment,
            edited_by=edited_by,
            lock_after_edit=lock_after_edit,
        )

    # ---------------------------------------------------------
    # Internal
    # ---------------------------------------------------------
    def _set_error(self, message: str) -> None:
        self.errorChanged.emit(str(message))
        self.infoChanged.emit("")