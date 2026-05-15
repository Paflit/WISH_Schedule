from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from app.presentation.viewmodels.editor_vm import EditorCellItem, EditorViewModel
from app.presentation.pages.drafts_page import DraftEntryDialog


DAY_NAMES = {
    1: "Пн",
    2: "Вт",
    3: "Ср",
    4: "Чт",
    5: "Пт",
    6: "Сб",
    7: "Вс",
}


class EntryEditDialog(QDialog):
    def __init__(self, parent, vm: EditorViewModel, entry_id: int):
        super().__init__(parent)
        self._vm = vm
        self._entry_id = int(entry_id)
        self._entry = self._vm.get_entry_by_schedule_id(self._entry_id)

        self.setWindowTitle("Редактирование занятия")
        self.setModal(True)
        self.resize(520, 260)

        layout = QVBoxLayout(self)

        self._title = QLabel()
        self._title.setWordWrap(True)
        layout.addWidget(self._title)

        form = QFormLayout()
        layout.addLayout(form)

        self.slot_btn = QPushButton("Выбрать слот…")
        self.teacher_btn = QPushButton("Выбрать преподавателя…")
        self.room_btn = QPushButton("Выбрать аудиторию…")
        self.group_btn = QPushButton("Выбрать группу…")

        self.slot_value = QLabel("—")
        self.teacher_value = QLabel("—")
        self.room_value = QLabel("—")
        self.group_value = QLabel("—")

        slot_row = QHBoxLayout()
        slot_row.addWidget(self.slot_value, 1)
        slot_row.addWidget(self.slot_btn)

        teacher_row = QHBoxLayout()
        teacher_row.addWidget(self.teacher_value, 1)
        teacher_row.addWidget(self.teacher_btn)

        room_row = QHBoxLayout()
        room_row.addWidget(self.room_value, 1)
        room_row.addWidget(self.room_btn)

        group_row = QHBoxLayout()
        group_row.addWidget(self.group_value, 1)
        group_row.addWidget(self.group_btn)

        form.addRow("Слот:", self._wrap(slot_row))
        form.addRow("Преподаватель:", self._wrap(teacher_row))
        form.addRow("Аудитория:", self._wrap(room_row))
        form.addRow("Группа:", self._wrap(group_row))

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.save_btn = QPushButton("Сохранить")
        self.cancel_btn = QPushButton("Отмена")
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.cancel_btn)
        layout.addLayout(buttons)

        self._new_slot_id: Optional[int] = None
        self._new_teacher_id: Optional[int] = None
        self._new_room_id: Optional[int] = None
        self._new_group_id: Optional[int] = None

        self.slot_btn.clicked.connect(self._choose_slot)
        self.teacher_btn.clicked.connect(self._choose_teacher)
        self.room_btn.clicked.connect(self._choose_room)
        self.group_btn.clicked.connect(self._choose_group)
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self._fill()

    def _wrap(self, row_layout: QHBoxLayout) -> QWidget:
        w = QWidget()
        w.setLayout(row_layout)
        return w

    def _fill(self) -> None:
        if self._entry is None:
            self._title.setText("Запись не найдена.")
            self.save_btn.setEnabled(False)
            return

        self._title.setText(
            f"<b>{self._entry.subject_name}</b> "
            f"({self._entry.part_type})<br>"
            f"{self._entry.group_name} | {self._entry.teacher_name} | {self._entry.room_number}"
        )
        self.slot_value.setText(
            f"{DAY_NAMES.get(int(self._entry.day_of_week), str(self._entry.day_of_week))}, "
            f"пара {int(self._entry.pair_number)}"
        )
        self.teacher_value.setText(self._entry.teacher_name)
        self.room_value.setText(self._entry.room_number)
        self.group_value.setText(self._entry.group_name)

    def _choose_slot(self) -> None:
        variant = self._vm.current_variant
        if variant is None:
            return

        choices = []
        mapping = {}

        seen = set()
        for e in variant.entries:
            key = (int(e.slot_id), int(e.day_of_week), int(e.pair_number))
            if key in seen:
                continue
            seen.add(key)
            text = (
                f"{DAY_NAMES.get(int(e.day_of_week), str(e.day_of_week))}, "
                f"пара {int(e.pair_number)} [slot_id={int(e.slot_id)}]"
            )
            choices.append(text)
            mapping[text] = int(e.slot_id)

        if not choices:
            QMessageBox.warning(self, "Нет слотов", "Не удалось получить доступные слоты.")
            return

        value, ok = QInputDialog.getItem(
            self,
            "Выбор слота",
            "Слот:",
            choices,
            0,
            False,
        )
        if ok and value:
            self._new_slot_id = mapping[value]
            self.slot_value.setText(value)

    def _choose_teacher(self) -> None:
        repo = getattr(self._vm, "_apply_manual_edit_uc", None)
        teachers_repo = getattr(repo, "_teachers_repo", None)
        if teachers_repo is None:
            QMessageBox.warning(self, "Нет данных", "Репозиторий преподавателей недоступен.")
            return

        teachers = teachers_repo.list_all()
        if not teachers:
            QMessageBox.warning(self, "Нет данных", "Список преподавателей пуст.")
            return

        choices = []
        mapping = {}
        for t in teachers:
            text = f"{t.full_name} [id={int(t.id_teacher)}]"
            choices.append(text)
            mapping[text] = int(t.id_teacher)

        value, ok = QInputDialog.getItem(
            self,
            "Выбор преподавателя",
            "Преподаватель:",
            choices,
            0,
            False,
        )
        if ok and value:
            self._new_teacher_id = mapping[value]
            self.teacher_value.setText(value)

    def _choose_room(self) -> None:
        repo = getattr(self._vm, "_apply_manual_edit_uc", None)
        rooms_repo = getattr(repo, "_rooms_repo", None)
        if rooms_repo is None:
            QMessageBox.warning(self, "Нет данных", "Репозиторий аудиторий недоступен.")
            return

        rooms = rooms_repo.list_all()
        if not rooms:
            QMessageBox.warning(self, "Нет данных", "Список аудиторий пуст.")
            return

        choices = []
        mapping = {}
        for r in rooms:
            text = (
                f"{r.room_number} [{r.room_type}, вместимость {int(r.capacity)}]"
                f" [id={int(r.id_room)}]"
            )
            choices.append(text)
            mapping[text] = int(r.id_room)

        value, ok = QInputDialog.getItem(
            self,
            "Выбор аудитории",
            "Аудитория:",
            choices,
            0,
            False,
        )
        if ok and value:
            self._new_room_id = mapping[value]
            self.room_value.setText(value)

    def _choose_group(self) -> None:
        repo = getattr(self._vm, "_apply_manual_edit_uc", None)
        groups_repo = getattr(repo, "_groups_repo", None)
        if groups_repo is None:
            QMessageBox.warning(self, "Нет данных", "Репозиторий групп недоступен.")
            return

        groups = groups_repo.list_all()
        if not groups:
            QMessageBox.warning(self, "Нет данных", "Список групп пуст.")
            return

        choices = []
        mapping = {}
        for g in groups:
            text = f"{g.group_name} [курс {g.year or '—'}, {int(g.quantity)} чел.] [id={int(g.id_group)}]"
            choices.append(text)
            mapping[text] = int(g.id_group)

        value, ok = QInputDialog.getItem(
            self,
            "Выбор группы",
            "Группа:",
            choices,
            0,
            False,
        )
        if ok and value:
            self._new_group_id = mapping[value]
            self.group_value.setText(value)

    def get_changes(self) -> dict:
        return {
            "new_slot_id": self._new_slot_id,
            "new_teacher_id": self._new_teacher_id,
            "new_room_id": self._new_room_id,
            "new_group_id": self._new_group_id,
        }


class ScheduleCellFrame(QFrame):
    def __init__(self, item: EditorCellItem, on_open, on_select=None, editable: bool = False):
        super().__init__()
        self.item = item
        self._on_open = on_open
        self._on_select = on_select
        self._editable = bool(editable)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._editable else Qt.CursorShape.ArrowCursor)
        if self._editable:
            self.setStyleSheet(
                """
                QFrame {
                    border: 1px solid #7f56d9;
                    border-radius: 6px;
                    background: #f5f3ff;
                }
                QFrame:hover {
                    background: #ede9fe;
                }
                """
            )
        else:
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

        title = QLabel(item.title)
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        subtitle = QLabel(item.subtitle)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #495057;")
        layout.addWidget(subtitle)

        if item.is_locked:
            lock_label = QLabel("🔒 Зафиксировано")
            lock_label.setStyleSheet("color: #8a5a00; font-size: 11px;")
            layout.addWidget(lock_label)

    def mousePressEvent(self, event):
        if callable(self._on_select):
            self._on_select(int(self.item.id_schedule))
        if self._editable and callable(self._on_open):
            self._on_open(int(self.item.id_schedule))
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if callable(self._on_select):
            self._on_select(int(self.item.id_schedule))
        if self._editable and callable(self._on_open):
            self._on_open(int(self.item.id_schedule))
        super().mouseDoubleClickEvent(event)


class EmptyScheduleCellFrame(QFrame):
    def __init__(self, *, on_open=None, editable: bool = False):
        super().__init__()
        self._on_open = on_open
        self._editable = bool(editable)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._editable else Qt.CursorShape.ArrowCursor)
        self.setStyleSheet(
            """
            QFrame {
                border: 1px dashed #cbd5e1;
                border-radius: 6px;
                background: #ffffff;
            }
            QFrame:hover {
                background: #f8fafc;
            }
            """
            if not self._editable else
            """
            QFrame {
                border: 1px dashed #7f56d9;
                border-radius: 6px;
                background: #faf5ff;
            }
            QFrame:hover {
                background: #f3e8ff;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        label = QLabel("Нажмите для добавления" if self._editable else "—")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: #7f56d9; font-weight: 600;" if self._editable else "color: #98a2b3;")
        layout.addWidget(label)

    def mousePressEvent(self, event):
        if self._editable and callable(self._on_open):
            self._on_open()
        super().mousePressEvent(event)


class EditorPage(QWidget):
    MODE_GROUP = "По группам"
    MODE_TEACHER = "По преподавателям"
    MODE_ROOM = "По аудиториям"

    def __init__(self, vm: EditorViewModel, calendar_repo=None):
        super().__init__()
        self.vm = vm
        self._calendar_repo = calendar_repo
        self._event_builder = None
        self._config = None
        self._groups_repo = None
        self._subjects_repo = None
        self._rooms_repo = None
        self._teachers_repo = None

        self._current_entry_id: Optional[int] = None
        self._preview_variant_id: Optional[int] = None
        self._calendar_edit_mode = False

        root = QVBoxLayout(self)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self._build_selector_page()
        self._build_detail_page()

        self.selector_refresh_btn.clicked.connect(self._populate_variants)
        self.selector_open_btn.clicked.connect(self._open_selected_variant)
        self.calendar_combo.currentIndexChanged.connect(self._calendar_changed)
        self.variants_table.itemSelectionChanged.connect(self._variant_selection_changed)
        self.variants_table.itemDoubleClicked.connect(self._open_selected_variant)
        self.back_btn.clicked.connect(self._show_selector_page)
        self.refresh_btn.clicked.connect(self._reload_current_variant)
        self.edit_btn.clicked.connect(self._toggle_calendar_edit_mode)
        self.view_mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.entity_combo.currentIndexChanged.connect(self._render_current_variant)
        self.week_filter_combo.currentIndexChanged.connect(self._render_current_variant)
        self.entries_list.itemClicked.connect(self._list_item_clicked)
        self.entries_list.itemDoubleClicked.connect(self._list_item_double_clicked)

        self.vm.variantLoaded.connect(self._on_variant_loaded)
        self.vm.entrySelected.connect(self._on_entry_selected)
        self.vm.editApplied.connect(self._on_edit_applied)
        self.vm.infoChanged.connect(self._on_info_changed)
        self.vm.errorChanged.connect(self._on_error_changed)

        self._load_calendars()
        self._populate_variants()
        self._show_selector_page()

    def configure_creation_support(
        self,
        *,
        event_builder,
        config,
        groups_repo,
        subjects_repo,
        rooms_repo,
        teachers_repo,
    ) -> None:
        self._event_builder = event_builder
        self._config = config
        self._groups_repo = groups_repo
        self._subjects_repo = subjects_repo
        self._rooms_repo = rooms_repo
        self._teachers_repo = teachers_repo

    def _build_selector_page(self) -> None:
        page = QWidget()
        root = QVBoxLayout(page)

        top_bar = QHBoxLayout()
        root.addLayout(top_bar)

        self.calendar_combo = QComboBox()
        self.selector_refresh_btn = QPushButton("Обновить")
        self.selector_open_btn = QPushButton("Открыть вариант")
        self.selector_open_btn.setEnabled(False)

        top_bar.addWidget(QLabel("Календарь:"))
        top_bar.addWidget(self.calendar_combo, 2)
        top_bar.addStretch(1)
        top_bar.addWidget(self.selector_refresh_btn)
        top_bar.addWidget(self.selector_open_btn)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Варианты расписания"))

        self.variants_table = QTableWidget(0, 4)
        self.variants_table.setHorizontalHeaderLabels(["ID", "Название", "Score", "Создан"])
        self.variants_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.variants_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.variants_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.variants_table.verticalHeader().setVisible(False)
        self.variants_table.setAlternatingRowColors(True)
        self.variants_table.setColumnWidth(0, 70)
        self.variants_table.setColumnWidth(1, 220)
        self.variants_table.setColumnWidth(2, 90)
        left_layout.addWidget(self.variants_table, 1)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        self.selector_title_label = QLabel("Вариант не выбран.")
        self.selector_title_label.setWordWrap(True)
        self.selector_title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        right_layout.addWidget(self.selector_title_label)

        right_layout.addWidget(QLabel("Краткая сводка варианта:"))
        self.selector_summary_list = QListWidget()
        right_layout.addWidget(self.selector_summary_list, 1)

        self.selector_status_label = QLabel("Выберите вариант расписания для просмотра.")
        self.selector_status_label.setWordWrap(True)
        right_layout.addWidget(self.selector_status_label)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.stack.addWidget(page)

    def _build_detail_page(self) -> None:
        page = QWidget()
        root = QVBoxLayout(page)

        top_bar = QHBoxLayout()
        root.addLayout(top_bar)

        self.back_btn = QPushButton("Назад к вариантам")
        self.refresh_btn = QPushButton("Обновить вариант")
        self.edit_btn = QPushButton("Редактировать календарь")

        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems([
            self.MODE_GROUP,
            self.MODE_TEACHER,
            self.MODE_ROOM,
        ])

        self.entity_combo = QComboBox()

        self.week_filter_combo = QComboBox()
        self.week_filter_combo.addItem("1 неделя", 1)
        self.week_filter_combo.addItem("2 неделя", 2)

        top_bar.addWidget(self.back_btn)
        top_bar.addWidget(QLabel("Режим:"))
        top_bar.addWidget(self.view_mode_combo, 1)
        top_bar.addWidget(QLabel("Сущность:"))
        top_bar.addWidget(self.entity_combo, 2)
        top_bar.addWidget(QLabel("Неделя:"))
        top_bar.addWidget(self.week_filter_combo, 1)
        top_bar.addStretch(1)
        top_bar.addWidget(self.refresh_btn)
        top_bar.addWidget(self.edit_btn)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(6, 6, 6, 6)
        self.grid_layout.setSpacing(6)
        self.info_label = QLabel("Выберите вариант расписания.")
        self.info_label.setWordWrap(True)
        self.info_label.hide()

        self.entries_list = QListWidget()
        self.entries_list.hide()

        self.selected_title = QLabel("Запись не выбрана.")
        self.selected_title.setWordWrap(True)
        self.selected_title.hide()

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.hide()

        root.addWidget(self.grid_container, 1)
        self.stack.addWidget(page)

    def _load_calendars(self) -> None:
        previous_calendar_id = self.calendar_combo.currentData()
        self.calendar_combo.blockSignals(True)
        self.calendar_combo.clear()
        if self._calendar_repo is not None:
            try:
                calendars = self._calendar_repo.list_calendars()
            except Exception as exc:
                self.selector_status_label.setText(f"Не удалось загрузить календари: {exc}")
                self.calendar_combo.blockSignals(False)
                return

            for cal in calendars:
                label = (
                    f"{getattr(cal, 'academic_year', '')} | "
                    f"семестр {getattr(cal, 'semester', '')} "
                    f"(id={getattr(cal, 'id_calendar', '')})"
                )
                self.calendar_combo.addItem(label, int(cal.id_calendar))

        if previous_calendar_id is not None:
            idx = self.calendar_combo.findData(int(previous_calendar_id))
            if idx >= 0:
                self.calendar_combo.setCurrentIndex(idx)

        self.calendar_combo.blockSignals(False)

    def refresh_calendars(self, selected_calendar_id: Optional[int] = None) -> None:
        self._load_calendars()
        if selected_calendar_id is not None:
            idx = self.calendar_combo.findData(int(selected_calendar_id))
            if idx >= 0:
                self.calendar_combo.setCurrentIndex(idx)
        self._populate_variants()

    def _calendar_changed(self) -> None:
        self._populate_variants()

    def _populate_variants(self) -> None:
        self._preview_variant_id = None
        self.variants_table.setRowCount(0)
        self.selector_open_btn.setEnabled(False)
        self.selector_title_label.setText("Вариант не выбран.")
        self.selector_summary_list.clear()
        calendar_id = self.calendar_combo.currentData()

        try:
            variants = self.vm._schedule_repo.list_variants(
                calendar_id=int(calendar_id) if calendar_id is not None else None
            )
        except Exception as exc:
            self.selector_status_label.setText(f"Не удалось загрузить список вариантов: {exc}")
            return

        for row_idx, variant in enumerate(variants):
            self.variants_table.insertRow(row_idx)
            variant_id = int(getattr(variant, "id_variant", 0) or 0)
            id_item = QTableWidgetItem(str(variant_id))
            id_item.setData(Qt.ItemDataRole.UserRole, variant_id)
            self.variants_table.setItem(row_idx, 0, id_item)
            self.variants_table.setItem(row_idx, 1, QTableWidgetItem(str(getattr(variant, "name", "") or "")))
            self.variants_table.setItem(row_idx, 2, QTableWidgetItem(str(int(getattr(variant, "objective_score", 0) or 0))))
            self.variants_table.setItem(row_idx, 3, QTableWidgetItem(str(getattr(variant, "created_at", "") or "")))

        if self.variants_table.rowCount() > 0:
            self.variants_table.selectRow(0)
            self._variant_selection_changed()
        else:
            self.selector_status_label.setText("В выбранном календаре нет вариантов расписания.")

    def _selected_variant_id(self) -> Optional[int]:
        row = self.variants_table.currentRow()
        if row < 0:
            return None
        item = self.variants_table.item(row, 0)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        if value is None:
            return None
        return int(value)

    def _variant_selection_changed(self) -> None:
        variant_id = self._selected_variant_id()
        if variant_id is None:
            self._preview_variant_id = None
            self.selector_open_btn.setEnabled(False)
            return
        self._preview_variant_id = int(variant_id)
        self.selector_open_btn.setEnabled(True)
        self._load_variant_preview(int(variant_id))

    def _load_variant_preview(self, variant_id: int) -> None:
        try:
            dto = self.vm._schedule_repo.get_variant_dto(int(variant_id))
        except Exception as exc:
            self.selector_status_label.setText(f"Не удалось загрузить вариант id={variant_id}: {exc}")
            self.selector_open_btn.setEnabled(False)
            return

        entries = list(dto.entries or [])
        self.selector_title_label.setText(
            f"{dto.name}<br><span style='font-size:12px; color:#667085;'>"
            f"id={int(dto.id_variant)}, записей: {len(entries)}</span>"
        )
        self.selector_summary_list.clear()
        for text in self._build_preview_rows(dto):
            self.selector_summary_list.addItem(QListWidgetItem(text))

        self.selector_status_label.setText(
            f"Выбран вариант '{dto.name}'. Нажмите 'Открыть вариант' для перехода к календарю."
        )

    def _build_preview_rows(self, dto) -> list[str]:
        entries = sorted(
            list(dto.entries or []),
            key=lambda e: (
                int(e.week_number),
                int(e.week_type),
                int(e.day_of_week),
                int(e.pair_number),
                str(e.group_name),
                str(e.subject_name),
            ),
        )

        rows: list[str] = []
        for entry in entries[:30]:
            rows.append(
                f"{DAY_NAMES.get(int(entry.day_of_week), str(entry.day_of_week))}, "
                f"{int(entry.pair_number)} пара - {entry.group_name} | {entry.subject_name}"
            )
        if len(entries) > 30:
            rows.append(f"... ещё записей: {len(entries) - 30}")
        if not rows:
            rows.append("В этом варианте пока нет записей.")
        return rows

    def _open_selected_variant(self, *_args) -> None:
        variant_id = self._preview_variant_id or self._selected_variant_id()
        if variant_id is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите вариант расписания.")
            return
        self.open_variant(int(variant_id))

    def open_variant(self, variant_id: int) -> None:
        self._set_calendar_edit_mode(False)
        variant_row = self.vm._schedule_repo.get_variant(int(variant_id))
        if variant_row is not None:
            calendar_id = int(getattr(variant_row, "calendar_id", 0) or 0)
            idx = self.calendar_combo.findData(calendar_id)
            if idx >= 0 and idx != self.calendar_combo.currentIndex():
                self.calendar_combo.setCurrentIndex(idx)
            else:
                self._populate_variants()

            for row_idx in range(self.variants_table.rowCount()):
                item = self.variants_table.item(row_idx, 0)
                if item is None:
                    continue
                value = item.data(Qt.ItemDataRole.UserRole)
                if int(value or 0) == int(variant_id):
                    self.variants_table.selectRow(row_idx)
                    break

        self.vm.load_variant(int(variant_id))
        self._show_detail_page()

    def _reload_current_variant(self) -> None:
        self.vm.refresh()

    def _on_variant_loaded(self, variant) -> None:
        self._current_entry_id = None
        self.selected_title.setText("Запись не выбрана.")
        self._rebuild_entity_filter(variant)
        self._render_variant(variant)
        self._show_detail_page()

    def _on_entry_selected(self, entry) -> None:
        self._current_entry_id = int(entry.id_schedule)
        self.selected_title.setText(
            f"<b>{entry.subject_name}</b> ({entry.part_type})<br>"
            f"{entry.group_name} | {entry.teacher_name} | {entry.room_number}<br>"
            f"Слот: {DAY_NAMES.get(int(entry.day_of_week), str(entry.day_of_week))}, "
            f"пара {int(entry.pair_number)} | id_schedule={int(entry.id_schedule)}"
        )

        for i in range(self.entries_list.count()):
            item = self.entries_list.item(i)
            if int(item.data(Qt.ItemDataRole.UserRole)) == int(entry.id_schedule):
                self.entries_list.setCurrentItem(item)
                break

    def _on_edit_applied(self, entry) -> None:
        self._current_entry_id = int(entry.id_schedule)

    def _on_info_changed(self, text: str) -> None:
        self.info_label.setText(text or "")

    def _on_error_changed(self, text: str) -> None:
        if text:
            self.status_label.setText(f"Ошибка: {text}")
            QMessageBox.warning(self, "Ошибка", text)
        else:
            self.status_label.setText("")

    def _show_selector_page(self) -> None:
        self._set_calendar_edit_mode(False)
        self.stack.setCurrentIndex(0)

    def _show_detail_page(self) -> None:
        self.stack.setCurrentIndex(1)

    def _set_calendar_edit_mode(self, enabled: bool) -> None:
        self._calendar_edit_mode = bool(enabled)
        if self._calendar_edit_mode and self._selected_mode() != self.MODE_GROUP:
            idx = self.view_mode_combo.findText(self.MODE_GROUP)
            if idx >= 0:
                self.view_mode_combo.setCurrentIndex(idx)

        if self._calendar_edit_mode:
            self.edit_btn.setText("Завершить редактирование")
            self.edit_btn.setStyleSheet("font-weight: 600; color: #7f56d9;")
        else:
            self.edit_btn.setText("Редактировать календарь")
            self.edit_btn.setStyleSheet("")

        self._render_current_variant()

    def _toggle_calendar_edit_mode(self) -> None:
        self._set_calendar_edit_mode(not self._calendar_edit_mode)

    def _selected_week_number(self) -> int:
        value = self.week_filter_combo.currentData()
        return int(value)

    def _selected_mode(self) -> str:
        return str(self.view_mode_combo.currentText())

    def _current_calendar_id(self) -> Optional[int]:
        if self.vm.current_variant_id is None:
            return None
        variant_row = self.vm._schedule_repo.get_variant(int(self.vm.current_variant_id))
        if variant_row is None:
            return None
        calendar_id = int(getattr(variant_row, "calendar_id", 0) or 0)
        return calendar_id if calendar_id > 0 else None

    def _selected_entity_key(self) -> Optional[tuple[str, int]]:
        value = self.entity_combo.currentData()
        if isinstance(value, tuple) and len(value) == 2:
            return value
        return None

    def _entity_key(self, entry, mode: str) -> tuple[str, int]:
        if mode == self.MODE_TEACHER:
            return (entry.teacher_name or "—", int(entry.teacher_id))
        if mode == self.MODE_ROOM:
            return (entry.room_number or "—", int(entry.room_id))
        return (entry.group_name or "—", int(entry.group_id))

    def _entity_label(self, key: tuple[str, int]) -> str:
        return key[0]

    def _on_mode_changed(self) -> None:
        variant = self.vm.current_variant
        if variant is None:
            return
        if self._calendar_edit_mode and self._selected_mode() != self.MODE_GROUP:
            self._set_calendar_edit_mode(False)
            return
        self._rebuild_entity_filter(variant)
        self._render_variant(variant)

    def _rebuild_entity_filter(self, variant) -> None:
        mode = self._selected_mode()
        selected_week = self._selected_week_number()

        entries = list(variant.entries or [])
        filtered = [e for e in entries if int(e.week_type) == int(selected_week)]

        entities = sorted(
            {self._entity_key(e, mode) for e in filtered},
            key=lambda x: (x[0], x[1]),
        )

        current = self.entity_combo.currentData()

        self.entity_combo.blockSignals(True)
        self.entity_combo.clear()

        for key in entities:
            self.entity_combo.addItem(self._entity_label(key), key)

        if entities:
            idx = self.entity_combo.findData(current)
            self.entity_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self.entity_combo.blockSignals(False)

    def _render_current_variant(self) -> None:
        variant = self.vm.current_variant
        if variant is not None:
            self._render_variant(variant)

    def _clear_grid(self) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_variant(self, variant) -> None:
        self._clear_grid()

        mode = self._selected_mode()
        selected_entity = self._selected_entity_key()
        selected_week = self._selected_week_number()

        entries = [e for e in variant.entries if int(e.week_type) == int(selected_week)]

        if not entries:
            self.grid_layout.addWidget(QLabel("Нет записей для выбранного фильтра."), 0, 0)
            self._fill_entries_list([])
            return

        if selected_entity is None:
            self.grid_layout.addWidget(QLabel("Выберите сущность для отображения."), 0, 0)
            self._fill_entries_list([])
            return

        entries = [e for e in entries if self._entity_key(e, mode) == selected_entity]

        if not entries:
            self.grid_layout.addWidget(QLabel("Нет записей для выбранной сущности."), 0, 0)
            self._fill_entries_list([])
            return

        days, pairs = self._grid_dimensions_for_week(selected_week, entries)

        corner = QLabel(self._entity_label(selected_entity))
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

        grouped = defaultdict(list)
        for e in entries:
            grouped[(int(e.day_of_week), int(e.pair_number))].append(e)

        for pair, row_idx in pair_rows:
            for day, col_idx in day_columns:
                cell_widget = QWidget()
                cell_layout = QVBoxLayout(cell_widget)
                cell_layout.setContentsMargins(2, 2, 2, 2)
                cell_layout.setSpacing(4)

                cell_entries = grouped.get((day, pair), [])
                for dto in cell_entries:
                    item = EditorCellItem.from_dto(dto)
                    frame = ScheduleCellFrame(
                        item,
                        self._open_editor_for_entry,
                        self.vm.select_entry,
                        editable=self._calendar_edit_mode and mode == self.MODE_GROUP,
                    )
                    cell_layout.addWidget(frame)

                if not cell_entries:
                    slot_id = self._slot_id_for_cell(selected_week, day, pair)
                    empty = EmptyScheduleCellFrame(
                        editable=self._calendar_edit_mode and mode == self.MODE_GROUP and slot_id is not None,
                        on_open=(
                            lambda sid=slot_id, d=day, p=pair: self._open_empty_cell_editor(sid, d, p)
                            if slot_id is not None else None
                        ),
                    )
                    cell_layout.addWidget(empty)

                self.grid_layout.addWidget(cell_widget, row_idx, col_idx)

        self._fill_entries_list(entries)

    def _fill_entries_list(self, entries) -> None:
        self.entries_list.clear()
        for e in entries:
            text = (
                f"{DAY_NAMES.get(int(e.day_of_week), str(e.day_of_week))}, "
                f"{int(e.pair_number)} пара — "
                f"{e.subject_name} ({e.part_type}) | "
                f"{e.group_name} | {e.teacher_name} | {e.room_number}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, int(e.id_schedule))
            self.entries_list.addItem(item)

    def _grid_dimensions_for_week(self, week_type: int, entries) -> tuple[list[int], list[int]]:
        calendar_repo = getattr(self.vm._apply_manual_edit_uc, "_calendar_repo", None)
        if calendar_repo is None or self.vm.current_variant_id is None:
            days = sorted({int(e.day_of_week) for e in entries})
            pairs = sorted({int(e.pair_number) for e in entries})
            return days, pairs

        variant_row = self.vm._schedule_repo.get_variant(int(self.vm.current_variant_id))
        if variant_row is None:
            days = sorted({int(e.day_of_week) for e in entries})
            pairs = sorted({int(e.pair_number) for e in entries})
            return days, pairs

        calendar_id = int(getattr(variant_row, "calendar_id", 0) or 0)
        slots = [
            s for s in calendar_repo.list_time_slots(calendar_id)
            if not bool(getattr(s, "is_lunch_break", False))
            and int(getattr(s, "week_type", 0) or 0) == int(week_type)
        ]

        days = sorted({int(getattr(s, "day_of_week", 0) or 0) for s in slots})
        pairs = sorted({int(getattr(s, "pair_number", 0) or 0) for s in slots})

        if not days:
            days = sorted({int(e.day_of_week) for e in entries})
        if not pairs:
            pairs = sorted({int(e.pair_number) for e in entries})

        return days, pairs

    def _slot_id_for_cell(self, week_type: int, day: int, pair: int) -> Optional[int]:
        calendar_id = self._current_calendar_id()
        if calendar_id is None or self._calendar_repo is None:
            return None
        for slot in self._calendar_repo.list_time_slots(int(calendar_id)):
            if bool(getattr(slot, "is_lunch_break", False)):
                continue
            if int(getattr(slot, "week_type", 0) or 0) != int(week_type):
                continue
            if int(getattr(slot, "day_of_week", 0) or 0) != int(day):
                continue
            if int(getattr(slot, "pair_number", 0) or 0) != int(pair):
                continue
            return int(getattr(slot, "id_slot", 0) or 0)
        return None

    def _available_events_for_group_week(self, group_id: int, week_type: int) -> list[object]:
        calendar_id = self._current_calendar_id()
        if calendar_id is None or self._event_builder is None or self._config is None or self._subjects_repo is None:
            return []

        subjects_by_id = {
            int(getattr(s, "id_subject", 0) or 0): s
            for s in self._subjects_repo.list_all()
        }
        used_event_ids = {
            int(getattr(entry, "event_id", 0) or 0)
            for entry in (self.vm.current_variant.entries if self.vm.current_variant is not None else [])
        }
        events = []
        for event in self._event_builder.build_events(
            calendar_id=int(calendar_id),
            hours_per_pair=int(getattr(self._config, "hours_per_pair", 2) or 2),
            locks=[],
        ):
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

    def _open_empty_cell_editor(self, slot_id: int, day: int, pair: int) -> None:
        if not self._calendar_edit_mode or self._selected_mode() != self.MODE_GROUP:
            return
        selected_entity = self._selected_entity_key()
        if selected_entity is None or self.vm.current_variant_id is None:
            return

        group_id = int(selected_entity[1])
        week_type = self._selected_week_number()
        available_events = self._available_events_for_group_week(group_id, week_type)
        if not available_events:
            QMessageBox.warning(self, "Нет доступных занятий", "Для выбранной группы и недели все допустимые занятия уже размещены в расписании.")
            return

        slot_label = f"{DAY_NAMES.get(int(day), str(day))}, {int(pair)} пара, неделя {int(week_type)}"
        dlg = DraftEntryDialog(
            self,
            slot_id=int(slot_id),
            slot_label=slot_label,
            available_events=available_events,
            teachers_repo=self._teachers_repo,
            teacher_part_matrix=self._teachers_repo.get_teacher_part_matrix(),
            rooms_repo=self._rooms_repo,
            groups_repo=self._groups_repo,
            current_entry=None,
            current_event=None,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        result = dlg.get_result()
        event_id = result.get("event_id")
        selected_event = next(
            (e for e in available_events if int(getattr(e, "id_event", 0) or 0) == int(event_id or 0)),
            None,
        )
        if selected_event is None:
            QMessageBox.warning(self, "Ошибка", "Нужно выбрать дисциплину для добавления.")
            return

        teacher_id = result.get("teacher_id")
        room_id = result.get("room_id")
        if teacher_id is None or room_id is None:
            QMessageBox.warning(self, "Ошибка", "Для готового расписания нужно выбрать преподавателя и аудиторию.")
            return

        created = self.vm.create_entry(
            event_id=int(getattr(selected_event, "id_event", 0) or 0),
            curriculum_id=int(getattr(selected_event, "curriculum_id", 0) or 0),
            slot_id=int(slot_id),
            group_id=int(getattr(selected_event, "group_id", 0) or 0),
            teacher_id=int(teacher_id),
            room_id=int(room_id),
            comment="Добавление из editor_page",
            edited_by="editor_page",
            lock_after_edit=True,
        )
        if created is not None:
            QMessageBox.information(self, "Сохранено", "Запись успешно добавлена.")

    def _list_item_clicked(self, item: QListWidgetItem) -> None:
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        if entry_id is not None:
            self.vm.select_entry(int(entry_id))

    def _list_item_double_clicked(self, item: QListWidgetItem) -> None:
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        if entry_id is not None:
            self._open_editor_for_entry(int(entry_id))

    def _open_current_entry_editor(self) -> None:
        if self._selected_mode() != self.MODE_GROUP:
            QMessageBox.information(self, "Редактирование ограничено", "Редактирование расписания сейчас доступно только в режиме 'По группам'.")
            return
        if self._current_entry_id is None:
            QMessageBox.information(self, "Запись не выбрана", "Сначала выберите запись.")
            return
        self._open_editor_for_entry(int(self._current_entry_id))

    def _open_editor_for_entry(self, entry_id: int) -> None:
        entry = self.vm.select_entry(int(entry_id))
        if entry is None:
            return

        dialog = EntryEditDialog(self, self.vm, int(entry_id))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        changes = dialog.get_changes()

        if not any(v is not None for v in changes.values()):
            QMessageBox.information(self, "Нет изменений", "Вы не выбрали новые значения.")
            return

        updated = self.vm.apply_edit(
            schedule_entry_id=int(entry_id),
            new_slot_id=changes["new_slot_id"],
            new_teacher_id=changes["new_teacher_id"],
            new_room_id=changes["new_room_id"],
            new_group_id=changes["new_group_id"],
            comment="Редактирование из editor_page",
            edited_by="editor_page",
            lock_after_edit=True,
        )
        if updated is not None:
            QMessageBox.information(self, "Сохранено", "Изменения успешно сохранены.")
