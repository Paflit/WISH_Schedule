# app/presentation/pages/subjects_page.py
"""
SubjectsPage

Экран справочника "Дисциплины".

Функции (MVP):
- просмотр списка дисциплин
- кнопки добавления/редактирования/удаления (заготовка)
- обновление

Позже можно добавить:
- фильтр/поиск
- привязку дисциплины к типу аудитории по умолчанию
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


class SubjectsPage(QWidget):

    def __init__(self, container):
        super().__init__()
        self.container = container
        self.subjects_repo = container.subjects_repo

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
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["ID", "Название дисциплины"])
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
            subjects = self.subjects_repo.list_all()
            self.table.setRowCount(len(subjects))

            for row, s in enumerate(subjects):
                self.table.setItem(row, 0, QTableWidgetItem(str(s.id_subject)))
                self.table.setItem(row, 1, QTableWidgetItem(s.subject_name))

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    # ---------------------------------------------------------

    def _not_implemented(self):
        QMessageBox.information(self, "MVP", "Редактирование справочника будет добавлено позже.")