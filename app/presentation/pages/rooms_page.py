from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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
    - обязательно есть тип аудитории;
    - обязательно есть вместимость.
    """

    ROOM_TYPES = [
        ("Лекционная", "lecture"),
        ("Обычная аудитория", "classroom"),
        ("Компьютерный класс", "computer"),
        ("Лаборатория", "lab"),
    ]

    def __init__(self, parent, room: Optional[object] = None):
        super().__init__(parent)
        self._room = room

        self.setWindowTitle(
            "Редактирование аудитории" if room is not None else "Добавление аудитории"
        )
        self.resize(420, 200)

        root = QVBoxLayout(self)

        form = QFormLayout()
        root.addLayout(form)

        self.room_number_combo = QComboBox()
        self.room_number_combo.setEditable(True)
        self.room_number_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.room_number_combo.setPlaceholderText("Введите номер или название аудитории")
        form.addRow("Аудитория:", self.room_number_combo)

        self.room_type_combo = QComboBox()
        for label, value in self.ROOM_TYPES:
            self.room_type_combo.addItem(label, value)
        form.addRow("Тип аудитории:", self.room_type_combo)

        self.capacity_spin = QSpinBox()
        self.capacity_spin.setRange(1, 5000)
        self.capacity_spin.setValue(30)
        form.addRow("Вместимость:", self.capacity_spin)

        hint = QLabel("ID аудитории создаётся автоматически базой данных.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #667085;")
        root.addWidget(hint)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        root.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self._fill()

    def _fill(self) -> None:
        if self._room is None:
            return

        room_number = str(getattr(self._room, "room_number", "") or "")
        room_type = str(getattr(self._room, "room_type", "") or "")
        capacity = int(getattr(self._room, "capacity", 30) or 30)

        self.room_number_combo.addItem(room_number)
        self.room_number_combo.setCurrentText(room_number)

        idx = self.room_type_combo.findData(room_type)
        if idx >= 0:
            self.room_type_combo.setCurrentIndex(idx)

        self.capacity_spin.setValue(capacity)

    def get_data(self) -> tuple[str, str, int]:
        room_number = self.room_number_combo.currentText().strip()
        room_type = str(self.room_type_combo.currentData() or "")
        capacity = int(self.capacity_spin.value())
        return room_number, room_type, capacity


class RoomsPage(QWidget):
    """
    Страница аудиторий.

    Показывает:
    - ID
    - номер/название аудитории
    - тип аудитории
    - вместимость

    Важно:
    - ID не вводится вручную;
    - данные должны быть пригодны для solver;
    - тип аудитории и вместимость обязательны.
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
            ["ID", "Аудитория", "Тип", "Вместимость"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(2, 180)
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

    def _add_room(self) -> None:
        dlg = RoomEditDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        room_number, room_type, capacity = dlg.get_data()

        if not room_number:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Номер или название аудитории не может быть пустым.",
            )
            return

        if not room_type:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Нужно выбрать тип аудитории.",
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

        room_number, room_type, capacity = dlg.get_data()

        if not room_number:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Номер или название аудитории не может быть пустым.",
            )
            return

        if not room_type:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Нужно выбрать тип аудитории.",
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
            room_type = str(getattr(room, "room_type", "") or "")
            capacity = int(getattr(room, "capacity", 0) or 0)

            id_item = QTableWidgetItem(str(id_room))
            id_item.setData(Qt.ItemDataRole.UserRole, id_room)

            room_item = QTableWidgetItem(room_number)
            type_item = QTableWidgetItem(self._room_type_label(room_type))
            capacity_item = QTableWidgetItem(str(capacity))

            self.table.setItem(row_idx, 0, id_item)
            self.table.setItem(row_idx, 1, room_item)
            self.table.setItem(row_idx, 2, type_item)
            self.table.setItem(row_idx, 3, capacity_item)

        self._set_status(f"Загружено аудиторий: {len(rows)}")