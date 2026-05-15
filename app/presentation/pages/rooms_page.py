from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class RoomEditDialog(QDialog):

    ROOM_TYPES = [
        ("Лаборатория", "lab"),
        ("Компьютерный класс", "computer"),
        ("Лекционная", "lecture"),
        ("Обычная аудитория", "classroom"),
    ]

    PRIORITY = ["lab", "computer", "lecture", "classroom"]

    def __init__(self, parent, *, subjects_repo=None, selected_subject_ids: Optional[list[int]] = None, room: Optional[object] = None):
        super().__init__(parent)
        self._room = room
        self._subjects_repo = subjects_repo
        self._selected_subject_ids = set(selected_subject_ids or [])

        self.setWindowTitle(
            "Редактирование аудитории" if room is not None else "Добавление аудитории"
        )
        self.resize(560, 560)

        root = QVBoxLayout(self)

        form = QFormLayout()
        root.addLayout(form)

        self.room_number_combo = QComboBox()
        self.room_number_combo.setEditable(True)
        self.room_number_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.room_number_combo.setPlaceholderText("Введите номер или название аудитории")
        form.addRow("Аудитория:", self.room_number_combo)

        self.capacity_spin = QSpinBox()
        self.capacity_spin.setRange(1, 5000)
        self.capacity_spin.setValue(30)
        form.addRow("Вместимость:", self.capacity_spin)

        types_box = QWidget()
        types_layout = QGridLayout(types_box)
        types_layout.setContentsMargins(0, 0, 0, 0)

        self.type_checks: dict[str, QCheckBox] = {}
        for idx, (label, value) in enumerate(self.ROOM_TYPES):
            checkbox = QCheckBox(label)
            self.type_checks[value] = checkbox
            types_layout.addWidget(checkbox, idx // 2, idx % 2)

        form.addRow("Типы аудитории:", types_box)

        self.subjects_list = QListWidget()
        self.subjects_list.setMinimumHeight(180)
        form.addRow("Закрепить за дисциплинами:", self.subjects_list)

        hint = QLabel(
            "Можно выбрать несколько типов одновременно.\n"
            "Приоритет специализации:\n"
            "Лабораторные → Компьютерные → Лекции → Учебные пары."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #667085;")
        root.addWidget(hint)

        self.primary_type_label = QLabel("Главный тип: —")
        self.primary_type_label.setStyleSheet("font-weight: 600; color: #344054;")
        root.addWidget(self.primary_type_label)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        root.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        for checkbox in self.type_checks.values():
            checkbox.toggled.connect(self._update_primary_type_preview)

        self._fill()
        self._load_subjects()
        self._update_primary_type_preview()

    def _load_subjects(self) -> None:
        self.subjects_list.clear()
        if self._subjects_repo is None:
            return
        for subject in self._subjects_repo.list_all():
            subject_id = int(getattr(subject, "id_subject", 0) or 0)
            item = QListWidgetItem(str(getattr(subject, "subject_name", "") or f"id={subject_id}"))
            item.setData(Qt.ItemDataRole.UserRole, subject_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if subject_id in self._selected_subject_ids else Qt.CheckState.Unchecked)
            self.subjects_list.addItem(item)

    def _fill(self) -> None:
        if self._room is None:
            return

        room_number = str(getattr(self._room, "room_number", "") or "")
        capacity = int(getattr(self._room, "capacity", 30) or 30)

        self.room_number_combo.addItem(room_number)
        self.room_number_combo.setCurrentText(room_number)
        self.capacity_spin.setValue(capacity)

        room_types = getattr(self._room, "room_types", None)
        if not room_types:
            single_type = str(getattr(self._room, "room_type", "") or "")
            room_types = [single_type] if single_type else []

        normalized = {str(x).strip().lower() for x in room_types if str(x).strip()}
        for value, checkbox in self.type_checks.items():
            checkbox.setChecked(value in normalized)

    def _get_selected_room_types(self) -> list[str]:
        selected = [value for value, cb in self.type_checks.items() if cb.isChecked()]
        selected.sort(key=lambda x: self.PRIORITY.index(x) if x in self.PRIORITY else 999)
        return selected

    def _get_primary_room_type(self) -> str:
        selected = self._get_selected_room_types()
        return selected[0] if selected else ""

    def _room_type_label(self, value: str) -> str:
        mapping = {
            "lab": "Лаборатория",
            "computer": "Компьютерный класс",
            "lecture": "Лекционная",
            "classroom": "Обычная аудитория",
        }
        return mapping.get(value, value or "—")

    def _update_primary_type_preview(self) -> None:
        primary = self._get_primary_room_type()
        self.primary_type_label.setText(
            f"Главный тип: {self._room_type_label(primary) if primary else '—'}"
        )

    def get_data(self) -> tuple[str, str, list[str], int, list[int]]:
        room_number = self.room_number_combo.currentText().strip()
        room_types = self._get_selected_room_types()
        primary_room_type = self._get_primary_room_type()
        capacity = int(self.capacity_spin.value())
        subject_ids = []
        for idx in range(self.subjects_list.count()):
            item = self.subjects_list.item(idx)
            if item.checkState() == Qt.CheckState.Checked:
                subject_ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return room_number, primary_room_type, room_types, capacity, subject_ids


class CreateCalendarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавление семестра")
        self.resize(420, 220)

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        self.academic_year_combo = QComboBox()
        self.academic_year_combo.setEditable(True)
        self.academic_year_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.academic_year_combo.addItems(["2025/2026", "2026/2027", "2027/2028"])
        form.addRow("Учебный год:", self.academic_year_combo)

        self.semester_combo = QComboBox()
        self.semester_combo.addItem("1 семестр", 1)
        self.semester_combo.addItem("2 семестр", 2)
        form.addRow("Семестр:", self.semester_combo)

        self.include_saturday = QComboBox()
        self.include_saturday.addItem("Без субботы", False)
        self.include_saturday.addItem("С субботой", True)
        form.addRow("Режим:", self.include_saturday)

        self.pairs_per_day_spin = QSpinBox()
        self.pairs_per_day_spin.setRange(1, 12)
        self.pairs_per_day_spin.setValue(8)
        form.addRow("Пар в день:", self.pairs_per_day_spin)

        self.weeks_in_semester_spin = QSpinBox()
        self.weeks_in_semester_spin.setRange(1, 30)
        self.weeks_in_semester_spin.setValue(18)
        form.addRow("Недель в семестре:", self.weeks_in_semester_spin)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        root.addWidget(self.button_box)

    def get_data(self) -> dict:
        return {
            "academic_year": self.academic_year_combo.currentText().strip(),
            "semester": int(self.semester_combo.currentData()),
            "include_saturday": bool(self.include_saturday.currentData()),
            "pairs_per_day": int(self.pairs_per_day_spin.value()),
            "weeks_in_semester": int(self.weeks_in_semester_spin.value()),
        }


class RoomsPage(QWidget):
    calendarCreated = pyqtSignal(int)

    def __init__(self, rooms_repo, calendar_repo, subjects_repo=None):
        super().__init__()
        self._rooms_repo = rooms_repo
        self._calendar_repo = calendar_repo
        self._subjects_repo = subjects_repo
        self._current_calendar_id: Optional[int] = None
        self._all_rows: list[object] = []
        self._sort_column: Optional[int] = None
        self._sort_order: int = 0

        root = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        root.addLayout(toolbar)

        toolbar.addWidget(QLabel("Календарь:"))

        self.calendar_combo = QComboBox()
        toolbar.addWidget(self.calendar_combo)

        self.add_calendar_btn = QPushButton("+")
        self.add_calendar_btn.setFixedWidth(32)
        self.add_calendar_btn.setToolTip("Добавить семестр")
        toolbar.addWidget(self.add_calendar_btn)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по таблице...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMaximumWidth(260)
        toolbar.addWidget(self.search_edit)

        toolbar.addStretch(1)

        self.add_btn = QPushButton("Добавить")
        self.edit_btn = QPushButton("Редактировать")
        self.delete_btn = QPushButton("Удалить")
        self.refresh_btn = QPushButton("Обновить")

        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.edit_btn)
        toolbar.addWidget(self.delete_btn)
        toolbar.addWidget(self.refresh_btn)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Аудитория", "Типы аудитории", "Вместимость"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().sectionClicked.connect(self._toggle_sort)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(2, 240)
        self.table.setColumnWidth(3, 110)
        root.addWidget(self.table)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.add_btn.clicked.connect(self._add_room)
        self.edit_btn.clicked.connect(self._edit_room)
        self.delete_btn.clicked.connect(self._delete_room)
        self.refresh_btn.clicked.connect(self.refresh)
        self.search_edit.textChanged.connect(self._apply_filters)
        self.calendar_combo.currentIndexChanged.connect(self._calendar_changed)
        self.add_calendar_btn.clicked.connect(self._create_calendar_dialog)

        self._load_calendars()
        self.refresh()

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            "color: #b42318;" if error else "color: #344054;"
        )

    def _selected_room_id(self) -> Optional[int]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        try:
            return int(item.data(Qt.ItemDataRole.UserRole))
        except (TypeError, ValueError):
            return None

    def _select_calendar_by_id(self, calendar_id: int) -> None:
        idx = self.calendar_combo.findData(int(calendar_id))
        if idx >= 0:
            self.calendar_combo.setCurrentIndex(idx)
            self._current_calendar_id = int(calendar_id)

    def _load_calendars(self) -> None:
        previous_calendar_id = self._current_calendar_id
        self.calendar_combo.blockSignals(True)
        self.calendar_combo.clear()
        try:
            calendars = self._calendar_repo.list_calendars()
        except Exception as exc:
            self._set_status(f"Не удалось загрузить календари: {exc}", error=True)
            self.calendar_combo.blockSignals(False)
            return

        for cal in calendars:
            label = (
                f"{getattr(cal, 'academic_year', '')} | "
                f"семестр {getattr(cal, 'semester', '')} "
                f"(id={getattr(cal, 'id_calendar', '')})"
            )
            self.calendar_combo.addItem(label, int(cal.id_calendar))

        if self.calendar_combo.count() > 0:
            if previous_calendar_id is not None:
                idx = self.calendar_combo.findData(int(previous_calendar_id))
                if idx >= 0:
                    self.calendar_combo.setCurrentIndex(idx)
            self._current_calendar_id = int(self.calendar_combo.currentData())
        else:
            self._current_calendar_id = None

        self.calendar_combo.blockSignals(False)

    def _calendar_changed(self) -> None:
        value = self.calendar_combo.currentData()
        self._current_calendar_id = int(value) if value is not None else None

    def _create_calendar_dialog(self) -> None:
        dlg = CreateCalendarDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        if not data["academic_year"]:
            QMessageBox.warning(self, "Ошибка", "Учебный год не может быть пустым.")
            return

        try:
            calendar_id = self._calendar_repo.create_calendar(
                academic_year=str(data["academic_year"]),
                semester=int(data["semester"]),
                include_saturday=bool(data["include_saturday"]),
                pairs_per_day=int(data["pairs_per_day"]),
                weeks_in_semester=int(data["weeks_in_semester"]),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать семестр:\n{exc}")
            return

        self._load_calendars()
        self._select_calendar_by_id(int(calendar_id))
        self._set_status("Семестр успешно создан.")
        self.calendarCreated.emit(int(calendar_id))

    def refresh_calendars(self, selected_calendar_id: Optional[int] = None) -> None:
        self._load_calendars()
        if selected_calendar_id is not None:
            self._select_calendar_by_id(int(selected_calendar_id))

    @staticmethod
    def _room_type_label(value: str) -> str:
        mapping = {
            "lecture": "Лекционная",
            "classroom": "Обычная аудитория",
            "computer": "Компьютерный класс",
            "lab": "Лаборатория",
        }
        return mapping.get(value, value or "—")

    def _room_types_label(self, room) -> str:
        room_types = getattr(room, "room_types", None)
        if not room_types:
            single_type = str(getattr(room, "room_type", "") or "")
            room_types = [single_type] if single_type else []

        labels = [self._room_type_label(str(x)) for x in room_types if str(x).strip()]
        return ", ".join(labels) if labels else "—"

    def _add_room(self) -> None:
        dlg = RoomEditDialog(self, subjects_repo=self._subjects_repo)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        room_number, primary_room_type, room_types, capacity, subject_ids = dlg.get_data()

        if not room_number:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Номер или название аудитории не может быть пустым.",
            )
            return

        if not room_types:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Нужно выбрать хотя бы один тип аудитории.",
            )
            return

        if not primary_room_type:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Не удалось определить главный тип аудитории.",
            )
            return

        if int(capacity) <= 0:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Вместимость должна быть больше 0.",
            )
            return

        try:
            room_id = self._rooms_repo.create(
                room_number=room_number,
                room_type=primary_room_type,
                room_types=room_types,
                capacity=int(capacity),
                building=None,
            )
            self._rooms_repo.replace_room_subject_assignments(int(room_id), subject_ids)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось добавить аудиторию:\n{exc}",
            )
            return

        self.refresh()
        self._set_status(f"Аудитория '{room_number}' добавлена.")

    def _edit_room(self) -> None:
        room_id = self._selected_room_id()
        if room_id is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите аудиторию.")
            return

        room = self._rooms_repo.get_by_id(int(room_id))
        if room is None:
            QMessageBox.warning(self, "Ошибка", "Аудитория не найдена.")
            self.refresh()
            return

        selected_subject_ids = self._rooms_repo.get_room_subject_ids(int(room_id))
        dlg = RoomEditDialog(
            self,
            subjects_repo=self._subjects_repo,
            selected_subject_ids=selected_subject_ids,
            room=room,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        room_number, primary_room_type, room_types, capacity, subject_ids = dlg.get_data()

        if not room_number:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Номер или название аудитории не может быть пустым.",
            )
            return

        if not room_types:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Нужно выбрать хотя бы один тип аудитории.",
            )
            return

        if not primary_room_type:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Не удалось определить главный тип аудитории.",
            )
            return

        if int(capacity) <= 0:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Вместимость должна быть больше 0.",
            )
            return

        try:
            self._rooms_repo.update(
                id_room=int(room_id),
                room_number=room_number,
                room_type=primary_room_type,
                room_types=room_types,
                capacity=int(capacity),
                building=None,
            )
            self._rooms_repo.replace_room_subject_assignments(int(room_id), subject_ids)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось сохранить изменения аудитории:\n{exc}",
            )
            return

        self.refresh()
        self._set_status(f"Аудитория '{room_number}' обновлена.")

    def _delete_room(self) -> None:
        room_id = self._selected_room_id()
        if room_id is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите аудиторию.")
            return

        room = self._rooms_repo.get_by_id(int(room_id))
        room_name = (
            getattr(room, "room_number", f"id={room_id}") if room else f"id={room_id}"
        )

        answer = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Удалить аудиторию '{room_name}'?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self._rooms_repo.delete(int(room_id))
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось удалить аудиторию:\n{exc}",
            )
            return

        self.refresh()
        self._set_status(f"Аудитория '{room_name}' удалена.")

    def refresh(self) -> None:
        try:
            self._all_rows = list(self._rooms_repo.list_all())
        except Exception as exc:
            self.table.setRowCount(0)
            self._set_status(f"Не удалось загрузить аудитории: {exc}", error=True)
            return

        self._apply_filters()

    def _toggle_sort(self, column: int) -> None:
        if self._sort_column != column:
            self._sort_column = column
            self._sort_order = 1
        elif self._sort_order == 1:
            self._sort_order = -1
        else:
            self._sort_column = None
            self._sort_order = 0

        self._apply_filters()

    def _apply_filters(self) -> None:
        rows = list(self._all_rows)
        query = self.search_edit.text().strip().lower()

        if query:
            filtered = []
            for room in rows:
                haystack = " ".join(
                    [
                        str(getattr(room, "id_room", "") or ""),
                        str(getattr(room, "room_number", "") or ""),
                        self._room_types_label(room),
                        str(getattr(room, "capacity", "") or ""),
                    ]
                ).lower()
                if query in haystack:
                    filtered.append(room)
            rows = filtered

        if self._sort_column is not None and self._sort_order != 0:
            key_map = {
                0: lambda x: int(getattr(x, "id_room", 0) or 0),
                1: lambda x: str(getattr(x, "room_number", "") or "").lower(),
                2: lambda x: self._room_types_label(x).lower(),
                3: lambda x: int(getattr(x, "capacity", 0) or 0),
            }
            rows.sort(key=key_map[self._sort_column], reverse=self._sort_order < 0)

        self._update_header_labels()
        self._render_rows(rows)

    def _update_header_labels(self) -> None:
        base_headers = ["ID", "Аудитория", "Типы аудитории", "Вместимость"]
        headers = []
        for idx, title in enumerate(base_headers):
            if self._sort_column == idx:
                headers.append(f"{title} {'▲' if self._sort_order > 0 else '▼' if self._sort_order < 0 else ''}".strip())
            else:
                headers.append(title)
        self.table.setHorizontalHeaderLabels(headers)

    def _render_rows(self, rows: list[object]) -> None:
        self.table.setRowCount(0)

        for row_idx, room in enumerate(rows):
            self.table.insertRow(row_idx)

            id_room = int(getattr(room, "id_room", 0))
            room_number = str(getattr(room, "room_number", "") or "")
            capacity = int(getattr(room, "capacity", 0) or 0)

            id_item = QTableWidgetItem(str(id_room))
            id_item.setData(Qt.ItemDataRole.UserRole, id_room)

            room_item = QTableWidgetItem(room_number)
            types_item = QTableWidgetItem(self._room_types_label(room))
            capacity_item = QTableWidgetItem(str(capacity))

            self.table.setItem(row_idx, 0, id_item)
            self.table.setItem(row_idx, 1, room_item)
            self.table.setItem(row_idx, 2, types_item)
            self.table.setItem(row_idx, 3, capacity_item)

        self._set_status(f"Загружено аудиторий: {len(rows)}")
