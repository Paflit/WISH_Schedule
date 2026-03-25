from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
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
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class RoomEditDialog(QDialog):
    """
    Диалог создания / редактирования аудитории.

    Актуальная модель:
    - ID не вводится вручную;
    - обязательно есть номер/название аудитории;
    - аудитория может поддерживать несколько типов одновременно;
    - обязательно есть вместимость.

    Приоритет главного типа:
    1. lab
    2. computer
    3. lecture
    4. classroom
    """

    ROOM_TYPES = [
        ("Лаборатория", "lab"),
        ("Компьютерный класс", "computer"),
        ("Лекционная", "lecture"),
        ("Обычная аудитория", "classroom"),
    ]

    def __init__(self, parent, room: Optional[object] = None):
        super().__init__(parent)
        self._room = room

        self.setWindowTitle(
            "Редактирование аудитории" if room is not None else "Добавление аудитории"
        )
        self.resize(470, 280)

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

        hint = QLabel(
            "Можно выбрать несколько типов одновременно.\n"
            "Главный тип определяется автоматически по приоритету:\n"
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
        self._update_primary_type_preview()

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
        priority = ["lab", "computer", "lecture", "classroom"]
        selected.sort(key=lambda x: priority.index(x) if x in priority else 999)
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

    def get_data(self) -> tuple[str, str, list[str], int]:
        room_number = self.room_number_combo.currentText().strip()
        room_types = self._get_selected_room_types()
        primary_room_type = self._get_primary_room_type()
        capacity = int(self.capacity_spin.value())
        return room_number, primary_room_type, room_types, capacity


class RoomsPage(QWidget):
    """
    Страница аудиторий.

    Показывает:
    - ID
    - номер/название аудитории
    - список типов аудитории
    - вместимость

    Важно:
    - ID не вводится вручную;
    - одна аудитория может подходить для нескольких типов занятий;
    - главный тип определяется по приоритету:
      lab > computer > lecture > classroom
    """

    def __init__(self, rooms_repo):
        super().__init__()
        self._rooms_repo = rooms_repo

        root = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        root.addLayout(toolbar)

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
        dlg = RoomEditDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        room_number, room_type, room_types, capacity = dlg.get_data()

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

        if int(capacity) <= 0:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Вместимость должна быть больше 0.",
            )
            return

        try:
            self._rooms_repo.create(
                room_number=room_number,
                room_type=room_type,
                room_types=room_types,
                capacity=int(capacity),
                building=None,
            )
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

        dlg = RoomEditDialog(self, room=room)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        room_number, room_type, room_types, capacity = dlg.get_data()

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
                room_type=room_type,
                room_types=room_types,
                capacity=int(capacity),
                building=None,
            )
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
            rows = self._rooms_repo.list_all()
        except Exception as exc:
            self.table.setRowCount(0)
            self._set_status(f"Не удалось загрузить аудитории: {exc}", error=True)
            return

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