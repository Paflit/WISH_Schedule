from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QSpinBox, QCheckBox, QDialogButtonBox
)


class TeacherDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        title: str,
        id_value: int | None = None,
        name_value: str = "",
        hard_max: int = 6,
        soft_max: int = 4,
        method_day: bool = True,
        commentary: str = "",
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

        self.name_edit = QLineEdit()
        self.name_edit.setText(name_value)

        self.hard_spin = QSpinBox()
        self.hard_spin.setRange(1, 12)
        self.hard_spin.setValue(hard_max)

        self.soft_spin = QSpinBox()
        self.soft_spin.setRange(1, 12)
        self.soft_spin.setValue(soft_max)

        self.method_chk = QCheckBox("Нужен методический день")
        self.method_chk.setChecked(bool(method_day))

        self.comment_edit = QLineEdit()
        self.comment_edit.setText(commentary or "")

        layout.addRow("ID:", self.id_spin)
        layout.addRow("ФИО:", self.name_edit)
        layout.addRow("Hard max (пары/день):", self.hard_spin)
        layout.addRow("Soft max (пары/день):", self.soft_spin)
        layout.addRow("", self.method_chk)
        layout.addRow("Комментарий:", self.comment_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return (
            self.id_spin.value(),
            self.name_edit.text().strip(),
            self.hard_spin.value(),
            self.soft_spin.value(),
            self.method_chk.isChecked(),
            self.comment_edit.text().strip() or None,
        )


class TeachersPage(QWidget):
    def __init__(self, container):
        super().__init__()
        self.container = container
        self.teachers_repo = container.teachers_repo

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
        self.table.setHorizontalHeaderLabels([
            "ID",
            "ФИО",
            "Hard max (пары/день)",
            "Soft max (пары/день)",
            "Методдень",
        ])
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_add.clicked.connect(self.add_teacher)
        self.btn_edit.clicked.connect(self.edit_teacher)
        self.btn_delete.clicked.connect(self.delete_teacher)

    def refresh(self):
        try:
            teachers = self.teachers_repo.list_all()
            self.table.setRowCount(len(teachers))

            for row, t in enumerate(teachers):
                self.table.setItem(row, 0, QTableWidgetItem(str(t.id_teacher)))
                self.table.setItem(row, 1, QTableWidgetItem(t.full_name))
                self.table.setItem(row, 2, QTableWidgetItem(str(t.hard_max_pairs_per_day)))
                self.table.setItem(row, 3, QTableWidgetItem(str(t.soft_max_pairs_per_day)))
                self.table.setItem(row, 4, QTableWidgetItem("Да" if t.needs_method_day else "Нет"))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return int(item.text()) if item else None

    def add_teacher(self):
        dlg = TeacherDialog(self, title="Добавить преподавателя")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        tid, name, hard_max, soft_max, method_day, commentary = dlg.values()
        if not name:
            QMessageBox.warning(self, "Проверка", "ФИО не может быть пустым.")
            return
        if soft_max > hard_max:
            QMessageBox.warning(self, "Проверка", "Soft max не может быть больше Hard max.")
            return

        try:
            self.teachers_repo.upsert(
                tid, name, hard_max=hard_max, soft_max=soft_max,
                needs_method_day=method_day, commentary=commentary
            )
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def edit_teacher(self):
        tid = self._selected_id()
        if tid is None:
            QMessageBox.warning(self, "Нет выбора", "Выберите преподавателя.")
            return

        row = self.table.currentRow()
        name = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
        hard_max = int(self.table.item(row, 2).text()) if self.table.item(row, 2) else 6
        soft_max = int(self.table.item(row, 3).text()) if self.table.item(row, 3) else 4
        method_day = (self.table.item(row, 4).text() == "Да") if self.table.item(row, 4) else True

        dlg = TeacherDialog(
            self,
            title="Редактировать преподавателя",
            id_value=tid,
            name_value=name,
            hard_max=hard_max,
            soft_max=soft_max,
            method_day=method_day,
            is_edit=True,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        _tid, name, hard_max, soft_max, method_day, commentary = dlg.values()
        if not name:
            QMessageBox.warning(self, "Проверка", "ФИО не может быть пустым.")
            return
        if soft_max > hard_max:
            QMessageBox.warning(self, "Проверка", "Soft max не может быть больше Hard max.")
            return

        try:
            self.teachers_repo.upsert(
                tid, name, hard_max=hard_max, soft_max=soft_max,
                needs_method_day=method_day, commentary=commentary
            )
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def delete_teacher(self):
        tid = self._selected_id()
        if tid is None:
            QMessageBox.warning(self, "Нет выбора", "Выберите преподавателя.")
            return

        try:
            self.teachers_repo.delete(tid)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))