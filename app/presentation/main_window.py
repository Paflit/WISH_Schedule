from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow,
    QTabWidget,
)

from app.presentation.pages.curriculum_page import CurriculumPage
from app.presentation.pages.drafts_page import DraftsPage
from app.presentation.pages.editor_page import EditorPage
from app.presentation.pages.generate_page import GeneratePage
from app.presentation.pages.groups_page import GroupsPage
from app.presentation.pages.rooms_page import RoomsPage
from app.presentation.pages.teachers_page import TeachersPage
from app.presentation.viewmodels.editor_vm import EditorViewModel


class MainWindow(QMainWindow):
    def __init__(self, container):
        super().__init__()
        self.container = container

        self.setWindowTitle(self.container.config.app_title)
        self.resize(
            int(self.container.config.window_width),
            int(self.container.config.window_height),
        )
        self.setMinimumSize(1100, 700)

        self._init_ui()

    def _init_ui(self) -> None:
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Pages
        self.groups_page = GroupsPage(
            groups_repo=self.container.groups_repo,
            calendar_repo=self.container.calendar_repo,
        )

        self.rooms_page = RoomsPage(
            rooms_repo=self.container.rooms_repo,
            calendar_repo=self.container.calendar_repo,
        )

        self.curriculum_page = CurriculumPage(
            curriculum_repo=self.container.curriculum_repo,
            groups_repo=self.container.groups_repo,
            subjects_repo=self.container.subjects_repo,
            calendar_repo=self.container.calendar_repo,
        )

        self.teachers_page = TeachersPage(
            teachers_repo=self.container.teachers_repo,
            subjects_repo=self.container.subjects_repo,
            calendar_repo=self.container.calendar_repo,
        )

        self.drafts_page = DraftsPage(
            schedule_repo=self.container.schedule_repo,
            calendar_repo=self.container.calendar_repo,
            event_builder=self.container.event_builder,
            config=self.container.config,
            groups_repo=self.container.groups_repo,
            subjects_repo=self.container.subjects_repo,
            rooms_repo=self.container.rooms_repo,
            teachers_repo=self.container.teachers_repo,
        )

        self.generate_page = GeneratePage(
            calendar_repo=self.container.calendar_repo,
            schedule_repo=self.container.schedule_repo,
            event_builder=self.container.event_builder,
            config=self.container.config,
            rules=self.container.rule_profiles.get("balanced"),
        )

        self.editor_vm = EditorViewModel(
            schedule_repo=self.container.schedule_repo,
            apply_manual_edit_uc=self.container.apply_manual_edit_uc,
        )
        self.editor_page = EditorPage(
            vm=self.editor_vm,
            calendar_repo=self.container.calendar_repo,
        )
        self.editor_page.configure_creation_support(
            event_builder=self.container.event_builder,
            config=self.container.config,
            groups_repo=self.container.groups_repo,
            subjects_repo=self.container.subjects_repo,
            rooms_repo=self.container.rooms_repo,
            teachers_repo=self.container.teachers_repo,
        )

        # Tabs
        self.tabs.addTab(self.groups_page, "Группы")
        self.tabs.addTab(self.rooms_page, "Аудитории")
        self.tabs.addTab(self.curriculum_page, "Учебный план")
        self.tabs.addTab(self.teachers_page, "Преподаватели")
        self.tabs.addTab(self.drafts_page, "Черновики")
        self.tabs.addTab(self.generate_page, "Генерация")
        self.tabs.addTab(self.editor_page, "Расписание")

        # Cross-page wiring
        self.generate_page.variantOpenRequested.connect(self._open_variant_in_editor)
        self.groups_page.calendarCreated.connect(self._on_calendar_created)
        self.rooms_page.calendarCreated.connect(self._on_calendar_created)
        self.curriculum_page.calendarCreated.connect(self._on_calendar_created)
        self.teachers_page.calendarCreated.connect(self._on_calendar_created)
        self.generate_page.calendarCreated.connect(self._on_calendar_created)

    def _open_variant_in_editor(self, variant_id: int) -> None:
        self.editor_page.open_variant(int(variant_id))
        self.tabs.setCurrentWidget(self.editor_page)

    def _on_calendar_created(self, calendar_id: int) -> None:
        target_calendar_id = int(calendar_id)
        for page in (
            self.groups_page,
            self.rooms_page,
            self.curriculum_page,
            self.teachers_page,
            self.drafts_page,
            self.generate_page,
            self.editor_page,
        ):
            refresh_method = getattr(page, "refresh_calendars", None)
            if callable(refresh_method):
                refresh_method(target_calendar_id)
