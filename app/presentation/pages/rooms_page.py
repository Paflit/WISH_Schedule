from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QSpinBox,
    QDialogButtonBox, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt


# Какие типы поддерживаем (можешь расширять)
ROOM_TYPES = [
    ("lecture", "Лекционная"),
    ("classroom", "Учебная"),
    ("computer", "Компьютерный класс"),
    ("lab", "Лаборатория"),
]


def types_to_csv(types: list[str]) -> str:
    # сохраняем в БД как "lecture,classroom"
    unique = []
    for t in types:
        t = t.strip()
        if t and t not in unique:
            unique.append(t)
    return ",".join(unique)


def csv_to_types(s: str | None) -> list[str]:
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


def type_label(code: str) -> str:
    for c, name in ROOM_TYPES:
        if c == code:
            return name
    return code


def type_labels_csv(csv: str | None) -> str:
    types = csv_to_types(csv)
    if not types:
        return "—"
    return ", ".join(type_label(t) for t in types)


class RoomDialog(QDialog):
    """
    Диалог добавления/редактирования аудитории:
    - номер
    - мультивыбор типов
    - вместимость
    """

    def __init__(
        self,
        parent=None,
        *,
        title: str,
        number_value: str = "",
        types_csv_value: str = "classroom",
        capacity_value: int = 30,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        layout = QFormLayout(self)

        self.number_edit = QLineEdit()
        self.number_edit.setText(number_value)

        self.types_list = QListWidget()
        self.types_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        selected = set(csv_to_types(types_csv_value))

        for code, name in ROOM_TYPES:
            item = QListWidgetItem(f"{name} ({code})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if code in selected else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.types_list.addItem(item)

        self.capacity_spin = QSpinBox()
        self.capacity_spin.setRange(1, 1000)
        self.capacity_spin.setValue(int(capacity_value) if capacity_value else 30)

        layout.addRow("Номер аудитории:", self.number_edit)
        layout.addRow("Типы аудитории:", self.types_list)
        layout.addRow("Вместимость:", self.capacity_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        number = self.number_edit.text().strip()
        capacity = int(self.capacity_spin.value())

        chosen = []
        for i in range(self.types_list.count()):
            item = self.types_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                chosen.append(str(item.data(Qt.ItemDataRole.UserRole)))

        return number, chosen, capacity


class RoomsPage(QWidget):
    def __init__(self, container):
        super().__init__()
        self.container = container
        self.rooms_repo = container.rooms_repo

        self._init_ui()
        self.refresh()

    def _init_ui(self):
        layout = QVBoxLayout()

        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Обновить")
        self.btn_add = QPushButton("Добавить")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_delete = QPushButton("Удалить")

        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Номер", "Типы", "Вместимость"])
        layout.addWidget(self.table)

        self.setLayout(layout)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_add.clicked.connect(self.add_room)
        self.btn_edit.clicked.connect(self.edit_room)
        self.btn_delete.clicked.connect(self.delete_room)

    def refresh(self):
        try:
            rooms = self.rooms_repo.list_all()
            self.table.setRowCount(len(rooms))

            for row, r in enumerate(rooms):
                self.table.setItem(row, 0, QTableWidgetItem(str(r.id_room)))
                self.table.setItem(row, 1, QTableWidgetItem(str(r.room_number)))

                # room_type теперь CSV: "lecture,classroom"
                self.table.setItem(row, 2, QTableWidgetItem(type_labels_csv(r.room_type)))

                self.table.setItem(row, 3, QTableWidgetItem(str(r.capacity)))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return int(item.text()) if item else None

    def add_room(self):
        dlg = RoomDialog(self, title="Добавить аудиторию")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        number, types, cap = dlg.values()
        if not number:
            QMessageBox.warning(self, "Проверка", "Номер аудитории не может быть пустым.")
            return
        if not types:
            QMessageBox.warning(self, "Проверка", "Выберите хотя бы один тип аудитории.")
            return

        try:
            self.rooms_repo.create(
                room_number=number,
                room_type=types_to_csv(types),
                capacity=cap,
                building=None,  # корпус больше не используем
            )
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def edit_room(self):
        rid = self._selected_id()
        if rid is None:
            QMessageBox.warning(self, "Нет выбора", "Выберите аудиторию.")
            return

        row = self.table.currentRow()
        number = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
        # Здесь в таблице мы показываем лейблы, поэтому подтянем реальное значение из БД:
        room = self.rooms_repo.get_by_id(rid)
        types_csv = room.room_type if room else "classroom"
        cap = int(self.table.item(row, 3).text()) if self.table.item(row, 3) else 30

        dlg = RoomDialog(
            self,
            title="Редактировать аудиторию",
            number_value=number,
            types_csv_value=types_csv,
            capacity_value=cap,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        number, types, cap = dlg.values()
        if not number:
            QMessageBox.warning(self, "Проверка", "Номер аудитории не может быть пустым.")
            return
        if not types:
            QMessageBox.warning(self, "Проверка", "Выберите хотя бы один тип аудитории.")
            return

        try:
            self.rooms_repo.update(
                id_room=rid,
                room_number=number,
                room_type=types_to_csv(types),
                capacity=cap,
                building=None,
            )
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def delete_room(self):
        rid = self._selected_id()
        if rid is None:
            QMessageBox.warning(self, "Нет выбора", "Выберите аудиторию.")
            return

        try:
            self.rooms_repo.delete(rid)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))