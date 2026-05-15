from __future__ import annotations

import json
import sys

from PyQt6.QtCore import QProcess, QProcessEnvironment, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

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


class GeneratePage(QWidget):
    variantOpenRequested = pyqtSignal(int)
    calendarCreated = pyqtSignal(int)

    DEFAULT_VARIANTS_COUNT = 1
    DEFAULT_TIME_LIMIT_SECONDS = 600

    def __init__(self, calendar_repo, schedule_repo, event_builder=None, config=None, rules=None):
        super().__init__()
        self._calendar_repo = calendar_repo
        self._schedule_repo = schedule_repo
        self._event_builder = event_builder
        self._config = config
        self._rules = rules

        self._process: QProcess | None = None
        self._stdout_buffer = ""
        self._current_variant_ids: list[int] = []

        root = QVBoxLayout(self)

        title = QLabel("Генерация расписания")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        subtitle = QLabel(
            "Генерация строит согласованное расписание для выбранного календаря "
            "в отдельном процессе."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #5f6b7a;")
        root.addWidget(subtitle)

        form = QFormLayout()
        root.addLayout(form)

        calendar_row = QHBoxLayout()
        self.calendar_combo = QComboBox()
        calendar_row.addWidget(self.calendar_combo)

        self.add_calendar_btn = QPushButton("+")
        self.add_calendar_btn.setFixedWidth(32)
        self.add_calendar_btn.setToolTip("Добавить семестр")
        calendar_row.addWidget(self.add_calendar_btn)

        calendar_row_widget = QWidget()
        calendar_row_widget.setLayout(calendar_row)

        form.addRow("Календарь:", calendar_row_widget)

        self.use_base_variant_checkbox = QCheckBox(
            "Генерировать на основе черновика"
        )
        form.addRow("", self.use_base_variant_checkbox)

        self.base_variant_combo = QComboBox()
        self.base_variant_combo.setEnabled(False)
        form.addRow("Черновик:", self.base_variant_combo)

        info_label = QLabel(
            "Количество вариантов не задаётся пользователем. "
            "Система формирует один итоговый вариант.\n"
            f"Лимит времени генерации фиксирован: {self.DEFAULT_TIME_LIMIT_SECONDS} сек."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #667085;")
        root.addWidget(info_label)

        buttons = QHBoxLayout()
        root.addLayout(buttons)

        self.generate_btn = QPushButton("Запустить генерацию")
        self.check_feasibility_btn = QPushButton("Проверить реализуемость")
        self.refresh_btn = QPushButton("Обновить список календарей")
        self.open_variant_btn = QPushButton("Открыть выбранный вариант")
        self.open_variant_btn.setEnabled(False)

        buttons.addWidget(self.generate_btn)
        buttons.addWidget(self.check_feasibility_btn)
        buttons.addWidget(self.refresh_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.open_variant_btn)

        self.status_label = QLabel("Выберите календарь и запустите генерацию.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-weight: 500;")
        root.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Готово к запуску")
        self.progress_bar.setTextVisible(True)
        root.addWidget(self.progress_bar)

        variants_title = QLabel("Результат генерации")
        variants_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        root.addWidget(variants_title)

        self.variants_table = QTableWidget(0, 4)
        self.variants_table.setHorizontalHeaderLabels(
            ["ID", "Название", "Score", "Записей"]
        )
        self.variants_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.variants_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.variants_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.variants_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.variants_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.variants_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.variants_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.variants_table, 1)

        log_title = QLabel("Ход генерации")
        log_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        root.addWidget(log_title)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Здесь будет отображаться ход генерации…")
        root.addWidget(self.log_output, 1)

        self.generate_btn.clicked.connect(self._start_generation)
        self.check_feasibility_btn.clicked.connect(self._check_feasibility)
        self.refresh_btn.clicked.connect(self._load_calendars)
        self.open_variant_btn.clicked.connect(self._open_selected_variant)
        self.variants_table.itemSelectionChanged.connect(self._sync_open_button_state)
        self.add_calendar_btn.clicked.connect(self._create_calendar_dialog)
        self.calendar_combo.currentIndexChanged.connect(self._calendar_changed)
        self.use_base_variant_checkbox.toggled.connect(self._on_use_base_variant_toggled)

        self._load_calendars()
        self._load_recent_variants()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._calendar_changed()

    def _select_calendar_by_id(self, calendar_id: int) -> None:
        idx = self.calendar_combo.findData(int(calendar_id))
        if idx >= 0:
            self.calendar_combo.setCurrentIndex(idx)

    def _offer_create_calendar_if_empty(self) -> None:
        answer = QMessageBox.question(
            self,
            "Календари отсутствуют",
            "В базе нет ни одного семестра.\nСоздать новый семестр сейчас?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._create_calendar_dialog()

    def _create_calendar_dialog(self) -> None:
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
        self._select_calendar_by_id(int(calendar_id))
        self._load_recent_variants(calendar_id=int(calendar_id))
        self._set_status("Семестр успешно создан.")
        self.calendarCreated.emit(int(calendar_id))

    def _load_calendars(self) -> None:
        previous_calendar_id = self.calendar_combo.currentData()
        self.calendar_combo.clear()

        try:
            calendars = self._calendar_repo.list_calendars()
        except Exception as exc:
            self._set_status(f"Не удалось загрузить календари: {exc}", error=True)
            return

        for cal in calendars:
            label = (
                f"{getattr(cal, 'academic_year', '')} | "
                f"семестр {getattr(cal, 'semester', '')} "
                f"(id={getattr(cal, 'id_calendar', '')})"
            )
            self.calendar_combo.addItem(label, int(cal.id_calendar))

        if previous_calendar_id is not None:
            idx = self.calendar_combo.findData(int(previous_calendar_id))
            if idx >= 0:
                self.calendar_combo.setCurrentIndex(idx)

        if self.calendar_combo.count() == 0:
            self._set_status("Календари не найдены.", error=True)
            self._offer_create_calendar_if_empty()
        else:
            self._set_status("Календари загружены.")

    def refresh_calendars(self, selected_calendar_id: int | None = None) -> None:
        self._load_calendars()
        if selected_calendar_id is not None:
            self._select_calendar_by_id(int(selected_calendar_id))
        self._calendar_changed()

    def _load_recent_variants(self, calendar_id: int | None = None) -> None:
        try:
            variants = self._schedule_repo.list_variants(calendar_id=calendar_id)
        except Exception as exc:
            self._append_log(f"[error] Не удалось загрузить варианты: {exc}")
            return

        rows = []
        for variant in variants[:50]:
            variant_id = int(getattr(variant, "id_variant", 0) or 0)
            try:
                dto = self._schedule_repo.get_variant_dto(variant_id)
                entries_count = len(getattr(dto, "entries", []) or [])
            except Exception:
                entries_count = 0

            rows.append(
                {
                    "id_variant": variant_id,
                    "name": str(getattr(variant, "name", "") or ""),
                    "objective_score": int(getattr(variant, "objective_score", 0) or 0),
                    "entries_count": entries_count,
                }
            )

        self._fill_variants_table(rows)
        self._fill_base_variant_combo(calendar_id)

    def _fill_base_variant_combo(self, calendar_id: int | None) -> None:
        current = self.base_variant_combo.currentData()
        self.base_variant_combo.blockSignals(True)
        self.base_variant_combo.clear()
        self.base_variant_combo.addItem("Не выбран", None)
        if calendar_id is not None:
            drafts = list(self._schedule_repo.list_generation_drafts(calendar_id=int(calendar_id)) or [])
            for draft in drafts:
                draft_id = int(getattr(draft, "id_draft", 0) or 0)
                name = str(getattr(draft, "name", "") or "")
                self.base_variant_combo.addItem(f"{name} (id={draft_id})", draft_id)

        idx = self.base_variant_combo.findData(current)
        self.base_variant_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.base_variant_combo.blockSignals(False)

    def _calendar_changed(self) -> None:
        calendar_id = self.calendar_combo.currentData()
        selected_calendar_id = int(calendar_id) if calendar_id is not None else None
        self._load_recent_variants(calendar_id=selected_calendar_id)
        self._fill_base_variant_combo(selected_calendar_id)

    def _on_use_base_variant_toggled(self, checked: bool) -> None:
        self.base_variant_combo.setEnabled(bool(checked))

    def _start_generation(self) -> None:
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(
                self,
                "Генерация уже идёт",
                "Дождитесь завершения текущей генерации.",
            )
            return

        calendar_id = self.calendar_combo.currentData()
        if calendar_id is None:
            QMessageBox.warning(self, "Нет календаря", "Сначала выберите календарь.")
            return

        variants_count = self.DEFAULT_VARIANTS_COUNT
        time_limit_seconds = self.DEFAULT_TIME_LIMIT_SECONDS
        use_base_variant = bool(self.use_base_variant_checkbox.isChecked())
        base_variant_id = self.base_variant_combo.currentData() if use_base_variant else None

        if use_base_variant and base_variant_id is None:
            QMessageBox.warning(
                self,
                "Черновик не выбран",
                "Выберите черновик, который нужно использовать как начальное условие.",
            )
            return

        report = self._build_feasibility_report(int(calendar_id))
        if report is None:
            return
        if not self._confirm_generation_with_critical_issues(report):
            return
        self._ensure_placeholder_resources(report)

        self._current_variant_ids = []
        self._fill_variants_table([])
        self._reset_progress_bar(running=True)

        self.log_output.clear()
        self._append_log(
            f"[start] calendar_id={int(calendar_id)}, "
            f"variants_count={variants_count}, "
            f"time_limit_seconds={time_limit_seconds}, "
            f"use_draft_as_locks={use_base_variant}, "
            f"draft_id={int(base_variant_id) if base_variant_id is not None else 'None'}"
        )

        self._set_running_state(True)
        self._set_status("Генерация запущена…")

        self._stdout_buffer = ""
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)

        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        self._process.setProcessEnvironment(env)

        self._process.readyReadStandardOutput.connect(self._on_stdout_ready)
        self._process.readyReadStandardError.connect(self._on_stderr_ready)
        self._process.finished.connect(self._on_process_finished)

        program = sys.executable
        args = [
            "-m",
            "app.presentation.workers.generate_worker",
            str(int(calendar_id)),
            str(int(variants_count)),
            str(int(time_limit_seconds)),
        ]

        if use_base_variant:
            args.extend([
                "--draft-id",
                str(int(base_variant_id)),
                "--use-draft-as-locks",
            ])

        self._process.start(program, args)

        if not self._process.waitForStarted(3000):
            self._set_running_state(False)
            self._set_status("Не удалось запустить worker генерации.", error=True)
            QMessageBox.critical(
                self,
                "Ошибка запуска",
                "Не удалось запустить процесс генерации.",
            )

    def _on_stdout_ready(self) -> None:
        if self._process is None:
            return

        chunk = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not chunk:
            return

        self._stdout_buffer += chunk

        while "\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
            except Exception:
                self._append_log(line)
                continue

            self._handle_worker_message(payload)

    def _on_stderr_ready(self) -> None:
        if self._process is None:
            return

        chunk = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        if not chunk:
            return

        for line in chunk.splitlines():
            line = line.strip()
            if line:
                self._append_log(f"[stderr] {line}")

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._set_running_state(False)

        if self._stdout_buffer.strip():
            for raw in self._stdout_buffer.splitlines():
                line = raw.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    self._handle_worker_message(payload)
                except Exception:
                    self._append_log(line)

        self._stdout_buffer = ""

        if exit_status != QProcess.ExitStatus.NormalExit:
            self._set_status("Процесс генерации завершился аварийно.", error=True)
            return

        if exit_code != 0:
            self._set_status("Генерация завершилась с ошибкой.", error=True)
            return

        self._set_status("Генерация завершена.")
        selected_calendar_id = self.calendar_combo.currentData()
        self._load_recent_variants(
            calendar_id=int(selected_calendar_id) if selected_calendar_id is not None else None
        )

    def _handle_worker_message(self, payload: dict) -> None:
        msg_type = str(payload.get("type", "") or "").strip()

        if msg_type == "started":
            if self.progress_bar.value() < 2:
                self._update_progress_bar("worker_started", {})
            self._append_log(
                "[worker] "
                f"Запущен: calendar_id={payload.get('calendar_id')}, "
                f"variants_count={payload.get('variants_count')}, "
                f"time_limit={payload.get('time_limit_seconds')} сек, "
                f"random_seed={payload.get('random_seed')}"
            )
            return

        if msg_type == "progress":
            stage = str(payload.get("stage", "") or "")
            data = payload.get("data", {}) or {}
            self._append_log(self._format_progress(stage, data))
            if stage == "start" and self.progress_bar.value() >= 70:
                self._set_progress_value(76, "Повторная генерация после автоисправлений")
            self._update_progress_bar(stage, data)
            self._set_status(self._human_stage(stage))
            return

        if msg_type == "done":
            self._set_progress_value(100, "Генерация завершена")
            variants = list(payload.get("variants", []) or [])
            self._current_variant_ids = [
                int(v.get("id_variant", 0) or 0) for v in variants if int(v.get("id_variant", 0) or 0) > 0
            ]
            self._fill_variants_table(variants)

            self._append_log(
                f"[done] Найдено вариантов: {int(payload.get('variants_count', len(variants)) or len(variants))}"
            )
            self._set_status("Генерация завершена.")
            return

        if msg_type == "error":
            message = str(payload.get("message", "") or "Неизвестная ошибка.")
            details = str(payload.get("details", "") or "")
            self._append_log(f"[error] {message}")
            if details:
                self._append_log(details)
            self.progress_bar.setFormat(f"Ошибка: {message}")
            self._set_status(message, error=True)
            return

        self._append_log(json.dumps(payload, ensure_ascii=False))

    def _fill_variants_table(self, variants: list[dict]) -> None:
        self.variants_table.setRowCount(0)

        for row_idx, variant in enumerate(variants):
            self.variants_table.insertRow(row_idx)

            id_variant = int(variant.get("id_variant", 0) or 0)
            name = str(variant.get("name", "") or "")
            score = int(variant.get("objective_score", 0) or 0)
            entries_count = int(variant.get("entries_count", 0) or 0)

            id_item = QTableWidgetItem(str(id_variant))
            id_item.setData(Qt.ItemDataRole.UserRole, id_variant)

            self.variants_table.setItem(row_idx, 0, id_item)
            self.variants_table.setItem(row_idx, 1, QTableWidgetItem(name))
            self.variants_table.setItem(row_idx, 2, QTableWidgetItem(str(score)))
            self.variants_table.setItem(row_idx, 3, QTableWidgetItem(str(entries_count)))

        self._sync_open_button_state()

    def _selected_variant_id(self) -> int | None:
        selected = self.variants_table.selectedItems()
        if not selected:
            return None

        row = selected[0].row()
        item = self.variants_table.item(row, 0)
        if item is None:
            return None

        value = item.data(Qt.ItemDataRole.UserRole)
        if value is None:
            return None

        return int(value)

    def _sync_open_button_state(self) -> None:
        self.open_variant_btn.setEnabled(self._selected_variant_id() is not None)

    def _open_selected_variant(self) -> None:
        variant_id = self._selected_variant_id()
        if variant_id is None:
            QMessageBox.information(
                self,
                "Вариант не выбран",
                "Сначала выберите вариант в таблице.",
            )
            return

        QMessageBox.information(
            self,
            "Открытие расписания",
            f"Открывается вариант расписания id={int(variant_id)}.",
        )
        self.variantOpenRequested.emit(int(variant_id))

    def _set_running_state(self, running: bool) -> None:
        self.generate_btn.setEnabled(not running)
        self.refresh_btn.setEnabled(not running)
        self.calendar_combo.setEnabled(not running)
        self.add_calendar_btn.setEnabled(not running)
        if not running and self.progress_bar.value() == 0:
            self.progress_bar.setFormat("Готово к запуску")

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(text)
        if error:
            self.status_label.setStyleSheet("font-weight: 600; color: #b42318;")
        else:
            self.status_label.setStyleSheet("font-weight: 500; color: #101828;")

    def _append_log(self, text: str) -> None:
        self.log_output.appendPlainText(text)

    def _reset_progress_bar(self, *, running: bool) -> None:
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Генерация запущена…" if running else "Готово к запуску")

    def _set_progress_value(self, value: int, text: str) -> None:
        clamped = max(0, min(100, int(value)))
        self.progress_bar.setValue(clamped)
        self.progress_bar.setFormat(text)

    def _update_progress_bar(self, stage: str, data: dict) -> None:
        current = int(self.progress_bar.value())
        stage_progress = {
            "worker_started": (2, "Процесс генерации запущен"),
            "start": (5, "Подготовка генерации"),
            "calendar_loaded": (10, "Календарь загружен"),
            "semester_plans_loaded": (16, "Загружен semester plan"),
            "weekly_plans_loaded": (20, "Загружен weekly plan"),
            "weekly_plans_missing": (20, "Используется fallback semester plan"),
            "reference_data_loaded": (28, "Загружены справочники"),
            "curriculum_map_loaded": (34, "Загружены элементы учебного плана"),
            "rules_loaded": (40, "Загружены правила"),
            "availability_loaded": (46, "Загружена доступность преподавателей"),
            "auto_placeholder_availability_repaired": (50, "Исправлена доступность автозаглушек"),
            "building_events": (56, "Формирование событий генерации"),
            "events_built": (64, "События генерации построены"),
            "pre_solver_diagnostics": (72, "Выполнена преддиагностика"),
            "auto_capacity_placeholders_added": (76, "Добавлены преподаватели по дефициту ресурса"),
            "auto_placeholders_added": (78, "Добавлены адресные заглушки"),
            "solver_started": (84, "Solver запущен"),
            "solver_infeasible_diagnostics": (90, "Собрана диагностика несовместимости"),
            "solver_finished": (94, "Solver завершил поиск"),
            "saving_variant": (97, "Сохранение варианта"),
            "variant_saved": (99, "Вариант сохранён"),
        }
        value, text = stage_progress.get(stage, (current, self._human_stage(stage)))
        self._set_progress_value(max(current, int(value)), text)

    def _human_stage(self, stage: str) -> str:
        mapping = {
            "start": "Подготовка генерации…",
            "calendar_loaded": "Календарь загружен.",
            "semester_plans_loaded": "Загружен semester plan.",
            "weekly_plans_loaded": "Загружен weekly plan.",
            "weekly_plans_missing": "Weekly plan не найден, используется semester plan.",
            "reference_data_loaded": "Загружены справочники.",
            "curriculum_map_loaded": "Загружены элементы учебного плана.",
            "rules_loaded": "Загружены правила генерации.",
            "availability_loaded": "Загружена доступность преподавателей.",
            "building_events": "Формирование событий генерации…",
            "events_built": "События генерации построены.",
            "auto_placeholders_added": "Добавлены заглушки для проблемных событий, повтор генерации…",
            "solver_started": "Solver запущен…",
            "solver_finished": "Solver завершил поиск.",
            "saving_variant": "Сохранение варианта…",
            "variant_saved": "Вариант сохранён.",
            "done": "Генерация завершена.",
        }
        return mapping.get(stage, stage or "Обработка…")

    def _format_progress(self, stage: str, data: dict) -> str:
        if not data:
            return f"[progress] {stage}"

        compact = ", ".join(f"{k}={v}" for k, v in data.items())
        return f"[progress] {stage}: {compact}"

    def _check_feasibility(self) -> None:
        """
        Проверка реализуемости расписания перед генерацией.
        """
        calendar_id = self.calendar_combo.currentData()
        if calendar_id is None:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Сначала выберите календарь.",
            )
            return

        try:
            self._set_status("Проверка реализуемости...", error=False)
            report = self._build_feasibility_report(int(calendar_id))
            if report is None:
                return

            # Формируем отчет
            message_parts = []

            if report.is_feasible:
                message_parts.append("✓ Расписание может быть сгенерировано.\n")
            else:
                message_parts.append("✗ Расписание НЕ может быть сгенерировано.\n")

            if report.critical_issues:
                message_parts.append(f"\nКритические проблемы ({len(report.critical_issues)}):")
                for issue in report.critical_issues[:10]:  # Показываем первые 10
                    message_parts.append(f"  • {issue.message}")
                if len(report.critical_issues) > 10:
                    message_parts.append(f"  ... и ещё {len(report.critical_issues) - 10}")

            if report.warnings:
                message_parts.append(f"\nПредупреждения ({len(report.warnings)}):")
                for issue in report.warnings[:10]:  # Показываем первые 10
                    message_parts.append(f"  • {issue.message}")
                if len(report.warnings) > 10:
                    message_parts.append(f"  ... и ещё {len(report.warnings) - 10}")

            if report.recommendations:
                message_parts.append("\nРекомендации:")
                for rec in report.recommendations:
                    message_parts.append(f"  • {rec}")

            if report.metrics:
                message_parts.append("\nМетрики:")
                for key, value in report.metrics.items():
                    if isinstance(value, float):
                        message_parts.append(f"  • {key}: {value:.2f}")
                    else:
                        message_parts.append(f"  • {key}: {value}")

            message = "\n".join(message_parts)

            # Показываем результат
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Проверка реализуемости")
            msg_box.setText(message)
            if report.is_feasible:
                msg_box.setIcon(QMessageBox.Icon.Information)
            else:
                msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.exec()

            self._set_status("Проверка реализуемости завершена.", error=False)

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось выполнить проверку реализуемости:\n{exc}",
            )
            self._set_status(f"Ошибка проверки: {exc}", error=True)

    def _build_feasibility_report(self, calendar_id: int):
        from app.application.use_cases.validate_feasibility import ValidateFeasibilityUseCase
        from app.infrastructure.db.repositories import (
            SqliteCalendarRepository,
            SqliteCurriculumRepository,
            SqliteGroupsRepository,
            SqliteSubjectsRepository,
            SqliteTeachersRepository,
            SqliteRoomsRepository,
        )

        session_factory = self._schedule_repo._session_factory
        calendar_repo = SqliteCalendarRepository(session_factory)
        curriculum_repo = SqliteCurriculumRepository(session_factory)
        groups_repo = SqliteGroupsRepository(session_factory)
        subjects_repo = SqliteSubjectsRepository(session_factory)
        teachers_repo = SqliteTeachersRepository(session_factory)
        rooms_repo = SqliteRoomsRepository(session_factory)

        use_case = ValidateFeasibilityUseCase(
            calendar_repo=calendar_repo,
            curriculum_repo=curriculum_repo,
            groups_repo=groups_repo,
            subjects_repo=subjects_repo,
            teachers_repo=teachers_repo,
            rooms_repo=rooms_repo,
            event_builder=self._event_builder,
            config=self._config,
            rules=self._rules,
        )
        return use_case.execute(int(calendar_id))

    def _confirm_generation_with_critical_issues(self, report) -> bool:
        critical_categories = {"teacher_coverage", "teacher_deficit", "room_coverage", "room_deficit", "bottleneck"}
        relevant_issues = [
            issue for issue in list(getattr(report, "critical_issues", []) or [])
            if str(getattr(issue, "category", "") or "") in critical_categories
        ]
        if not relevant_issues:
            return True

        lines = [
            "Обнаружены критические проблемы с обеспечением преподавателями или аудиториями.",
            "Если вы запустите генерацию сейчас, некоторые данные останутся пустыми.",
            "Хотите продолжить?",
            "",
            f"Критических проблем: {len(relevant_issues)}",
        ]
        for issue in relevant_issues[:8]:
            lines.append(f"• {issue.message}")
        if len(relevant_issues) > 8:
            lines.append(f"• ... и ещё {len(relevant_issues) - 8}")

        answer = QMessageBox.question(
            self,
            "Критические проблемы генерации",
            "\n".join(lines),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _ensure_placeholder_resources(self, report) -> None:
        teacher_created = self._ensure_placeholder_teachers(report)
        room_created = self._ensure_placeholder_rooms(report)
        if teacher_created or room_created:
            self._append_log(
                f"[info] Добавлены недостающие данные: преподавателей={teacher_created}, аудиторий={room_created}"
            )

    def _ensure_placeholder_teachers(self, report) -> int:
        created_count = 0
        teacher_issues = [
            issue for issue in list(getattr(report, "critical_issues", []) or [])
            if str(getattr(issue, "category", "") or "") == "teacher_coverage"
        ]
        if not teacher_issues:
            return 0

        for issue in teacher_issues:
            details = getattr(issue, "details", {}) or {}
            subject_id = int(details.get("subject_id", 0) or 0)
            subject_name = str(details.get("subject_name", "") or f"ID={subject_id}")
            part_type = str(details.get("part_type", "") or "practice")
            if subject_id <= 0:
                continue

            base_name = f"Преподаватель {subject_name}"
            full_name = self._unique_teacher_name(base_name)
            teacher_id = self._create_placeholder_teacher(full_name, subject_id, part_type)
            if teacher_id > 0:
                created_count += 1
        return created_count

    def _ensure_placeholder_rooms(self, report) -> int:
        room_types = []
        for issue in list(getattr(report, "critical_issues", []) or []):
            category = str(getattr(issue, "category", "") or "")
            if category not in {"room_coverage", "room_deficit"}:
                continue
            details = getattr(issue, "details", {}) or {}
            room_type = str(details.get("room_type", "") or "").strip().lower()
            if room_type:
                room_types.append(room_type)

        created_count = 0
        for room_type in sorted(set(room_types)):
            if self._room_type_exists(room_type):
                continue
            room_number = self._unique_room_number(f"Аудитория для {room_type}")
            self._rooms_repo_create_placeholder(room_number, room_type)
            created_count += 1
        return created_count

    def _unique_teacher_name(self, base_name: str) -> str:
        from app.infrastructure.db.repositories import SqliteTeachersRepository

        repo = SqliteTeachersRepository(self._schedule_repo._session_factory)
        idx = 1
        while True:
            candidate = f"{base_name}{idx}"
            if repo.get_by_full_name(candidate) is None:
                return candidate
            idx += 1

    def _create_placeholder_teacher(self, full_name: str, subject_id: int, part_type: str) -> int:
        from app.infrastructure.db.repositories import SqliteTeachersRepository

        repo = SqliteTeachersRepository(self._schedule_repo._session_factory)
        teacher_id = repo.create(
            full_name=full_name,
            hard_max=6,
            soft_max=4,
            needs_method_day=False,
            commentary="Автоматически добавлен при генерации из-за нехватки преподавателей.",
        )
        repo.replace_teacher_subject_rules(
            int(teacher_id),
            [
                {
                    "subject_id": int(subject_id),
                    "can_lecture": part_type == "lecture",
                    "can_practice": part_type == "practice",
                    "can_computer_practice": part_type == "computer_practice",
                    "can_lab": part_type == "lab",
                }
            ],
        )
        return int(teacher_id)

    def _room_type_exists(self, room_type: str) -> bool:
        from app.infrastructure.db.repositories import SqliteRoomsRepository

        repo = SqliteRoomsRepository(self._schedule_repo._session_factory)
        for room in repo.list_all():
            room_types = getattr(room, "room_types", None) or (getattr(room, "room_type", ""),)
            if str(room_type).lower() in {str(x).lower() for x in room_types if str(x).strip()}:
                return True
        return False

    def _unique_room_number(self, base_name: str) -> str:
        from app.infrastructure.db.repositories import SqliteRoomsRepository

        repo = SqliteRoomsRepository(self._schedule_repo._session_factory)
        existing = {str(getattr(room, "room_number", "") or "") for room in repo.list_all()}
        idx = 1
        while True:
            candidate = f"{base_name} {idx}"
            if candidate not in existing:
                return candidate
            idx += 1

    def _rooms_repo_create_placeholder(self, room_number: str, room_type: str) -> None:
        from app.infrastructure.db.repositories import SqliteRoomsRepository

        repo = SqliteRoomsRepository(self._schedule_repo._session_factory)
        repo.create(
            room_number=room_number,
            room_type=room_type,
            room_types=[room_type],
            capacity=35,
            building="Автозаглушка",
        )
