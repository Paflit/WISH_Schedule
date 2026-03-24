from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow,
    QTabWidget,
)

from app.presentation.pages.curriculum_page import CurriculumPage
from app.presentation.pages.editor_page import EditorPage
from app.presentation.pages.generate_page import GeneratePage
from app.presentation.pages.groups_page import GroupsPage
from app.presentation.pages.rooms_page import RoomsPage
from app.presentation.pages.teachers_page import TeachersPage
from app.presentation.pages.variants_page import VariantsPage
from app.presentation.viewmodels.editor_vm import EditorViewModel


class MainWindow(QMainWindow):
    """
    Главное окно приложения.

    Здесь создаются только актуальные страницы и передаются уже
    конкретные зависимости из container, а не сам container целиком.
    """

    def __init__(self, container):
        super().__init__()
        self.container = container

        self.setWindowTitle(self.container.config.app_title)
        self.resize(
            int(self.container.config.window_width),
            int(self.container.config.window_height),
        )

        self._init_ui()

    def _init_ui(self) -> None:
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # -----------------------------------------------------
        # Pages
        # -----------------------------------------------------
        self.teachers_page = TeachersPage(
            teachers_repo=self.container.teachers_repo,
            subjects_repo=self.container.subjects_repo,
            calendar_repo=self.container.calendar_repo,
        )

        self.groups_page = GroupsPage(
            groups_repo=self.container.groups_repo,
        )

        self.rooms_page = RoomsPage(
            rooms_repo=self.container.rooms_repo,
        )

        self.curriculum_page = CurriculumPage(
            curriculum_repo=self.container.curriculum_repo,
            groups_repo=self.container.groups_repo,
            subjects_repo=self.container.subjects_repo,
            calendar_repo=self.container.calendar_repo,
        )

        self.generate_page = GeneratePage(
            calendar_repo=self.container.calendar_repo,
            schedule_repo=self.container.schedule_repo,
        )

        self.variants_page = VariantsPage(
            schedule_repo=self.container.schedule_repo,
            calendar_repo=self.container.calendar_repo,
        )

        self.editor_vm = EditorViewModel(
            schedule_repo=self.container.schedule_repo,
            apply_manual_edit_uc=self.container.apply_manual_edit_uc,
        )
        self.editor_page = EditorPage(
            vm=self.editor_vm,
        )

        # -----------------------------------------------------
        # Tabs
        # -----------------------------------------------------
        self.tabs.addTab(self.teachers_page, "Преподаватели")
        self.tabs.addTab(self.groups_page, "Группы")
        self.tabs.addTab(self.rooms_page, "Аудитории")
        self.tabs.addTab(self.curriculum_page, "Учебный план")
        self.tabs.addTab(self.generate_page, "Генерация")
        self.tabs.addTab(self.variants_page, "Варианты")
        self.tabs.addTab(self.editor_page, "Расписание")

        # -----------------------------------------------------
        # Cross-page wiring
        # -----------------------------------------------------
        self.variants_page.variantOpenRequested.connect(self._open_variant_in_editor)

    def _open_variant_in_editor(self, variant_id: int) -> None:
        self.editor_vm.load_variant(int(variant_id))
        self.tabs.setCurrentWidget(self.editor_page)