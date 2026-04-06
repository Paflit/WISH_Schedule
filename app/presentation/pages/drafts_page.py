from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)


DAY_NAMES = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
PART_TYPE_LABELS = {
    "lecture": "Лекция",
    "practice": "Практика",
    "computer_practice": "Комп. практика",
    "lab": "Лабораторная",
}


class DraftEntryDialog(QDialog):
    def __init__(
        self,
        parent,
        *,
        slot_id: int,
        slot_label: str,
        available_events: list[object],
        teachers_repo,
        teacher_part_matrix,
        rooms_repo,
        groups_repo,
        current_entry=None,
        current_event=None,
    ):
        super().__init__(parent)
        self._available_events = list(available_events or [])
        self._selectable_events = self._deduplicate_events(self._available_events)
        self._teachers_repo = teachers_repo
        self._teacher_part_matrix = teacher_part_matrix
        self._rooms_repo = rooms_repo
        self._groups_repo = groups_repo
        self._current_entry = current_entry
        self._current_event = current_event
        self._slot_id = int(slot_id)

        self.setWindowTitle("Редактирование ячейки черновика")
        self.resize(640, 240)

        root = QVBoxLayout(self)

        title = QLabel(f"Слот: <b>{slot_label}</b>")
        title.setWordWrap(True)
        root.addWidget(title)

        form = QFormLayout()
        root.addLayout(form)

        self.event_combo = QComboBox()
        form.addRow("Дисциплина:", self.event_combo)

        self.teacher_combo = QComboBox()
        form.addRow("Преподаватель:", self.teacher_combo)

        self.room_combo = QComboBox()
        form.addRow("Аудитория:", self.room_combo)

        hint = QLabel(
            "Для черновика обязательно закрепляется дисциплина.\n"
            "Преподавателя можно не фиксировать."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #667085;")
        root.addWidget(hint)

        self.button_box = QDialogButtonBox()
        self.save_btn = self.button_box.addButton("Сохранить", QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_btn = self.button_box.addButton("Отмена", QDialogButtonBox.ButtonRole.RejectRole)
        self.clear_btn = None
        if current_entry is not None:
            self.clear_btn = self.button_box.addButton("Очистить ячейку", QDialogButtonBox.ButtonRole.DestructiveRole)
        root.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        if self.clear_btn is not None:
            self.clear_btn.clicked.connect(self._mark_for_delete)
        self.event_combo.currentIndexChanged.connect(self._reload_teachers)
        self.event_combo.currentIndexChanged.connect(self._reload_rooms)

        self._delete_requested = False
        self._load_events()
        self._load_teachers()
        self._load_rooms()
        self._fill_current()

    def _deduplicate_events(self, events: list[object]) -> list[object]:
        unique_events: list[object] = []
        seen_keys: set[tuple[int, str, str, int, int]] = set()

        for event in events or []:
            key = (
                int(getattr(event, "subject_id", 0) or 0),
                str(getattr(event, "part_type", "") or "").strip().lower(),
                str(getattr(event, "required_room_type", "") or "").strip().lower(),
                int(getattr(event, "fixed_week_type", 0) or 0),
                int(getattr(event, "group_id", 0) or 0),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique_events.append(event)

        return unique_events

    def _load_events(self) -> None:
        self.event_combo.clear()
        for event in self._selectable_events:
            subject_name = str(getattr(event, "subject_name", "") or f"ID={int(getattr(event, 'subject_id', 0) or 0)}")
            part_type = PART_TYPE_LABELS.get(str(getattr(event, "part_type", "") or ""), str(getattr(event, "part_type", "") or ""))
            text = f"{subject_name} | {part_type}"
            self.event_combo.addItem(text, int(getattr(event, "id_event", 0) or 0))

    def _load_teachers(self) -> None:
        self._reload_teachers()

    def _load_rooms(self) -> None:
        self._reload_rooms()

    def _reload_teachers(self) -> None:
        self.teacher_combo.clear()
        self.teacher_combo.addItem("Не фиксировать", None)
        event_id = self.event_combo.currentData()
        selected_event = next(
            (e for e in self._selectable_events if int(getattr(e, "id_event", 0) or 0) == int(event_id or 0)),
            None,
        )
        if selected_event is None:
            return

        subject_id = int(getattr(selected_event, "subject_id", 0) or 0)
        part_type = str(getattr(selected_event, "part_type", "") or "")
        for teacher in self._teachers_repo.list_all():
            teacher_id = int(getattr(teacher, "id_teacher", 0) or 0)
            if not self._teacher_part_matrix.get((teacher_id, subject_id, part_type), False):
                continue
            self.teacher_combo.addItem(str(getattr(teacher, "full_name", "") or ""), teacher_id)

    def _reload_rooms(self) -> None:
        self.room_combo.clear()
        self.room_combo.addItem("Не фиксировать", None)
        event_id = self.event_combo.currentData()
        selected_event = next(
            (e for e in self._selectable_events if int(getattr(e, "id_event", 0) or 0) == int(event_id or 0)),
            None,
        )
        if selected_event is None:
            return

        required_room_type = str(getattr(selected_event, "required_room_type", "") or "").strip().lower()
        group_id = int(getattr(selected_event, "group_id", 0) or 0)
        group = self._groups_repo.get_by_id(group_id) if hasattr(self._groups_repo, "get_by_id") else None
        required_capacity = int(getattr(group, "quantity", 0) or 0)

        for room in self._rooms_repo.list_all():
            room_types = getattr(room, "room_types", None)
            if room_types:
                normalized_types = {str(x).strip().lower() for x in room_types if str(x).strip()}
            else:
                raw_type = str(getattr(room, "room_type", "") or "")
                normalized_types = {x.strip().lower() for x in raw_type.split(",") if x.strip()}

            if required_room_type and required_room_type not in normalized_types:
                continue
            if int(getattr(room, "capacity", 0) or 0) < required_capacity:
                continue

            room_label = f"{str(getattr(room, 'room_number', '') or '')} ({int(getattr(room, 'capacity', 0) or 0)} мест)"
            self.room_combo.addItem(room_label, int(getattr(room, "id_room", 0) or 0))

    def _fill_current(self) -> None:
        if self._current_event is not None:
            idx = self.event_combo.findData(int(getattr(self._current_event, "id_event", 0) or 0))
            if idx >= 0:
                self.event_combo.setCurrentIndex(idx)

        if self._current_entry is not None:
            teacher_id = getattr(self._current_entry, "teacher_id", None)
            idx = self.teacher_combo.findData(int(teacher_id) if teacher_id is not None else None)
            if idx >= 0:
                self.teacher_combo.setCurrentIndex(idx)
            room_id = getattr(self._current_entry, "room_id", None)
            idx = self.room_combo.findData(int(room_id) if room_id is not None else None)
            if idx >= 0:
                self.room_combo.setCurrentIndex(idx)

    def _mark_for_delete(self) -> None:
        self._delete_requested = True
        self.accept()

    def get_result(self) -> dict:
        return {
            "delete_requested": bool(self._delete_requested),
            "slot_id": int(self._slot_id),
            "event_id": self.event_combo.currentData(),
            "teacher_id": self.teacher_combo.currentData(),
            "room_id": self.room_combo.currentData(),
        }


class DraftCellFrame(QFrame):
    def __init__(self, *, title: str, subtitle: str = "", draft_entry_id: Optional[int] = None, on_open=None):
        super().__init__()
        self._draft_entry_id = draft_entry_id
        self._on_open = on_open

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            """
            QFrame {
                border: 1px solid #bfc7d5;
                border-radius: 6px;
                background: #f7f9fc;
            }
            QFrame:hover {
                background: #eef3fb;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(3)

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle or "")
        subtitle_label.setWordWrap(True)
        subtitle_label.setStyleSheet("color: #495057;")
        layout.addWidget(subtitle_label)

    def mouseDoubleClickEvent(self, event):
        if callable(self._on_open):
            self._on_open()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if callable(self._on_open):
            self._on_open()
        super().mousePressEvent(event)


class DraftsPage(QWidget):
    def __init__(
        self,
        *,
        schedule_repo,
        calendar_repo,
        event_builder,
        config,
        groups_repo,
        subjects_repo,
        rooms_repo,
        teachers_repo,
    ):
        super().__init__()
        self._schedule_repo = schedule_repo
        self._calendar_repo = calendar_repo
        self._event_builder = event_builder
        self._config = config
        self._groups_repo = groups_repo
        self._subjects_repo = subjects_repo
        self._rooms_repo = rooms_repo
        self._teachers_repo = teachers_repo

        self._events: list[object] = []
        self._events_by_id: dict[int, object] = {}
        self._slots_by_week_day_pair: dict[tuple[int, int, int], int] = {}

        root = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        root.addLayout(top_bar)

        top_bar.addWidget(QLabel("Календарь:"))
        self.calendar_combo = QComboBox()
        top_bar.addWidget(self.calendar_combo, 2)

        self.create_draft_btn = QPushButton("Создать черновик")
        self.delete_draft_btn = QPushButton("Удалить черновик")
        self.refresh_btn = QPushButton("Обновить")
        top_bar.addWidget(self.create_draft_btn)
        top_bar.addWidget(self.delete_draft_btn)
        top_bar.addStretch(1)
        top_bar.addWidget(self.refresh_btn)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        splitter.addWidget(left_panel)

        left_layout.addWidget(QLabel("Черновики"))
        self.draft_combo = QComboBox()
        left_layout.addWidget(self.draft_combo)

        filter_row = QHBoxLayout()
        left_layout.addLayout(filter_row)
        filter_row.addWidget(QLabel("Группа:"))
        self.group_combo = QComboBox()
        filter_row.addWidget(self.group_combo, 2)
        filter_row.addWidget(QLabel("Неделя:"))
        self.week_combo = QComboBox()
        self.week_combo.addItem("1 неделя", 1)
        self.week_combo.addItem("2 неделя", 2)
        filter_row.addWidget(self.week_combo, 1)

        self.info_label = QLabel("Выберите календарь и черновик.")
        self.info_label.setWordWrap(True)
        left_layout.addWidget(self.info_label)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(6, 6, 6, 6)
        self.grid_layout.setSpacing(6)
        left_layout.addWidget(self.grid_container, 1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        splitter.addWidget(right_panel)

        self.selected_cell_label = QLabel("Ячейка не выбрана.")
        self.selected_cell_label.setWordWrap(True)
        right_layout.addWidget(self.selected_cell_label)

        hint = QLabel(
            "Клик по ячейке открывает добавление или редактирование черновика.\n"
            "В черновике обязательно задается дисциплина, преподаватель можно не фиксировать."
        )
        hint.setWordWrap(True)
        right_layout.addWidget(hint)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)
        right_layout.addStretch(1)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)

        self.calendar_combo.currentIndexChanged.connect(self.refresh)
        self.refresh_btn.clicked.connect(self.refresh)
        self.create_draft_btn.clicked.connect(self._create_draft)
        self.delete_draft_btn.clicked.connect(self._delete_draft)
        self.draft_combo.currentIndexChanged.connect(self._render_grid)
        self.group_combo.currentIndexChanged.connect(self._render_grid)
        self.week_combo.currentIndexChanged.connect(self._render_grid)

        self._load_calendars()
        self.refresh()

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet("color: #b42318;" if error else "color: #344054;")

    def _load_calendars(self) -> None:
        self.calendar_combo.blockSignals(True)
        self.calendar_combo.clear()
        for cal in self._calendar_repo.list_calendars():
            label = f"{getattr(cal, 'academic_year', '')} | семестр {getattr(cal, 'semester', '')} (id={getattr(cal, 'id_calendar', '')})"
            self.calendar_combo.addItem(label, int(cal.id_calendar))
        self.calendar_combo.blockSignals(False)

    def _selected_calendar_id(self) -> Optional[int]:
        value = self.calendar_combo.currentData()
        return int(value) if value is not None else None

    def _selected_draft_id(self) -> Optional[int]:
        value = self.draft_combo.currentData()
        return int(value) if value is not None else None

    def _selected_group_id(self) -> Optional[int]:
        value = self.group_combo.currentData()
        return int(value) if value is not None else None

    def _selected_week_type(self) -> int:
        return int(self.week_combo.currentData() or 1)

    def refresh(self) -> None:
        calendar_id = self._selected_calendar_id()
        self.draft_combo.blockSignals(True)
        self.draft_combo.clear()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()

        self._events = []
        self._events_by_id = {}
        self._slots_by_week_day_pair = {}

        if calendar_id is None:
            self.draft_combo.blockSignals(False)
            self.group_combo.blockSignals(False)
            self._render_grid()
            return

        drafts = list(self._schedule_repo.list_generation_drafts(calendar_id=int(calendar_id)) or [])
        for draft in drafts:
            self.draft_combo.addItem(str(getattr(draft, "name", "") or ""), int(getattr(draft, "id_draft", 0) or 0))

        groups = list(self._groups_repo.list_all() or [])
        for group in groups:
            self.group_combo.addItem(str(getattr(group, "group_name", "") or ""), int(getattr(group, "id_group", 0) or 0))

        self._events = list(
            self._event_builder.build_events(
                calendar_id=int(calendar_id),
                hours_per_pair=int(getattr(self._config, "hours_per_pair", 2) or 2),
                locks=[],
            )
        )
        self._events_by_id = {
            int(getattr(event, "id_event", 0) or 0): event
            for event in self._events
            if int(getattr(event, "id_event", 0) or 0) > 0
        }

        seen = set()
        for slot in self._calendar_repo.list_time_slots(int(calendar_id)):
            if bool(getattr(slot, "is_lunch_break", False)):
                continue
            key = (
                int(getattr(slot, "week_type", 0) or 0),
                int(getattr(slot, "day_of_week", 0) or 0),
                int(getattr(slot, "pair_number", 0) or 0),
            )
            if key in seen:
                continue
            seen.add(key)
            self._slots_by_week_day_pair[key] = int(getattr(slot, "id_slot", 0) or 0)

        self.draft_combo.blockSignals(False)
        self.group_combo.blockSignals(False)
        self._render_grid()

    def _clear_grid(self) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _draft_entries_for_selected_context(self) -> dict[tuple[int, int], object]:
        draft_id = self._selected_draft_id()
        group_id = self._selected_group_id()
        week_type = self._selected_week_type()
        result: dict[tuple[int, int], object] = {}
        if draft_id is None or group_id is None:
            return result

        entries = list(self._schedule_repo.list_generation_draft_entries(int(draft_id)) or [])
        for entry in entries:
            event = self._events_by_id.get(int(getattr(entry, "event_id", 0) or 0))
            if event is None:
                continue
            if int(getattr(event, "group_id", 0) or 0) != int(group_id):
                continue
            if int(getattr(event, "fixed_week_type", 0) or 0) != int(week_type):
                continue
            day = int(getattr(entry, "day_of_week", 0) or 0)
            pair = int(getattr(entry, "pair_number", 0) or 0)
            result[(day, pair)] = SimpleNamespace(entry=entry, event=event)
        return result

    def _validate_draft_conflicts(
        self,
        *,
        draft_id: int,
        event_id: int,
        slot_id: int,
        teacher_id: Optional[int],
        room_id: Optional[int],
        current_draft_entry_id: Optional[int] = None,
    ) -> None:
        current_event = self._events_by_id.get(int(event_id))
        if current_event is None:
            raise ValueError("Не удалось определить событие для проверки черновика.")

        current_group_id = int(getattr(current_event, "group_id", 0) or 0)
        entries = list(self._schedule_repo.list_generation_draft_entries(int(draft_id)) or [])
        for entry in entries:
            draft_entry_id = int(getattr(entry, "id_draft_entry", 0) or 0)
            if current_draft_entry_id is not None and draft_entry_id == int(current_draft_entry_id):
                continue
            if int(getattr(entry, "slot_id", 0) or 0) != int(slot_id):
                continue

            other_event = self._events_by_id.get(int(getattr(entry, "event_id", 0) or 0))
            other_group_id = int(getattr(other_event, "group_id", 0) or 0) if other_event is not None else 0

            if other_group_id > 0 and int(other_group_id) == int(current_group_id):
                raise ValueError("У группы уже стоит другое занятие в этот слот.")

            existing_teacher_id = getattr(entry, "teacher_id", None)
            if teacher_id is not None and existing_teacher_id is not None and int(existing_teacher_id) == int(teacher_id):
                raise ValueError("Преподаватель уже занят в этот слот в другом черновом занятии.")

            existing_room_id = getattr(entry, "room_id", None)
            if room_id is not None and existing_room_id is not None and int(existing_room_id) == int(room_id):
                raise ValueError("Аудитория уже занята в этот слот в другом черновом занятии.")

    def _render_grid(self) -> None:
        self._clear_grid()
        calendar_id = self._selected_calendar_id()
        group_id = self._selected_group_id()
        week_type = self._selected_week_type()

        if calendar_id is None:
            self.grid_layout.addWidget(QLabel("Сначала выберите календарь."), 0, 0)
            return

        days = sorted({d for (wt, d, p) in self._slots_by_week_day_pair.keys() if int(wt) == int(week_type)})
        pairs = sorted({p for (wt, d, p) in self._slots_by_week_day_pair.keys() if int(wt) == int(week_type)})

        if not days or not pairs:
            self.grid_layout.addWidget(QLabel("Для выбранной недели нет слотов."), 0, 0)
            return

        group_name = self.group_combo.currentText().strip() if group_id is not None else "Группа"
        corner = QLabel(group_name or "Группа")
        corner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        corner.setStyleSheet("font-weight: 600;")
        self.grid_layout.addWidget(corner, 0, 0)

        day_columns = []
        for col_idx, day in enumerate(days, start=1):
            header = QLabel(DAY_NAMES.get(day, str(day)))
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setStyleSheet("font-weight: 600;")
            self.grid_layout.addWidget(header, 0, col_idx)
            day_columns.append((day, col_idx))

        pair_rows = []
        for row_idx, pair in enumerate(pairs, start=1):
            pair_label = QLabel(f"{pair} пара")
            pair_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pair_label.setStyleSheet("font-weight: 600;")
            self.grid_layout.addWidget(pair_label, row_idx, 0)
            pair_rows.append((pair, row_idx))

        entries_by_cell = self._draft_entries_for_selected_context()

        for pair, row_idx in pair_rows:
            for day, col_idx in day_columns:
                slot_id = self._slots_by_week_day_pair.get((int(week_type), int(day), int(pair)))
                if slot_id is None:
                    self.grid_layout.addWidget(QLabel("—"), row_idx, col_idx)
                    continue

                payload = entries_by_cell.get((int(day), int(pair)))
                if payload is None:
                    cell = DraftCellFrame(
                        title="Пусто",
                        subtitle="Нажмите для добавления",
                        on_open=lambda sid=slot_id, d=day, p=pair: self._open_cell_editor(sid, d, p),
                    )
                else:
                    entry = payload.entry
                    event = payload.event
                    subject_id = int(getattr(event, "subject_id", 0) or 0)
                    subject = next((s for s in self._subjects_repo.list_all() if int(getattr(s, "id_subject", 0) or 0) == subject_id), None)
                    subject_name = str(getattr(subject, "subject_name", f"ID={subject_id}") or f"ID={subject_id}")
                    part_type = PART_TYPE_LABELS.get(str(getattr(event, "part_type", "") or ""), str(getattr(event, "part_type", "") or ""))
                    teacher_name = str(getattr(entry, "teacher_name", "") or "Преподаватель не закреплен")
                    room_name = str(getattr(entry, "room_number", "") or "Аудитория не закреплена")
                    cell = DraftCellFrame(
                        title=f"{subject_name} ({part_type})",
                        subtitle=f"{teacher_name} | {room_name}",
                        draft_entry_id=int(getattr(entry, "id_draft_entry", 0) or 0),
                        on_open=lambda sid=slot_id, d=day, p=pair: self._open_cell_editor(sid, d, p),
                    )
                self.grid_layout.addWidget(cell, row_idx, col_idx)

    def _events_for_group_week(self, group_id: int, week_type: int) -> list[object]:
        subjects_by_id = {int(getattr(s, "id_subject", 0) or 0): s for s in self._subjects_repo.list_all()}
        draft_id = self._selected_draft_id()
        used_event_ids: set[int] = set()
        if draft_id is not None:
            for draft_entry in self._schedule_repo.list_generation_draft_entries(int(draft_id)) or []:
                used_event_ids.add(int(getattr(draft_entry, "event_id", 0) or 0))

        events = []
        for event in self._events:
            if int(getattr(event, "group_id", 0) or 0) != int(group_id):
                continue
            if int(getattr(event, "fixed_week_type", 0) or 0) != int(week_type):
                continue
            if int(getattr(event, "id_event", 0) or 0) in used_event_ids:
                continue
            subject_id = int(getattr(event, "subject_id", 0) or 0)
            subject = subjects_by_id.get(subject_id)
            enriched = SimpleNamespace(**event.__dict__)
            enriched.subject_name = str(getattr(subject, "subject_name", f"ID={subject_id}") or f"ID={subject_id}")
            events.append(enriched)
        events.sort(key=lambda e: (str(getattr(e, "subject_name", "") or ""), str(getattr(e, "part_type", "") or ""), int(getattr(e, "id_event", 0) or 0)))
        return events

    def _open_cell_editor(self, slot_id: int, day: int, pair: int) -> None:
        draft_id = self._selected_draft_id()
        group_id = self._selected_group_id()
        week_type = self._selected_week_type()
        if draft_id is None or group_id is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите черновик и группу.")
            return

        entries_by_cell = self._draft_entries_for_selected_context()
        payload = entries_by_cell.get((int(day), int(pair)))
        current_entry = payload.entry if payload is not None else None
        current_event = payload.event if payload is not None else None
        slot_label = f"{DAY_NAMES.get(int(day), str(day))}, {int(pair)} пара, неделя {int(week_type)}"

        available_events = self._events_for_group_week(int(group_id), int(week_type))
        if current_event is not None:
            available_events.append(current_event)
            available_events.sort(key=lambda e: (str(getattr(e, "subject_name", "") or ""), str(getattr(e, "part_type", "") or ""), int(getattr(e, "id_event", 0) or 0)))

        if not available_events:
            QMessageBox.warning(
                self,
                "Превышение учебного плана",
                "Для выбранной группы и недели все допустимые занятия уже размещены в черновике."
            )
            return

        dlg = DraftEntryDialog(
            self,
            slot_id=int(slot_id),
            slot_label=slot_label,
            available_events=available_events,
            teachers_repo=self._teachers_repo,
            teacher_part_matrix=self._teachers_repo.get_teacher_part_matrix(),
            rooms_repo=self._rooms_repo,
            groups_repo=self._groups_repo,
            current_entry=current_entry,
            current_event=current_event,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        result = dlg.get_result()
        self.selected_cell_label.setText(f"Выбрана ячейка: {slot_label}")

        if result["delete_requested"]:
            if current_entry is not None:
                self._schedule_repo.delete_generation_draft_entry(int(getattr(current_entry, "id_draft_entry", 0) or 0))
            self._render_grid()
            return

        event_id = result.get("event_id")
        if event_id is None:
            QMessageBox.warning(self, "Ошибка", "Нужно выбрать дисциплину для черновика.")
            return

        try:
            self._validate_draft_conflicts(
                draft_id=int(draft_id),
                event_id=int(event_id),
                slot_id=int(result["slot_id"]),
                teacher_id=int(result["teacher_id"]) if result.get("teacher_id") is not None else None,
                room_id=int(result["room_id"]) if result.get("room_id") is not None else None,
                current_draft_entry_id=int(getattr(current_entry, "id_draft_entry", 0) or 0) if current_entry is not None else None,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Конфликт черновика", str(exc))
            return

        self._schedule_repo.upsert_generation_draft_entry(
            draft_id=int(draft_id),
            event_id=int(event_id),
            slot_id=int(result["slot_id"]),
            teacher_id=int(result["teacher_id"]) if result.get("teacher_id") is not None else None,
            room_id=int(result["room_id"]) if result.get("room_id") is not None else None,
            comment=None,
        )
        self._render_grid()

    def _create_draft(self) -> None:
        calendar_id = self._selected_calendar_id()
        if calendar_id is None:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите календарь.")
            return
        name, ok = QInputDialog.getText(self, "Новый черновик", "Название черновика:")
        if not ok or not str(name).strip():
            return
        draft_id = self._schedule_repo.create_generation_draft(int(calendar_id), str(name).strip())
        self.refresh()
        idx = self.draft_combo.findData(int(draft_id))
        if idx >= 0:
            self.draft_combo.setCurrentIndex(idx)

    def _delete_draft(self) -> None:
        draft_id = self._selected_draft_id()
        if draft_id is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите черновик.")
            return
        self._schedule_repo.delete_generation_draft(int(draft_id))
        self.refresh()
