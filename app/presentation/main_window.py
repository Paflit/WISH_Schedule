from __future__ import annotations

import shutil
import sqlite3
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QTabWidget,
    QWidget,
)

from app.config import AppConfig
from app.di import build_container
from app.presentation.pages.curriculum_page import CurriculumPage
from app.presentation.pages.drafts_page import DraftsPage
from app.presentation.pages.editor_page import EditorPage
from app.presentation.pages.generate_page import GeneratePage
from app.presentation.pages.groups_page import GroupsPage
from app.presentation.pages.rooms_page import RoomsPage
from app.presentation.pages.teachers_page import TeachersPage
from app.presentation.database_selector import choose_database
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

        self._root = None
        self._db_button = None
        self._init_ui()

    def _db_path(self) -> Path:
        db_url = str(self.container.config.db_url)
        return Path(db_url.replace("sqlite:///", "", 1))

    def _init_ui(self) -> None:
        self._root = QVBoxLayout()
        root_widget = QWidget()
        root_widget.setLayout(self._root)
        top_bar = QHBoxLayout()
        self._root.addLayout(top_bar)
        self._db_button = QPushButton(f"БД: {self._db_path().name}")
        self._db_button.setToolTip("Нажмите, чтобы переключить базу данных")
        self._db_button.clicked.connect(self._switch_database_dialog)
        top_bar.addWidget(self._db_button)
        top_bar.addStretch(1)
        self.save_db_btn = QPushButton("Сохранить базу данных")
        top_bar.addWidget(self.save_db_btn)
        self.save_db_btn.clicked.connect(self._save_database_dialog)

        self.tabs = QTabWidget()
        self._root.addWidget(self.tabs, 1)
        self.setCentralWidget(root_widget)

        self._build_pages()

    def _build_pages(self) -> None:
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if widget is not None:
                widget.deleteLater()

        # Pages
        self.groups_page = GroupsPage(
            groups_repo=self.container.groups_repo,
            calendar_repo=self.container.calendar_repo,
        )

        self.rooms_page = RoomsPage(
            rooms_repo=self.container.rooms_repo,
            calendar_repo=self.container.calendar_repo,
            subjects_repo=self.container.subjects_repo,
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
            groups_repo=self.container.groups_repo,
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

    def _switch_database_dialog(self) -> None:
        selected_path = choose_database(self, force=True)
        if selected_path is None:
            QMessageBox.information(self, "Базы данных", "В папке data нет других файлов .db/.bd для выбора.")
            return
        if selected_path.resolve() == self._db_path().resolve():
            return

        os.environ["APP_DB_PATH"] = str(selected_path)
        try:
            self.container = build_container(AppConfig.load())
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть базу данных:\n{exc}")
            return

        if self._db_button is not None:
            self._db_button.setText(f"БД: {self._db_path().name}")
        self._build_pages()
        QMessageBox.information(self, "База данных", f"Открыта база данных:\n{selected_path.name}")

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

    def _save_database_dialog(self) -> None:
        source_path = self._db_path()
        if not source_path.exists():
            QMessageBox.warning(self, "Ошибка", f"Файл БД не найден: {source_path}")
            return
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить базу данных",
            str(source_path.with_name(source_path.stem + "_copy" + source_path.suffix)),
            "SQLite DB (*.db *.bd);;All files (*)",
        )
        if not target_path:
            return

        calendars = list(self.container.calendar_repo.list_calendars() or [])
        dlg = QDialog(self)
        dlg.setWindowTitle("Состав сохраняемой базы")
        layout = QVBoxLayout(dlg)
        all_cb = QCheckBox("Сохранить все данные")
        all_cb.setChecked(True)
        layout.addWidget(all_cb)
        calendar_checks = []
        for cal in calendars:
            cb = QCheckBox(f"{getattr(cal, 'academic_year', '')} | семестр {getattr(cal, 'semester', '')}")
            cb.setChecked(True)
            cb.setEnabled(False)
            cb.setProperty("calendar_id", int(getattr(cal, "id_calendar", 0) or 0))
            layout.addWidget(cb)
            calendar_checks.append(cb)
        all_cb.toggled.connect(lambda checked: [cb.setEnabled(not checked) for cb in calendar_checks])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        shutil.copy2(source_path, target_path)
        if not all_cb.isChecked():
            keep_ids = [int(cb.property("calendar_id")) for cb in calendar_checks if cb.isChecked()]
            self._prune_database_calendars(Path(target_path), keep_ids)
        QMessageBox.information(self, "Готово", f"База данных сохранена:\n{target_path}")

    def _prune_database_calendars(self, db_path: Path, keep_calendar_ids: list[int]) -> None:
        if not keep_calendar_ids:
            return
        placeholders = ",".join("?" for _ in keep_calendar_ids)
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                f"DELETE FROM AcademicCalendar WHERE id_calendar NOT IN ({placeholders})",
                tuple(int(x) for x in keep_calendar_ids),
            )
            conn.commit()
