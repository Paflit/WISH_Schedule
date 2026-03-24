# app/presentation/pages/groups_page.py
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QSpinBox, QComboBox, QDialogButtonBox
)

class GroupDialog(QDialog):
    """
    Диалог добавления/редактирования группы.
    Курс выбирается строго из 1..5.
    """

    def __init__(
        self,
        parent=None,
        *,
        title: str,
        name_value: str = "",
        year_value: int = 1,
        quantity_value: int = 25,
        education_form: str = "full-time",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        layout = QFormLayout(self)

        self.name_edit = QLineEdit()
        self.name_edit.setText(name_value)

        # Курс: только 1..5
        self.year_combo = QComboBox()
        for y in [1, 2, 3, 4, 5]:
            self.year_combo.addItem(str(y), y)

        # выставим текущий курс
        try:
            y = int(year_value)
        except Exception:
            y = 1
        idx = self.year_combo.findData(y)
        self.year_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 500)
        self.qty_spin.setValue(int(quantity_value) if quantity_value else 25)

        self.form_combo = QComboBox()
        self.form_combo.addItem("очная (full-time)", "full-time")
        self.form_combo.addItem("очно-заочная (part-time)", "part-time")
        self.form_combo.addItem("заочная (distance)", "distance")
        idx = self.form_combo.findData(education_form)
        if idx >= 0:
            self.form_combo.setCurrentIndex(idx)

        layout.addRow("Группа:", self.name_edit)
        layout.addRow("Курс:", self.year_combo)
        layout.addRow("Количество студентов:", self.qty_spin)
        layout.addRow("Форма обучения:", self.form_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return (
            self.name_edit.text().strip(),
            int(self.year_combo.currentData()),          # всегда 1..5
            int(self.qty_spin.value()),
            str(self.form_combo.currentData()),
        )


class GroupsPage(QWidget):
    def __init__(self, container):
        super().__init__()
        self.container = container
        self.groups_repo = container.groups_repo

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
        self.table.setHorizontalHeaderLabels(["ID", "Название", "Курс", "Количество"])
        layout.addWidget(self.table)

        self.setLayout(layout)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_add.clicked.connect(self.add_group)
        self.btn_edit.clicked.connect(self.edit_group)
        self.btn_delete.clicked.connect(self.delete_group)

    def refresh(self):
        try:
            groups = self.groups_repo.list_all()
            self.table.setRowCount(len(groups))

            for row, g in enumerate(groups):
                self.table.setItem(row, 0, QTableWidgetItem(str(g.id_group)))
                self.table.setItem(row, 1, QTableWidgetItem(g.group_name))
                # курс теперь всегда число 1..5
                self.table.setItem(row, 2, QTableWidgetItem("" if g.year is None else str(g.year)))
                self.table.setItem(row, 3, QTableWidgetItem(str(g.quantity)))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return int(item.text()) if item else None

    def add_group(self):
        dlg = GroupDialog(self, title="Добавить группу", year_value=1, quantity_value=25)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        name, year, qty, form = dlg.values()
        if not name:
            QMessageBox.warning(self, "Проверка", "Название группы не может быть пустым.")
            return

        try:
            self.groups_repo.create(group_name=name, year=year, quantity=qty, education_form=form)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def edit_group(self):
        gid = self._selected_id()
        if gid is None:
            QMessageBox.warning(self, "Нет выбора", "Выберите группу.")
            return

        row = self.table.currentRow()
        name = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
        year_txt = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
        try:
            year = int(year_txt) if year_txt.strip() else 1
        except Exception:
            year = 1
        qty = int(self.table.item(row, 3).text()) if self.table.item(row, 3) else 25

        # education_form не показываем в таблице, оставим full-time по умолчанию (можешь расширить позже)
        dlg = GroupDialog(
            self,
            title="Редактировать группу",
            name_value=name,
            year_value=year,
            quantity_value=qty,
            education_form="full-time",
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        name, year, qty, form = dlg.values()
        if not name:
            QMessageBox.warning(self, "Проверка", "Название группы не может быть пустым.")
            return

        try:
            self.groups_repo.update(id_group=gid, group_name=name, year=year, quantity=qty, education_form=form)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def delete_group(self):
        gid = self._selected_id()
        if gid is None:
            QMessageBox.warning(self, "Нет выбора", "Выберите группу.")
            return

        try:
            self.groups_repo.delete(gid)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))