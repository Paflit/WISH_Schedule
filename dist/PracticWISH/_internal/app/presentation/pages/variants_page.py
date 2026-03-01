# app/presentation/pages/variants_page.py
"""
VariantsPage

Экран просмотра вариантов расписания.

Функции:
- показать список вариантов для выбранного семестра
- показать score/статус/комментарий
- открыть вариант в EditorPage
- переименовать / сменить статус (через SaveVariantUseCase)

MVP:
- таблица вариантов
- кнопка "Обновить"
- кнопка "Открыть в редакторе"
- кнопка "Утвердить" (approved)
"""

from __future__ import annotations

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

from app.application.use_cases.save_variant import SaveVariantCommand


class VariantsPage(QWidget):

    def __init__(self, container):
        super().__init__()
        self.container = container

        self.calendar_repo = container.calendar_repo
        self.schedule_repo = container.schedule_repo
        self.save_variant_uc = container.save_variant_uc

        self._init_ui()
        self._load_calendars()
        self.refresh()

    # ---------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        self.calendar_combo = QComboBox()
        self.btn_refresh = QPushButton("Обновить")
        self.btn_approve = QPushButton("Утвердить (approved)")

        top_layout.addWidget(QLabel("Семестр:"))
        top_layout.addWidget(self.calendar_combo)
        top_layout.addWidget(self.btn_refresh)
        top_layout.addWidget(self.btn_approve)

        layout.addLayout(top_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "ID",
            "Название",
            "Score",
            "Статус",
            "Профиль",
        ])
        layout.addWidget(self.table)

        self.setLayout(layout)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_approve.clicked.connect(self._approve_selected)

    # ---------------------------------------------------------

    def _load_calendars(self):
        try:
            calendars = self.calendar_repo.list_all()
            self.calendar_combo.clear()
            for c in calendars:
                self.calendar_combo.addItem(
                    f"{c.academic_year} / Семестр {c.semester}",
                    userData=c.id_calendar
                )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    # ---------------------------------------------------------

    def refresh(self):
        calendar_id = self.calendar_combo.currentData()
        if not calendar_id:
            return

        try:
            variants = self.schedule_repo.list_variants(calendar_id=calendar_id)

            self.table.setRowCount(len(variants))

            for row, v in enumerate(variants):
                self.table.setItem(row, 0, QTableWidgetItem(str(v["id_variant"])))
                self.table.setItem(row, 1, QTableWidgetItem(v["name"]))
                self.table.setItem(row, 2, QTableWidgetItem(str(v["objective_score"])))
                self.table.setItem(row, 3, QTableWidgetItem(v["status"]))
                self.table.setItem(row, 4, QTableWidgetItem(v["rule_profile_key"]))

        except Exception as e:
            QMessageBox.critical(self, "Ошибка загрузки вариантов", str(e))

    # ---------------------------------------------------------

    def _approve_selected(self):
        selected = self.table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Нет выбора", "Выберите вариант.")
            return

        variant_id_item = self.table.item(selected, 0)
        if not variant_id_item:
            return

        variant_id = int(variant_id_item.text())

        try:
            cmd = SaveVariantCommand(
                variant_id=variant_id,
                status="approved",
            )
            self.save_variant_uc.execute(cmd)
            QMessageBox.information(self, "Успешно", "Вариант утверждён.")
            self.refresh()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))