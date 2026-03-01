# app/presentation/pages/subjects_page.py
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox
)


class SubjectDialog(QDialog):
    def __init__(self, parent=None, *, title: str, id_value: int | None = None, name_value: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)

        layout = QFormLayout(self)

        self.id_spin = QSpinBox()
        self.id_spin.setRange(1, 10**9)
        if id_value is not None:
            self.id_spin.setValue(id_value)
            self.id_spin.setEnabled(False)  # ID не меняем при редактировании

        self.name_edit = QLineEdit()
        self.name_edit.setText(name_value)

        layout.addRow("ID:", self.id_spin)
        layout.addRow("Название:", self.name_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> tuple[int, str]:
        return self.id_spin.value(), self.name_edit.text().strip()


class SubjectsPage(QWidget):
    def __init__(self, container):
        super().__init__()
        self.container = container
        self.subjects_repo = container.subjects_repo

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
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["ID", "Название дисциплины"])
        layout.addWidget(self.table)

        self.setLayout(layout)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_add.clicked.connect(self.add_subject)
        self.btn_edit.clicked.connect(self.edit_subject)
        self.btn_delete.clicked.connect(self.delete_subject)

    def refresh(self):
        try:
            subjects = self.subjects_repo.list_all()
            self.table.setRowCount(len(subjects))
            for row, s in enumerate(subjects):
                self.table.setItem(row, 0, QTableWidgetItem(str(s.id_subject)))
                self.table.setItem(row, 1, QTableWidgetItem(s.subject_name))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return int(item.text())

    def add_subject(self):
        dlg = SubjectDialog(self, title="Добавить дисциплину")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        sid, name = dlg.values()
        if not name:
            QMessageBox.warning(self, "Проверка", "Название дисциплины не может быть пустым.")
            return

        try:
            self.subjects_repo.upsert(sid, name)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def edit_subject(self):
        sid = self._selected_id()
        if sid is None:
            QMessageBox.warning(self, "Нет выбора", "Выберите дисциплину.")
            return

        # Получим текущее имя из таблицы
        row = self.table.currentRow()
        name_item = self.table.item(row, 1)
        current_name = name_item.text() if name_item else ""

        dlg = SubjectDialog(self, title="Редактировать дисциплину", id_value=sid, name_value=current_name)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        _sid, name = dlg.values()
        if not name:
            QMessageBox.warning(self, "Проверка", "Название дисциплины не может быть пустым.")
            return

        try:
            self.subjects_repo.upsert(sid, name)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def delete_subject(self):
        sid = self._selected_id()
        if sid is None:
            QMessageBox.warning(self, "Нет выбора", "Выберите дисциплину.")
            return

        try:
            self.subjects_repo.delete(sid)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))