# app/presentation/pages/curriculum_page.py
"""
CurriculumPage

Экран для просмотра и управления:
- Учебным планом (CurriculumItems)
- Планом на семестр (CurriculumSemesterPlan)
- Недельной нагрузкой (WeeklyLoadPlan)

MVP:
- Выбор календаря (семестра)
- Таблица дисциплин на семестр
- Отображение часов в семестре
- Кнопка обновления

Расширение:
- Редактирование часов
- Настройка WeeklyLoadPlan
- Диалог распределения по неделям
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


class CurriculumPage(QWidget):

    def __init__(self, container):
        super().__init__()
        self.container = container

        self.calendar_repo = container.calendar_repo
        self.curriculum_repo = container.curriculum_repo

        self._init_ui()
        self._load_calendars()

    # ---------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout()

        # Top panel
        top_layout = QHBoxLayout()

        self.calendar_select = QComboBox()
        self.refresh_button = QPushButton("Обновить")

        top_layout.addWidget(QLabel("Семестр:"))
        top_layout.addWidget(self.calendar_select)
        top_layout.addWidget(self.refresh_button)

        layout.addLayout(top_layout)

        # Table
        self.curriculum_table = QTableWidget()
        self.curriculum_table.setColumnCount(6)
        self.curriculum_table.setHorizontalHeaderLabels([
            "Группа",
            "Дисциплина",
            "Тип",
            "Тип аудитории",
            "Часы в семестре",
            "Комментарий",
        ])

        layout.addWidget(self.curriculum_table)

        self.setLayout(layout)

        # Signals
        self.refresh_button.clicked.connect(self._refresh_curriculum)
        self.calendar_select.currentIndexChanged.connect(self._refresh_curriculum)

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

    def _refresh_curriculum(self):
        calendar_id = self.calendar_select.currentData()
        if not calendar_id:
            return

        try:
            plans = self.curriculum_repo.get_semester_plans(calendar_id)

            self.curriculum_table.setRowCount(len(plans))

            for row, plan in enumerate(plans):
                # Получаем CurriculumItem
                item = self.curriculum_repo.get_curriculum_item(plan.curriculum_id)

                self.curriculum_table.setItem(row, 0, QTableWidgetItem(str(item.group_id)))
                self.curriculum_table.setItem(row, 1, QTableWidgetItem(str(item.subject_id)))
                self.curriculum_table.setItem(row, 2, QTableWidgetItem(item.part_type))
                self.curriculum_table.setItem(row, 3, QTableWidgetItem(item.required_room_type))
                self.curriculum_table.setItem(row, 4, QTableWidgetItem(str(plan.hours_in_semester)))
                self.curriculum_table.setItem(row, 5, QTableWidgetItem(plan.comment or ""))

        except Exception as e:
            QMessageBox.critical(self, "Ошибка загрузки учебного плана", str(e))