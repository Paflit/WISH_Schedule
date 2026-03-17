from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow, QWidget, QTabWidget, QVBoxLayout, QMessageBox

from app.domain.exceptions import DomainError

from app.presentation.pages.teachers_page import TeachersPage
from app.presentation.pages.groups_page import GroupsPage
from app.presentation.pages.rooms_page import RoomsPage
from app.presentation.pages.curriculum_page import CurriculumPage
from app.presentation.pages.generate_page import GeneratePage
from app.presentation.pages.variants_page import VariantsPage
from app.presentation.pages.editor_page import EditorPage


class MainWindow(QMainWindow):
    def __init__(self, container):
        super().__init__()
        self.container = container

        self.setWindowTitle("PracticWISH — Оптимизация учебного расписания")
        self.setMinimumSize(1200, 800)

        self._init_ui()

    def _init_ui(self):
        central = QWidget(self)
        layout = QVBoxLayout(central)

        self.tabs = QTabWidget(central)

        self.teachers_page = TeachersPage(self.container)
        self.groups_page = GroupsPage(self.container)
        self.rooms_page = RoomsPage(self.container)
        self.curriculum_page = CurriculumPage(self.container)

        self.editor_page = EditorPage(self.container)

        self.generate_page = GeneratePage(
            self.container,
            open_variant_callback=self.open_variant_in_editor,
        )

        self.variants_page = VariantsPage(
            self.container,
            open_variant_callback=self.open_variant_in_editor,
        )

        self.tabs.addTab(self.teachers_page, "Преподаватели")
        self.tabs.addTab(self.groups_page, "Группы")
        self.tabs.addTab(self.rooms_page, "Аудитории")
        self.tabs.addTab(self.curriculum_page, "Учебный план")
        self.tabs.addTab(self.generate_page, "Генерация")
        self.tabs.addTab(self.variants_page, "Варианты")
        self.tabs.addTab(self.editor_page, "Расписание")

        layout.addWidget(self.tabs)
        self.setCentralWidget(central)

    def open_variant_in_editor(self, variant_id: int):
        """
        Открывает выбранный вариант во вкладке 'Расписание'.
        """
        try:
            if hasattr(self.editor_page, "set_variant"):
                self.editor_page.set_variant(int(variant_id))
            else:
                combo = getattr(self.editor_page, "variants_combo", None)
                if combo is not None:
                    for i in range(combo.count()):
                        item_data = combo.itemData(i)
                        if item_data is not None and int(item_data) == int(variant_id):
                            combo.setCurrentIndex(i)
                            break

            self.tabs.setCurrentWidget(self.editor_page)

        except Exception as e:
            QMessageBox.critical(self, "Ошибка открытия варианта", str(e))

    def show_error(self, error: Exception) -> None:
        if isinstance(error, DomainError):
            QMessageBox.warning(self, "Ошибка", str(error))
        else:
            QMessageBox.critical(self, "Системная ошибка", str(error))