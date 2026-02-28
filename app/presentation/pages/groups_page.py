# app/presentation/pages/groups_page.py
"""
GroupsPage

Экран справочника "Группы".

Функции (MVP):
- просмотр списка групп
- добавление / редактирование / удаление (заготовка кнопок)
- обновление данных

Примечание:
В этом варианте мы напрямую читаем через repo из контейнера.
Позже лучше:
- сделать DictionariesViewModel (MVVM)
- и вызывать use-cases для изменения справочников
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


class GroupsPage(QWidget):

    def __init__(self, container):
        super().__init__()
        self.container = container
        self.groups_repo = container.groups_repo

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
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Название", "Курс", "Количество"])
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
            groups = self.groups_repo.list_all()
            self.table.setRowCount(len(groups))

            for row, g in enumerate(groups):
                self.table.setItem(row, 0, QTableWidgetItem(str(g.id_group)))
                self.table.setItem(row, 1, QTableWidgetItem(g.group_name))
                # year может быть None — покажем пусто
                self.table.setItem(row, 2, QTableWidgetItem("" if g.year is None else str(g.year)))
                self.table.setItem(row, 3, QTableWidgetItem(str(g.quantity)))

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    # ---------------------------------------------------------

    def _not_implemented(self):
        QMessageBox.information(self, "MVP", "Редактирование справочников будет добавлено позже.")