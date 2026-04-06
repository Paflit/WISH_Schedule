from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QListWidget,
    QListWidgetItem,
)

from app.application.dto.schedule_dto import ScheduleVariantDTO
from app.presentation.widgets.metrics_panel import MetricsPanel


DAY_NAMES = {
    1: "Пн",
    2: "Вт",
    3: "Ср",
    4: "Чт",
    5: "Пт",
    6: "Сб",
    7: "Вс",
}

PART_TYPE_LABELS = {
    "lecture": "Лекция",
    "practice": "Практика",
    "computer_practice": "Комп. практика",
    "lab": "Лабораторная",
}


class CreateCalendarDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавление семестра")
        self.resize(420, 220)

        root = QVBoxLayout(self)

        form = QFormLayout()
        root.addLayout(form)

        self.academic_year_combo = QComboBox()
        self.academic_year_combo.setEditable(True)
        self.academic_year_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.academic_year_combo.addItems(
            [
                "2025/2026",
                "2026/2027",
                "2027/2028",
            ]
        )
        form.addRow("Учебный год:", self.academic_year_combo)

        self.semester_combo = QComboBox()
        self.semester_combo.addItem("1 семестр", 1)
        self.semester_combo.addItem("2 семестр", 2)
        form.addRow("Семестр:", self.semester_combo)

        self.include_saturday = QCheckBox("Включить субботу")
        form.addRow("", self.include_saturday)

        self.pairs_per_day_spin = QSpinBox()
        self.pairs_per_day_spin.setRange(1, 12)
        self.pairs_per_day_spin.setValue(8)
        form.addRow("Пар в день:", self.pairs_per_day_spin)

        self.weeks_in_semester_spin = QSpinBox()
        self.weeks_in_semester_spin.setRange(1, 30)
        self.weeks_in_semester_spin.setValue(18)
        form.addRow("Недель в семестре:", self.weeks_in_semester_spin)

        hint = QLabel(
            "Новый семестр будет создан только если в базе ещё нет "
            "такой комбинации учебного года и номера семестра."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #667085;")
        root.addWidget(hint)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        root.addWidget(self.button_box)

    def get_data(self) -> dict:
        return {
            "academic_year": self.academic_year_combo.currentText().strip(),
            "semester": int(self.semester_combo.currentData()),
            "include_saturday": bool(self.include_saturday.isChecked()),
            "pairs_per_day": int(self.pairs_per_day_spin.value()),
            "weeks_in_semester": int(self.weeks_in_semester_spin.value()),
        }


class VariantsPage(QWidget):

    variantOpenRequested = pyqtSignal(int)

    def __init__(self, schedule_repo, calendar_repo=None):
        super().__init__()
        self._schedule_repo = schedule_repo
        self._calendar_repo = calendar_repo

        self._current_calendar_id: Optional[int] = None
        self._current_variant_id: Optional[int] = None
        self._current_variant_dto: Optional[ScheduleVariantDTO] = None

        root = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        root.addLayout(toolbar)

        toolbar.addWidget(QLabel("Календарь:"))

        self.calendar_combo = QComboBox()
        toolbar.addWidget(self.calendar_combo)

        self.add_calendar_btn = QPushButton("+")
        self.add_calendar_btn.setFixedWidth(32)
        self.add_calendar_btn.setToolTip("Добавить семестр")
        toolbar.addWidget(self.add_calendar_btn)

        toolbar.addStretch(1)

        self.refresh_btn = QPushButton("Обновить")
        self.open_btn = QPushButton("Открыть вариант")
        self.open_btn.setEnabled(False)

        toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.open_btn)

        splitter = QSplitter()
        root.addWidget(splitter, 1)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        left_layout.addWidget(QLabel("Доступные варианты"))

        self.variants_table = QTableWidget(0, 5)
        self.variants_table.setHorizontalHeaderLabels(
            ["ID", "Название", "Score", "Статус", "Создан"]
        )
        self.variants_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.variants_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.variants_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.variants_table.verticalHeader().setVisible(False)
        self.variants_table.setAlternatingRowColors(True)
        self.variants_table.horizontalHeader().setStretchLastSection(True)
        self.variants_table.setColumnWidth(0, 70)
        self.variants_table.setColumnWidth(1, 260)
        self.variants_table.setColumnWidth(2, 90)
        self.variants_table.setColumnWidth(3, 110)
        left_layout.addWidget(self.variants_table, 1)

        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.title_label = QLabel("Вариант не выбран.")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        right_layout.addWidget(self.title_label)

        self.metrics_panel = MetricsPanel()
        right_layout.addWidget(self.metrics_panel)

        right_layout.addWidget(QLabel("Краткая сводка записей варианта"))

        self.summary_list = QListWidget()
        right_layout.addWidget(self.summary_list, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.refresh_btn.clicked.connect(self.refresh)
        self.open_btn.clicked.connect(self._open_current_variant)
        self.calendar_combo.currentIndexChanged.connect(self._calendar_changed)
        self.variants_table.itemSelectionChanged.connect(self._variant_selection_changed)
        self.add_calendar_btn.clicked.connect(self._create_calendar_dialog)

        self._load_calendars()
        self.refresh()

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            "color: #b42318;" if error else "color: #344054;"
        )

    def _load_calendars(self) -> None:
        self.calendar_combo.blockSignals(True)
        self.calendar_combo.clear()
        self.calendar_combo.addItem("Все календари", None)

        if self._calendar_repo is None:
            self.calendar_combo.blockSignals(False)
            return

        try:
            calendars = self._calendar_repo.list_calendars()
        except Exception as exc:
            self._set_status(f"Не удалось загрузить календари: {exc}", error=True)
            self.calendar_combo.blockSignals(False)
            return

        for cal in calendars:
            label = (
                f"{getattr(cal, 'academic_year', '')} | "
                f"семестр {getattr(cal, 'semester', '')} "
                f"(id={getattr(cal, 'id_calendar', '')})"
            )
            self.calendar_combo.addItem(label, int(cal.id_calendar))

        self.calendar_combo.blockSignals(False)

        if self.calendar_combo.count() <= 1 and self._calendar_repo is not None:
            self._offer_create_calendar_if_empty()

    def _offer_create_calendar_if_empty(self) -> None:
        answer = QMessageBox.question(
            self,
            "Календари отсутствуют",
            "В базе нет ни одного семестра.\nСоздать новый семестр сейчас?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._create_calendar_dialog()

    def _create_calendar_dialog(self) -> None:
        if self._calendar_repo is None:
            QMessageBox.warning(self, "Ошибка", "Репозиторий календарей недоступен.")
            return

        dlg = CreateCalendarDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()

        if not data["academic_year"]:
            QMessageBox.warning(self, "Ошибка", "Учебный год не может быть пустым.")
            return

        try:
            calendar_id = self._calendar_repo.create_calendar(
                academic_year=str(data["academic_year"]),
                semester=int(data["semester"]),
                include_saturday=bool(data["include_saturday"]),
                pairs_per_day=int(data["pairs_per_day"]),
                weeks_in_semester=int(data["weeks_in_semester"]),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось создать семестр:\n{exc}",
            )
            return

        self._load_calendars()
        idx = self.calendar_combo.findData(int(calendar_id))
        if idx >= 0:
            self.calendar_combo.setCurrentIndex(idx)
            self._current_calendar_id = int(calendar_id)

        self.refresh()
        self._set_status("Семестр успешно создан.")

    def _calendar_changed(self) -> None:
        value = self.calendar_combo.currentData()
        self._current_calendar_id = int(value) if value is not None else None
        self.refresh()

    def _selected_variant_id(self) -> Optional[int]:
        row = self.variants_table.currentRow()
        if row < 0:
            return None
        item = self.variants_table.item(row, 0)
        if item is None:
            return None
        try:
            return int(item.data(Qt.ItemDataRole.UserRole))
        except (TypeError, ValueError):
            return None

    def refresh(self) -> None:
        self._current_variant_id = None
        self._current_variant_dto = None
        self.open_btn.setEnabled(False)
        self.title_label.setText("Вариант не выбран.")
        self.summary_list.clear()
        self.metrics_panel.set_metrics({})

        try:
            variants = self._schedule_repo.list_variants(calendar_id=self._current_calendar_id)
        except Exception as exc:
            self.variants_table.setRowCount(0)
            self._set_status(f"Не удалось загрузить варианты: {exc}", error=True)
            return

        self.variants_table.setRowCount(0)

        for row_idx, variant in enumerate(variants):
            self.variants_table.insertRow(row_idx)

            variant_id = int(getattr(variant, "id_variant", 0) or 0)
            name = str(getattr(variant, "name", "") or "")
            objective_score = int(getattr(variant, "objective_score", 0) or 0)
            status = str(getattr(variant, "status", "") or "")
            created_at = str(getattr(variant, "created_at", "") or "")

            id_item = QTableWidgetItem(str(variant_id))
            id_item.setData(Qt.ItemDataRole.UserRole, variant_id)

            self.variants_table.setItem(row_idx, 0, id_item)
            self.variants_table.setItem(row_idx, 1, QTableWidgetItem(name))
            self.variants_table.setItem(row_idx, 2, QTableWidgetItem(str(objective_score)))
            self.variants_table.setItem(row_idx, 3, QTableWidgetItem(status or "—"))
            self.variants_table.setItem(row_idx, 4, QTableWidgetItem(created_at or "—"))

        self._set_status(f"Загружено вариантов: {len(variants)}")

        if self.variants_table.rowCount() > 0:
            self.variants_table.selectRow(0)
            self._variant_selection_changed()

    def _variant_selection_changed(self) -> None:
        variant_id = self._selected_variant_id()
        if variant_id is None:
            self._current_variant_id = None
            self._current_variant_dto = None
            self.open_btn.setEnabled(False)
            self.title_label.setText("Вариант не выбран.")
            self.summary_list.clear()
            self.metrics_panel.set_metrics({})
            return

        try:
            dto = self._schedule_repo.get_variant_dto(int(variant_id))
        except Exception as exc:
            self._set_status(f"Не удалось загрузить вариант id={variant_id}: {exc}", error=True)
            self.open_btn.setEnabled(False)
            return

        self._current_variant_id = int(variant_id)
        self._current_variant_dto = dto
        self.open_btn.setEnabled(True)

        self._fill_variant_details(dto)

    def _fill_variant_details(self, dto: ScheduleVariantDTO) -> None:
        self.title_label.setText(
            f"{dto.name}<br><span style='font-size:12px; color:#667085;'>"
            f"id={int(dto.id_variant)}, записей: {len(dto.entries)}</span>"
        )

        metrics = self._build_metrics(dto)
        self.metrics_panel.set_metrics(metrics)

        self.summary_list.clear()
        summary_rows = self._build_summary_rows(dto)
        for text in summary_rows:
            self.summary_list.addItem(QListWidgetItem(text))

        self._set_status(
            f"Выбран вариант '{dto.name}', записей: {len(dto.entries)}, "
            f"score: {int(dto.objective_score)}"
        )

    def _build_metrics(self, dto: ScheduleVariantDTO) -> dict:
        entries = list(dto.entries or [])

        unique_groups = len({int(e.group_id) for e in entries if int(e.group_id) > 0})
        unique_teachers = len({int(e.teacher_id) for e in entries if int(e.teacher_id) > 0})
        unique_rooms = len({int(e.room_id) for e in entries if int(e.room_id) > 0})
        locked_entries = len([e for e in entries if bool(e.is_locked)])

        return {
            "id_variant": int(dto.id_variant),
            "objective_score": int(dto.objective_score),
            "entries_count": len(entries),
            "groups_count": unique_groups,
            "teachers_count": unique_teachers,
            "rooms_count": unique_rooms,
            "locked_entries": locked_entries,
        }

    def _build_summary_rows(self, dto: ScheduleVariantDTO) -> list[str]:
        entries = sorted(
            list(dto.entries or []),
            key=lambda e: (
                int(e.week_number),
                int(e.week_type),
                int(e.day_of_week),
                int(e.pair_number),
                str(e.group_name),
                str(e.subject_name),
            ),
        )

        rows: list[str] = []
        for entry in entries[:200]:
            day_name = DAY_NAMES.get(int(entry.day_of_week), str(entry.day_of_week))
            part_label = PART_TYPE_LABELS.get(entry.part_type, entry.part_type or "—")

            week_part = ""
            if int(entry.week_number) > 0:
                week_part = f"Неделя {int(entry.week_number)}"
            elif int(entry.week_type) > 0:
                week_part = "Числитель" if int(entry.week_type) == 1 else "Знаменатель"

            line = (
                f"{week_part + ' | ' if week_part else ''}"
                f"{day_name}, {int(entry.pair_number)} пара — "
                f"{entry.group_name} | {entry.subject_name} ({part_label}) | "
                f"{entry.teacher_name} | {entry.room_number}"
            )
            if bool(entry.is_locked):
                line += " | 🔒"
            rows.append(line)

        if len(entries) > 200:
            rows.append(f"... ещё записей: {len(entries) - 200}")

        if not rows:
            rows.append("В этом варианте пока нет записей.")

        return rows

    def _open_current_variant(self) -> None:
        if self._current_variant_id is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите вариант.")
            return
        self.variantOpenRequested.emit(int(self._current_variant_id))