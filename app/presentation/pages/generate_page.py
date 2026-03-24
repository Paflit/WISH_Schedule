from __future__ import annotations

import json
import sys

from PyQt6.QtCore import QProcess, Qt
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from app.presentation.widgets.metrics_panel import MetricsPanel


class CreateCalendarDialog(QDialog):
    """
    Диалог создания нового семестра / календаря.
    """

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
    """
    Страница генерации расписания.

    Актуальная логика:
    - пользователь выбирает календарь;
    - лимит времени не меняется из UI;
    - генерация запускается в отдельном worker-процессе;
    - количество вариантов пользователь не задаёт;
    - UI получает progress/done/error из stdout worker.

    Сейчас страница запускает генерацию одного итогового варианта
    с фиксированным лимитом времени 600 секунд.
    """

    DEFAULT_VARIANTS_COUNT = 1
    DEFAULT_TIME_LIMIT_SECONDS = 600

    def __init__(self, calendar_repo, schedule_repo):
        super().__init__()
        self._calendar_repo = calendar_repo
        self._schedule_repo = schedule_repo

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
        self.refresh_btn = QPushButton("Обновить список календарей")
        self.open_variant_btn = QPushButton("Открыть выбранный вариант")
        self.open_variant_btn.setEnabled(False)

        buttons.addWidget(self.generate_btn)
        buttons.addWidget(self.refresh_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.open_variant_btn)

        self.status_label = QLabel("Выберите календарь и запустите генерацию.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-weight: 500;")
        root.addWidget(self.status_label)

        self.metrics_panel = MetricsPanel()
        root.addWidget(self.metrics_panel)

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
        self.refresh_btn.clicked.connect(self._load_calendars)
        self.open_variant_btn.clicked.connect(self._open_selected_variant)
        self.variants_table.itemSelectionChanged.connect(self._sync_open_button_state)
        self.add_calendar_btn.clicked.connect(self._create_calendar_dialog)

        self._load_calendars()
        self._load_recent_variants()

    # ---------------------------------------------------------
    # Calendar helpers
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Load data
    # ---------------------------------------------------------
    def _load_calendars(self) -> None:
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

        if self.calendar_combo.count() == 0:
            self._set_status("Календари не найдены.", error=True)
            self._offer_create_calendar_if_empty()
        else:
            self._set_status("Календари загружены.")

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

    # ---------------------------------------------------------
    # Worker lifecycle
    # ---------------------------------------------------------
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

        self._current_variant_ids = []
        self._fill_variants_table([])
        self.metrics_panel.set_metrics({})

        self.log_output.clear()
        self._append_log(
            f"[start] calendar_id={int(calendar_id)}, "
            f"variants_count={variants_count}, "
            f"time_limit_seconds={time_limit_seconds}"
        )

        self._set_running_state(True)
        self._set_status("Генерация запущена…")

        self._stdout_buffer = ""
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)

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

    # ---------------------------------------------------------
    # Worker message handling
    # ---------------------------------------------------------
    def _handle_worker_message(self, payload: dict) -> None:
        msg_type = str(payload.get("type", "") or "").strip()

        if msg_type == "started":
            self._append_log(
                "[worker] "
                f"Запущен: calendar_id={payload.get('calendar_id')}, "
                f"variants_count={payload.get('variants_count')}, "
                f"time_limit={payload.get('time_limit_seconds')} сек"
            )
            return

        if msg_type == "progress":
            stage = str(payload.get("stage", "") or "")
            data = payload.get("data", {}) or {}
            self._append_log(self._format_progress(stage, data))
            self._set_status(self._human_stage(stage))
            return

        if msg_type == "done":
            variants = list(payload.get("variants", []) or [])
            self._current_variant_ids = [
                int(v.get("id_variant", 0) or 0) for v in variants if int(v.get("id_variant", 0) or 0) > 0
            ]
            self._fill_variants_table(variants)

            if variants:
                best = min(
                    variants,
                    key=lambda x: int(x.get("objective_score", 0) or 0),
                )
                self.metrics_panel.set_metrics(
                    {
                        "variants_count": int(payload.get("variants_count", len(variants)) or len(variants)),
                        "best_variant_id": int(best.get("id_variant", 0) or 0),
                        "best_objective_score": int(best.get("objective_score", 0) or 0),
                        "best_entries_count": int(best.get("entries_count", 0) or 0),
                    }
                )
            else:
                self.metrics_panel.set_metrics(
                    {"variants_count": int(payload.get("variants_count", 0) or 0)}
                )

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
            self._set_status(message, error=True)
            return

        self._append_log(json.dumps(payload, ensure_ascii=False))

    # ---------------------------------------------------------
    # Table / selection
    # ---------------------------------------------------------
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
            "Вариант выбран",
            f"Выбран вариант расписания id={int(variant_id)}.\n"
            f"Дальнейшее открытие можно связать с экраном вариантов или редактором.",
        )

    # ---------------------------------------------------------
    # UI helpers
    # ---------------------------------------------------------
    def _set_running_state(self, running: bool) -> None:
        self.generate_btn.setEnabled(not running)
        self.refresh_btn.setEnabled(not running)
        self.calendar_combo.setEnabled(not running)
        self.add_calendar_btn.setEnabled(not running)

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(text)
        if error:
            self.status_label.setStyleSheet("font-weight: 600; color: #b42318;")
        else:
            self.status_label.setStyleSheet("font-weight: 500; color: #101828;")

    def _append_log(self, text: str) -> None:
        self.log_output.appendPlainText(text)

    def _human_stage(self, stage: str) -> str:
        mapping = {
            "start": "Подготовка генерации…",
            "calendar_loaded": "Календарь загружен.",
            "semester_plans_loaded": "Загружен semester plan.",
            "weekly_plans_loaded": "Загружен weekly plan.",
            "reference_data_loaded": "Загружены справочники.",
            "curriculum_map_loaded": "Загружены элементы учебного плана.",
            "rules_loaded": "Загружены правила генерации.",
            "availability_loaded": "Загружена доступность преподавателей.",
            "building_events": "Формирование событий генерации…",
            "events_built": "События генерации построены.",
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