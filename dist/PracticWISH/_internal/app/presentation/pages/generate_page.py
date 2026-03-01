# app/presentation/pages/generate_page.py
"""
GeneratePage

Экран генерации расписания.

Функции:
- выбрать семестр (calendar_id)
- выбрать профиль правил (students/teachers/balanced)
- указать лимит времени и число вариантов
- нажать "Сгенерировать"
- показать список вариантов (score)
- открыть вариант в Editor/Variants (через сигнал/коллбек)

GUI -> GenerateScheduleUseCase
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QSpinBox,
    QMessageBox,
    QListWidget,
    QListWidgetItem,
)

from app.application.use_cases.generate_schedule import GenerateScheduleCommand


class GeneratePage(QWidget):

    def __init__(self, container):
        super().__init__()
        self.container = container

        self.calendar_repo = container.calendar_repo
        self.rule_profiles = container.rule_profiles
        self.generate_uc = container.generate_schedule_uc

        self._init_ui()
        self._load_calendars()
        self._load_profiles()

    # ---------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout()

        # Calendar + Profile
        top_layout = QHBoxLayout()

        self.calendar_combo = QComboBox()
        self.profile_combo = QComboBox()

        top_layout.addWidget(QLabel("Семестр:"))
        top_layout.addWidget(self.calendar_combo)
        top_layout.addWidget(QLabel("Профиль:"))
        top_layout.addWidget(self.profile_combo)

        layout.addLayout(top_layout)

        # Solver settings
        settings_layout = QHBoxLayout()

        self.time_limit_spin = QSpinBox()
        self.time_limit_spin.setRange(1, 600)
        self.time_limit_spin.setValue(self.container.config.solver_time_limit_seconds)

        self.variants_spin = QSpinBox()
        self.variants_spin.setRange(1, 30)
        self.variants_spin.setValue(self.container.config.solver_variants_count)

        settings_layout.addWidget(QLabel("Лимит (сек):"))
        settings_layout.addWidget(self.time_limit_spin)
        settings_layout.addWidget(QLabel("Вариантов:"))
        settings_layout.addWidget(self.variants_spin)

        layout.addLayout(settings_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self.generate_button = QPushButton("Сгенерировать расписание")
        btn_layout.addWidget(self.generate_button)
        layout.addLayout(btn_layout)

        # Output list
        self.variants_list = QListWidget()
        layout.addWidget(QLabel("Сгенерированные варианты:"))
        layout.addWidget(self.variants_list)

        self.setLayout(layout)

        # Signals
        self.generate_button.clicked.connect(self._on_generate)

    # ---------------------------------------------------------

    def _load_calendars(self):
        try:
            calendars = self.calendar_repo.list_all()
            self.calendar_combo.clear()
            for c in calendars:
                self.calendar_combo.addItem(
                    f"{c.academic_year} / Семестр {c.semester}",
                    userData=c.id_calendar,
                )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _load_profiles(self):
        self.profile_combo.clear()
        for key in self.rule_profiles.list_keys():
            self.profile_combo.addItem(key, userData=key)

    # ---------------------------------------------------------

    def _on_generate(self):
        calendar_id = self.calendar_combo.currentData()
        profile_key = self.profile_combo.currentData()

        if not calendar_id:
            QMessageBox.warning(self, "Нет семестра", "Выберите семестр.")
            return

        try:
            cmd = GenerateScheduleCommand(
                calendar_id=calendar_id,
                rule_profile_key=profile_key,
                variants_count=self.variants_spin.value(),
                time_limit_seconds=self.time_limit_spin.value(),
            )

            result = self.generate_uc.execute(cmd)

            self.variants_list.clear()

            for v in result.variants:
                item = QListWidgetItem(f"{v.name} | score={v.objective_score}")
                item.setData(32, v.id_variant)  # Qt.UserRole
                self.variants_list.addItem(item)

            QMessageBox.information(self, "Готово", f"Сгенерировано вариантов: {len(result.variants)}")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка генерации", str(e))