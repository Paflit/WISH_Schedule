# app/presentation/pages/teachers_page.py
"""
TeachersPage

Экран справочника "Преподаватели".

Функции (MVP):
- просмотр списка преподавателей
- отображение ограничений нагрузки (soft/hard)
- кнопки добавления/редактирования/удаления (заготовка)
- обновление

Расширение:
- форма пожеланий/доступности (TeacherAvailability)
- привязка дисциплин (TeacherSubjects)
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
)


class TeachersPage(QWidget):

    def __init__(self, container):
        super().__init__()
        self.container = container
        self.teachers_repo = container.teachers_repo

        self._init_ui()
        self.refresh()

    # ---------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout()

        # Buttons
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

        # Table
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

        # Signals
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_add.clicked.connect(self._not_implemented)
        self.btn_edit.clicked.connect(self._not_implemented)
        self.btn_delete.clicked.connect(self._not_implemented)

    # ---------------------------------------------------------

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

    # ---------------------------------------------------------

    def _not_implemented(self):
        QMessageBox.information(self, "MVP", "Редактирование справочника будет добавлено позже.")