# app/presentation/main_window.py
"""
MainWindow — главное окно desktop-приложения (PyQt6).

Требования к архитектуре:
- MainWindow отвечает за layout и навигацию (QTabWidget)
- НЕ импортирует viewmodels напрямую
- НЕ использует инфраструктуру напрямую
- Работает только с Pages (presentation/pages/*)

Страницы внутри сами создают нужные ViewModel через container (DI).
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QTabWidget,
    QVBoxLayout,
    QMessageBox,
)

from app.domain.exceptions import DomainError
from app.presentation.pages.teachers_page import TeachersPage
from app.presentation.pages.subjects_page import SubjectsPage
from app.presentation.pages.groups_page import GroupsPage
from app.presentation.pages.rooms_page import RoomsPage
from app.presentation.pages.calendar_page import CalendarPage
from app.presentation.pages.curriculum_page import CurriculumPage
from app.presentation.pages.generate_page import GeneratePage
from app.presentation.pages.variants_page import VariantsPage
from app.presentation.pages.editor_page import EditorPage


class MainWindow(QMainWindow):
    """
    Главное окно:
    - вкладки (QTabWidget) для страниц
    - единый способ показывать ошибки
    """

    def __init__(self, container):
        super().__init__()
        self.container = container

        self.setWindowTitle("PracticWISH — Оптимизация учебного расписания")
        self.setMinimumSize(1200, 800)

        self._init_ui()

    # ---------------------------------------------------------

    def _init_ui(self):
        central = QWidget(self)
        layout = QVBoxLayout(central)

        self.tabs = QTabWidget(central)

        # -----------------------------
        # Справочники (раздельные вкладки)
        # -----------------------------
        self.tabs.addTab(TeachersPage(self.container), "Преподаватели")
        self.tabs.addTab(SubjectsPage(self.container), "Дисциплины")
        self.tabs.addTab(GroupsPage(self.container), "Группы")
        self.tabs.addTab(RoomsPage(self.container), "Аудитории")

        # -----------------------------
        # Планирование
        # -----------------------------
        self.tabs.addTab(CalendarPage(self.container), "Календарь")
        self.tabs.addTab(CurriculumPage(self.container), "Учебный план")

        # -----------------------------
        # Генерация / варианты / редактор
        # -----------------------------
        self.tabs.addTab(GeneratePage(self.container), "Генерация")
        self.tabs.addTab(VariantsPage(self.container), "Варианты")
        self.tabs.addTab(EditorPage(self.container), "Редактор")

        layout.addWidget(self.tabs)
        self.setCentralWidget(central)

    # ---------------------------------------------------------

    def show_error(self, error: Exception) -> None:
        """
        Унифицированный вывод ошибок (можно вызывать со страниц).
        """
        if isinstance(error, DomainError):
            QMessageBox.warning(self, "Ошибка", str(error))
        else:
            QMessageBox.critical(self, "Системная ошибка", str(error))