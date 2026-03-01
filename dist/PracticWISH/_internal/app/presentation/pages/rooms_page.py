from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QSpinBox, QComboBox, QDialogButtonBox
)


class RoomDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        title: str,
        id_value: int | None = None,
        number_value: str = "",
        type_value: str = "lecture",
        capacity_value: int = 30,
        building_value: str = "",
        is_edit: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        layout = QFormLayout(self)

        self.id_spin = QSpinBox()
        self.id_spin.setRange(1, 10**9)
        if id_value is not None:
            self.id_spin.setValue(id_value)
            if is_edit:
                self.id_spin.setEnabled(False)

        self.number_edit = QLineEdit()
        self.number_edit.setText(number_value)

        self.type_combo = QComboBox()
        self.type_combo.addItem("Лекционная (lecture)", "lecture")
        self.type_combo.addItem("Компьютерный класс (computer)", "computer")
        self.type_combo.addItem("Лаборатория (lab)", "lab")
        self.type_combo.addItem("Учебная (classroom)", "classroom")
        idx = self.type_combo.findData(type_value)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)

        self.capacity_spin = QSpinBox()
        self.capacity_spin.setRange(1, 1000)
        self.capacity_spin.setValue(int(capacity_value) if capacity_value else 30)

        self.building_edit = QLineEdit()
        self.building_edit.setText(building_value or "")

        layout.addRow("ID:", self.id_spin)
        layout.addRow("Номер аудитории:", self.number_edit)
        layout.addRow("Тип:", self.type_combo)
        layout.addRow("Вместимость:", self.capacity_spin)
        layout.addRow("Корпус:", self.building_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        b = self.building_edit.text().strip()
        return (
            self.id_spin.value(),
            self.number_edit.text().strip(),
            self.type_combo.currentData(),
            self.capacity_spin.value(),
            b or None,
        )


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
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Номер", "Тип", "Вместимость", "Корпус"])
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
                self.table.setItem(row, 2, QTableWidgetItem(r.room_type))
                self.table.setItem(row, 3, QTableWidgetItem(str(r.capacity)))
                self.table.setItem(row, 4, QTableWidgetItem("" if r.building is None else str(r.building)))
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

        rid, number, rtype, cap, building = dlg.values()
        if not number:
            QMessageBox.warning(self, "Проверка", "Номер аудитории не может быть пустым.")
            return

        try:
            self.rooms_repo.upsert(rid, number, rtype, cap, building=building)
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
        rtype = self.table.item(row, 2).text() if self.table.item(row, 2) else "lecture"
        cap = int(self.table.item(row, 3).text()) if self.table.item(row, 3) else 30
        building = self.table.item(row, 4).text() if self.table.item(row, 4) else ""

        dlg = RoomDialog(
            self,
            title="Редактировать аудиторию",
            id_value=rid,
            number_value=number,
            type_value=rtype,
            capacity_value=cap,
            building_value=building,
            is_edit=True,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        _rid, number, rtype, cap, building = dlg.values()
        if not number:
            QMessageBox.warning(self, "Проверка", "Номер аудитории не может быть пустым.")
            return

        try:
            self.rooms_repo.upsert(rid, number, rtype, cap, building=building)
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