# app/presentation/pages/rooms_page.py
"""
RoomsPage

Экран справочника "Аудитории".

Функции (MVP):
- просмотр списка аудиторий
- кнопки добавления/редактирования/удаления (заготовка)
- обновление

Полезно для проверки:
- тип аудитории (lecture / computer / lab / etc.)
- вместимость
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


class RoomsPage(QWidget):

    def __init__(self, container):
        super().__init__()
        self.container = container
        self.rooms_repo = container.rooms_repo

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
        self.table.setHorizontalHeaderLabels(["ID", "Номер", "Тип", "Вместимость", "Корпус"])
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

    # ---------------------------------------------------------

    def _not_implemented(self):
        QMessageBox.information(self, "MVP", "Редактирование справочников будет добавлено позже.")