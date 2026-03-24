from __future__ import annotations

from collections import defaultdict
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
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from app.presentation.viewmodels.editor_vm import EditorCellItem, EditorViewModel


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
    def __init__(self, item: EditorCellItem, on_open):
        super().__init__()
        self.item = item
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

    def mouseDoubleClickEvent(self, event):
        if callable(self._on_open):
            self._on_open(int(self.item.id_schedule))
        super().mouseDoubleClickEvent(event)


class EditorPage(QWidget):
    """
    Экран ручного редактирования расписания.

    Особенности:
    - работает с id_schedule;
    - отображает готовый вариант расписания по сетке;
    - позволяет выбрать запись и открыть редактирование;
    - после правки полностью перечитывает вариант через ViewModel;
    - отображает записи по выбранному режиму и конкретной сущности.
    """

    MODE_GROUP = "По группам"
    MODE_TEACHER = "По преподавателям"
    MODE_ROOM = "По аудиториям"

    def __init__(self, vm: EditorViewModel):
        super().__init__()
        self.vm = vm

        self._current_entry_id: Optional[int] = None

        root = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        root.addLayout(top_bar)

        self.variant_combo = QComboBox()
        self.refresh_btn = QPushButton("Обновить")
        self.edit_btn = QPushButton("Редактировать запись")
        self.edit_btn.setEnabled(False)

        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(
            [
                self.MODE_GROUP,
                self.MODE_TEACHER,
                self.MODE_ROOM,
            ]
        )

        self.entity_combo = QComboBox()

        self.week_filter_combo = QComboBox()
        self.week_filter_combo.addItem("Все недели", None)

        self.week_type_filter_combo = QComboBox()
        self.week_type_filter_combo.addItem("Все типы недель", None)
        self.week_type_filter_combo.addItem("Числитель", 1)
        self.week_type_filter_combo.addItem("Знаменатель", 2)

        top_bar.addWidget(QLabel("Вариант:"))
        top_bar.addWidget(self.variant_combo, 2)
        top_bar.addWidget(QLabel("Режим:"))
        top_bar.addWidget(self.view_mode_combo, 1)
        top_bar.addWidget(QLabel("Сущность:"))
        top_bar.addWidget(self.entity_combo, 2)
        top_bar.addWidget(QLabel("Неделя:"))
        top_bar.addWidget(self.week_filter_combo, 1)
        top_bar.addWidget(QLabel("Тип недели:"))
        top_bar.addWidget(self.week_type_filter_combo, 1)
        top_bar.addWidget(self.refresh_btn)
        top_bar.addWidget(self.edit_btn)

        splitter = QSplitter()
        root.addWidget(splitter, 1)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(6, 6, 6, 6)
        self.grid_layout.setSpacing(6)
        splitter.addWidget(self.grid_container)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        splitter.addWidget(right_panel)

        self.info_label = QLabel("Выберите вариант расписания.")
        self.info_label.setWordWrap(True)
        right_layout.addWidget(self.info_label)

        right_layout.addWidget(QLabel("Записи выбранной сущности:"))

        self.entries_list = QListWidget()
        right_layout.addWidget(self.entries_list, 1)

        self.selected_title = QLabel("Запись не выбрана.")
        self.selected_title.setWordWrap(True)
        right_layout.addWidget(self.selected_title)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)

        self.refresh_btn.clicked.connect(self._reload_current_variant)
        self.edit_btn.clicked.connect(self._open_current_entry_editor)
        self.variant_combo.currentIndexChanged.connect(self._variant_changed)
        self.view_mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.entity_combo.currentIndexChanged.connect(self._render_current_variant)
        self.week_filter_combo.currentIndexChanged.connect(self._render_current_variant)
        self.week_type_filter_combo.currentIndexChanged.connect(self._render_current_variant)
        self.entries_list.itemClicked.connect(self._list_item_clicked)
        self.entries_list.itemDoubleClicked.connect(self._list_item_double_clicked)

        self.vm.variantLoaded.connect(self._on_variant_loaded)
        self.vm.entrySelected.connect(self._on_entry_selected)
        self.vm.editApplied.connect(self._on_edit_applied)
        self.vm.infoChanged.connect(self._on_info_changed)
        self.vm.errorChanged.connect(self._on_error_changed)

        self._populate_variants()

    # ---------------------------------------------------------
    # Init / load
    # ---------------------------------------------------------
    def _populate_variants(self) -> None:
        self.variant_combo.blockSignals(True)
        self.variant_combo.clear()

        try:
            variants = self.vm._schedule_repo.list_variants()
        except Exception as exc:
            self.status_label.setText(f"Не удалось загрузить список вариантов: {exc}")
            self.variant_combo.blockSignals(False)
            return

        for variant in variants:
            self.variant_combo.addItem(
                f"{variant.name} (id={int(variant.id_variant)})",
                int(variant.id_variant),
            )

        self.variant_combo.blockSignals(False)

        if self.variant_combo.count() > 0:
            self.variant_combo.setCurrentIndex(0)
            self._variant_changed()

    def _variant_changed(self) -> None:
        variant_id = self.variant_combo.currentData()
        if variant_id is None:
            return
        self.vm.load_variant(int(variant_id))

    def _reload_current_variant(self) -> None:
        self.vm.refresh()

    # ---------------------------------------------------------
    # VM callbacks
    # ---------------------------------------------------------
    def _on_variant_loaded(self, variant) -> None:
        self._current_entry_id = None
        self.edit_btn.setEnabled(False)
        self.selected_title.setText("Запись не выбрана.")
        self._rebuild_week_filters(variant)
        self._rebuild_entity_filter(variant)
        self._render_variant(variant)

    def _on_entry_selected(self, entry) -> None:
        self._current_entry_id = int(entry.id_schedule)
        self.edit_btn.setEnabled(True)
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
        self.edit_btn.setEnabled(True)

    def _on_info_changed(self, text: str) -> None:
        self.info_label.setText(text or "")

    def _on_error_changed(self, text: str) -> None:
        if text:
            self.status_label.setText(f"Ошибка: {text}")
            QMessageBox.warning(self, "Ошибка", text)
        else:
            self.status_label.setText("")

    # ---------------------------------------------------------
    # Filters / rendering
    # ---------------------------------------------------------
    def _rebuild_week_filters(self, variant) -> None:
        weeks = sorted({int(e.week_number) for e in variant.entries if int(e.week_number) > 0})

        self.week_filter_combo.blockSignals(True)
        self.week_filter_combo.clear()
        self.week_filter_combo.addItem("Все недели", None)
        for w in weeks:
            self.week_filter_combo.addItem(f"Неделя {w}", w)
        self.week_filter_combo.blockSignals(False)

    def _selected_week_number(self) -> Optional[int]:
        value = self.week_filter_combo.currentData()
        return int(value) if value is not None else None

    def _selected_week_type(self) -> Optional[int]:
        value = self.week_type_filter_combo.currentData()
        return int(value) if value is not None else None

    def _selected_mode(self) -> str:
        return str(self.view_mode_combo.currentText())

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
        self._rebuild_entity_filter(variant)
        self._render_variant(variant)

    def _rebuild_entity_filter(self, variant) -> None:
        mode = self._selected_mode()

        entries = list(variant.entries or [])
        filtered = [
            e for e in entries
            if (self._selected_week_number() is None or int(e.week_number) == int(self._selected_week_number()))
            and (self._selected_week_type() is None or int(e.week_type) == int(self._selected_week_type()))
        ]

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

        entries = [
            e for e in variant.entries
            if (self._selected_week_number() is None or int(e.week_number) == int(self._selected_week_number()))
            and (self._selected_week_type() is None or int(e.week_type) == int(self._selected_week_type()))
        ]

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

        days = sorted({int(e.day_of_week) for e in entries})
        pairs = sorted({int(e.pair_number) for e in entries})

        self.grid_layout.addWidget(QLabel("День / пара"), 0, 0)

        col = 1
        day_columns = []
        for day in days:
            for pair in pairs:
                header = QLabel(f"{DAY_NAMES.get(day, str(day))}\n{pair} пара")
                header.setAlignment(Qt.AlignmentFlag.AlignCenter)
                header.setStyleSheet("font-weight: 600;")
                self.grid_layout.addWidget(header, 0, col)
                day_columns.append((day, pair, col))
                col += 1

        entity_label = QLabel(self._entity_label(selected_entity))
        entity_label.setStyleSheet("font-weight: 600;")
        self.grid_layout.addWidget(entity_label, 1, 0)

        grouped = defaultdict(list)
        for e in entries:
            grouped[(int(e.day_of_week), int(e.pair_number))].append(e)

        for day, pair, col_idx in day_columns:
            cell_widget = QWidget()
            cell_layout = QVBoxLayout(cell_widget)
            cell_layout.setContentsMargins(2, 2, 2, 2)
            cell_layout.setSpacing(4)

            cell_entries = grouped.get((day, pair), [])
            for dto in cell_entries:
                item = EditorCellItem.from_dto(dto)
                frame = ScheduleCellFrame(item, self._open_editor_for_entry)
                cell_layout.addWidget(frame)

            if not cell_entries:
                empty = QLabel("—")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty.setStyleSheet("color: #98a2b3;")
                cell_layout.addWidget(empty)

            self.grid_layout.addWidget(cell_widget, 1, col_idx)

        self._fill_entries_list(entries)

    # ---------------------------------------------------------
    # Right panel list
    # ---------------------------------------------------------
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

    def _list_item_clicked(self, item: QListWidgetItem) -> None:
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        if entry_id is not None:
            self.vm.select_entry(int(entry_id))

    def _list_item_double_clicked(self, item: QListWidgetItem) -> None:
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        if entry_id is not None:
            self._open_editor_for_entry(int(entry_id))

    # ---------------------------------------------------------
    # Edit dialog
    # ---------------------------------------------------------
    def _open_current_entry_editor(self) -> None:
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