# app/presentation/pages/calendar_page.py
"""
CalendarPage

Экран управления:
- Академическим календарём
- Неделями семестра
- Таймслотами (день, пара, время)

В MVP:
- Отображаем список календарей
- Возможность выбрать активный
- Таблица таймслотов
- Кнопка "Обновить"

Бизнес-логика не реализуется здесь.
Страница вызывает controller/use-case через container.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
)


class CalendarPage(QWidget):

    def __init__(self, container):
        super().__init__()
        self.container = container

        self.calendar_repo = container.calendar_repo

        self._init_ui()
        self._load_calendars()

    # ---------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout()

        # Top controls
        top_layout = QHBoxLayout()

        self.calendar_select = QComboBox()
        self.refresh_button = QPushButton("Обновить")

        top_layout.addWidget(QLabel("Семестр:"))
        top_layout.addWidget(self.calendar_select)
        top_layout.addWidget(self.refresh_button)

        layout.addLayout(top_layout)

        # Table for slots
        self.slots_table = QTableWidget()
        self.slots_table.setColumnCount(5)
        self.slots_table.setHorizontalHeaderLabels([
            "Неделя",
            "Тип недели",
            "День",
            "Пара",
            "Обед"
        ])

        layout.addWidget(self.slots_table)

        self.setLayout(layout)

        # Signals
        self.refresh_button.clicked.connect(self._refresh_slots)
        self.calendar_select.currentIndexChanged.connect(self._refresh_slots)

    # ---------------------------------------------------------

    def _load_calendars(self):
        try:
            calendars = self.calendar_repo.list_all()

            self.calendar_select.clear()

            for c in calendars:
                self.calendar_select.addItem(
                    f"{c.academic_year} / Семестр {c.semester}",
                    userData=c.id_calendar
                )

        except Exception as e:
            QMessageBox.critical(self, "Ошибка загрузки календарей", str(e))

    # ---------------------------------------------------------

    def _refresh_slots(self):
        calendar_id = self.calendar_select.currentData()
        if not calendar_id:
            return

        try:
            slots = self.calendar_repo.list_time_slots(calendar_id)

            self.slots_table.setRowCount(len(slots))

            for row, s in enumerate(slots):
                self.slots_table.setItem(row, 0, QTableWidgetItem(str(s.week_number_in_semester)))
                self.slots_table.setItem(row, 1, QTableWidgetItem(str(s.week_type)))
                self.slots_table.setItem(row, 2, QTableWidgetItem(str(s.day_of_week)))
                self.slots_table.setItem(row, 3, QTableWidgetItem(str(s.pair_number)))
                self.slots_table.setItem(row, 4, QTableWidgetItem("Да" if s.is_lunch_break else "Нет"))

        except Exception as e:
            QMessageBox.critical(self, "Ошибка загрузки слотов", str(e))