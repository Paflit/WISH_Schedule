from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.application.dto.schedule_dto import ScheduleEntryDTO


DAY_NAMES = {
    1: "Пн",
    2: "Вт",
    3: "Ср",
    4: "Чт",
    5: "Пт",
    6: "Сб",
    7: "Вс",
}

PART_TYPE_LABELS = {
    "lecture": "Лекция",
    "practice": "Практика",
    "computer_practice": "Комп. практика",
    "lab": "Лабораторная",
}


@dataclass(frozen=True)
class GridCellEntry:
    id_schedule: int
    variant_id: int
    slot_id: int
    week_number: int
    week_type: int
    day_of_week: int
    pair_number: int

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
    def from_dto(cls, dto: ScheduleEntryDTO) -> "GridCellEntry":
        return cls(
            id_schedule=int(dto.id_schedule),
            variant_id=int(dto.variant_id),
            slot_id=int(dto.slot_id),
            week_number=int(dto.week_number),
            week_type=int(dto.week_type),
            day_of_week=int(dto.day_of_week),
            pair_number=int(dto.pair_number),
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
    def part_label(self) -> str:
        return PART_TYPE_LABELS.get(self.part_type, self.part_type or "—")

    def title_for_mode(self, mode: str) -> str:
        return self.subject_name

    def subtitle_for_mode(self, mode: str) -> str:
        if mode == "teacher":
            parts = [self.group_name, self.room_number, self.part_label]
        elif mode == "room":
            parts = [self.group_name, self.teacher_name, self.part_label]
        else:
            parts = [self.teacher_name, self.room_number, self.part_label]
        return " | ".join(p for p in parts if p)


class ScheduleEntryCard(QFrame):
    clicked = pyqtSignal(int)
    doubleClicked = pyqtSignal(int)

    def __init__(self, entry: GridCellEntry, mode: str):
        super().__init__()
        self.entry = entry
        self.mode = mode

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            """
            QFrame {
                border: 1px solid #c9d2e3;
                border-radius: 8px;
                background: #f8fbff;
            }
            QFrame:hover {
                background: #eef4ff;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(3)

        title = QLabel(self.entry.title_for_mode(mode))
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: 600;")
        root.addWidget(title)

        subtitle = QLabel(self.entry.subtitle_for_mode(mode))
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #475467; font-size: 12px;")
        root.addWidget(subtitle)

        if self.entry.is_locked:
            lock_label = QLabel("🔒 Зафиксировано")
            lock_label.setStyleSheet("color: #8a5a00; font-size: 11px;")
            root.addWidget(lock_label)

    def mousePressEvent(self, event):
        self.clicked.emit(int(self.entry.id_schedule))
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit(int(self.entry.id_schedule))
        super().mouseDoubleClickEvent(event)


class ScheduleCellWidget(QWidget):
    entryClicked = pyqtSignal(int)
    entryDoubleClicked = pyqtSignal(int)

    def __init__(self, entries: list[GridCellEntry], mode: str):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(4)

        if not entries:
            empty = QLabel("—")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #98a2b3;")
            root.addWidget(empty)
            return

        for entry in entries:
            card = ScheduleEntryCard(entry, mode)
            card.clicked.connect(self.entryClicked.emit)
            card.doubleClicked.connect(self.entryDoubleClicked.emit)
            root.addWidget(card)

        root.addStretch(1)


class ScheduleGrid(QWidget):
    """
    Универсальная сетка расписания.

    Возможности:
    - отображение по группам / преподавателям / аудиториям;
    - фильтр по конкретной сущности выбранного режима;
    - фильтр по неделе и типу недели;
    - хранение и показ нескольких занятий в одной ячейке;
    - работа с id_schedule как главным идентификатором записи.

    Ожидаемые данные:
    - список ScheduleEntryDTO
    """

    entryClicked = pyqtSignal(int)
    entryDoubleClicked = pyqtSignal(int)

    VIEW_MODES = [
        ("По группам", "group"),
        ("По преподавателям", "teacher"),
        ("По аудиториям", "room"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        self._entries: list[ScheduleEntryDTO] = []
        self._on_open: Optional[Callable[[int], None]] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        toolbar = QHBoxLayout()
        root.addLayout(toolbar)

        toolbar.addWidget(QLabel("Режим:"))

        self.view_mode_combo = QComboBox()
        for label, value in self.VIEW_MODES:
            self.view_mode_combo.addItem(label, value)
        toolbar.addWidget(self.view_mode_combo)

        toolbar.addWidget(QLabel("Сущность:"))
        self.entity_combo = QComboBox()
        toolbar.addWidget(self.entity_combo)

        toolbar.addWidget(QLabel("Неделя:"))
        self.week_combo = QComboBox()
        self.week_combo.addItem("Все недели", None)
        toolbar.addWidget(self.week_combo)

        toolbar.addWidget(QLabel("Тип недели:"))
        self.week_type_combo = QComboBox()
        self.week_type_combo.addItem("Все типы недель", None)
        self.week_type_combo.addItem("Числитель", 1)
        self.week_type_combo.addItem("Знаменатель", 2)
        toolbar.addWidget(self.week_type_combo)

        toolbar.addStretch(1)

        self.summary_label = QLabel("Нет данных для отображения.")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        root.addWidget(self.scroll, 1)

        self.grid_host = QWidget()
        self.grid_layout = QGridLayout(self.grid_host)
        self.grid_layout.setContentsMargins(6, 6, 6, 6)
        self.grid_layout.setSpacing(6)
        self.scroll.setWidget(self.grid_host)

        self.view_mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.entity_combo.currentIndexChanged.connect(self._render)
        self.week_combo.currentIndexChanged.connect(self._on_week_changed)
        self.week_type_combo.currentIndexChanged.connect(self._on_week_type_changed)

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------
    def set_entries(self, entries: Iterable[ScheduleEntryDTO]) -> None:
        self._entries = list(entries or [])
        self._rebuild_week_filter()
        self._rebuild_entity_filter()
        self._render()

    def clear(self) -> None:
        self._entries = []
        self._rebuild_week_filter()
        self._rebuild_entity_filter()
        self._render()

    def set_open_handler(self, callback: Optional[Callable[[int], None]]) -> None:
        self._on_open = callback

    def current_view_mode(self) -> str:
        return str(self.view_mode_combo.currentData() or "group")

    def selected_entity(self) -> Optional[tuple[str, int]]:
        value = self.entity_combo.currentData()
        if isinstance(value, tuple) and len(value) == 2:
            return value
        return None

    def selected_week(self) -> Optional[int]:
        value = self.week_combo.currentData()
        return int(value) if value is not None else None

    def selected_week_type(self) -> Optional[int]:
        value = self.week_type_combo.currentData()
        return int(value) if value is not None else None

    # ---------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------
    def _entity_key(self, entry: GridCellEntry, mode: str) -> tuple[str, int]:
        if mode == "teacher":
            return (entry.teacher_name or "—", int(entry.teacher_id))
        if mode == "room":
            return (entry.room_number or "—", int(entry.room_id))
        return (entry.group_name or "—", int(entry.group_id))

    def _rebuild_week_filter(self) -> None:
        weeks = sorted({int(e.week_number) for e in self._entries if int(e.week_number) > 0})

        self.week_combo.blockSignals(True)
        current = self.week_combo.currentData()
        self.week_combo.clear()
        self.week_combo.addItem("Все недели", None)
        for week in weeks:
            self.week_combo.addItem(f"Неделя {week}", week)

        idx = self.week_combo.findData(current)
        self.week_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.week_combo.blockSignals(False)

    def _rebuild_entity_filter(self) -> None:
        mode = self.current_view_mode()
        current = self.entity_combo.currentData()

        entries = self._filtered_entries_without_entity()
        entities = sorted(
            {self._entity_key(e, mode) for e in entries},
            key=lambda x: (x[0].lower(), x[1]),
        )

        self.entity_combo.blockSignals(True)
        self.entity_combo.clear()

        for label, entity_id in entities:
            self.entity_combo.addItem(label, (label, entity_id))

        if entities:
            idx = self.entity_combo.findData(current)
            self.entity_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self.entity_combo.blockSignals(False)

    def _on_mode_changed(self) -> None:
        self._rebuild_entity_filter()
        self._render()

    def _on_week_changed(self) -> None:
        self._rebuild_entity_filter()
        self._render()

    def _on_week_type_changed(self) -> None:
        self._rebuild_entity_filter()
        self._render()

    def _clear_grid(self) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _filtered_entries_without_entity(self) -> list[GridCellEntry]:
        week_number = self.selected_week()
        week_type = self.selected_week_type()

        result: list[GridCellEntry] = []
        for dto in self._entries:
            if week_number is not None and int(dto.week_number) != int(week_number):
                continue
            if week_type is not None and int(dto.week_type) != int(week_type):
                continue
            result.append(GridCellEntry.from_dto(dto))
        return result

    def _filtered_entries(self) -> list[GridCellEntry]:
        mode = self.current_view_mode()
        selected_entity = self.selected_entity()

        entries = self._filtered_entries_without_entity()
        if selected_entity is None:
            return []

        return [e for e in entries if self._entity_key(e, mode) == selected_entity]

    def _render(self) -> None:
        self._clear_grid()

        entries = self._filtered_entries_without_entity()
        if not entries:
            self.summary_label.setText("Нет записей для выбранного фильтра.")
            self.grid_layout.addWidget(QLabel("Нет данных."), 0, 0)
            return

        mode = self.current_view_mode()
        selected_entity = self.selected_entity()

        if selected_entity is None:
            self.summary_label.setText("Выберите сущность для отображения.")
            self.grid_layout.addWidget(QLabel("Выберите сущность."), 0, 0)
            return

        entries = [e for e in entries if self._entity_key(e, mode) == selected_entity]
        if not entries:
            self.summary_label.setText("Нет записей для выбранной сущности.")
            self.grid_layout.addWidget(QLabel("Нет данных."), 0, 0)
            return

        days = sorted({int(e.day_of_week) for e in entries})
        pairs = sorted({int(e.pair_number) for e in entries})

        grouped: dict[tuple[int, int], list[GridCellEntry]] = defaultdict(list)
        for entry in entries:
            grouped[(int(entry.day_of_week), int(entry.pair_number))].append(entry)

        self.grid_layout.addWidget(QLabel("Сущность / день"), 0, 0)

        column_map: list[tuple[int, int, int]] = []
        col = 1
        for day in days:
            for pair in pairs:
                header = QLabel(f"{DAY_NAMES.get(day, str(day))}\n{pair} пара")
                header.setAlignment(Qt.AlignmentFlag.AlignCenter)
                header.setStyleSheet("font-weight: 600;")
                self.grid_layout.addWidget(header, 0, col)
                column_map.append((day, pair, col))
                col += 1

        entity_label = QLabel(selected_entity[0])
        entity_label.setStyleSheet("font-weight: 600;")
        entity_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid_layout.addWidget(entity_label, 1, 0)

        for day, pair, col_idx in column_map:
            cell_entries = grouped.get((day, pair), [])
            cell_entries = sorted(
                cell_entries,
                key=lambda e: (
                    e.subject_name.lower(),
                    e.teacher_name.lower(),
                    e.room_number.lower(),
                    e.group_name.lower(),
                    e.id_schedule,
                ),
            )

            cell = ScheduleCellWidget(cell_entries, mode)
            cell.entryClicked.connect(self._handle_entry_clicked)
            cell.entryDoubleClicked.connect(self._handle_entry_double_clicked)
            self.grid_layout.addWidget(cell, 1, col_idx)

        self.summary_label.setText(
            f"Режим: {self.view_mode_combo.currentText()} | "
            f"сущность: {selected_entity[0]} | "
            f"записей: {len(entries)}"
        )

    def _handle_entry_clicked(self, schedule_entry_id: int) -> None:
        self.entryClicked.emit(int(schedule_entry_id))

    def _handle_entry_double_clicked(self, schedule_entry_id: int) -> None:
        self.entryDoubleClicked.emit(int(schedule_entry_id))
        if callable(self._on_open):
            self._on_open(int(schedule_entry_id))