from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QMessageBox,
    QDialog,
    QFormLayout,
    QLineEdit,
    QDialogButtonBox,
)

from app.application.use_cases.save_variant import SaveVariantCommand


class ApproveGeneratedDialog(QDialog):
    def __init__(self, current_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Утверждение варианта")
        self.setMinimumWidth(420)

        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.name_edit.setText(current_name)
        layout.addRow("Новое название:", self.name_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return self.name_edit.text().strip()


class GeneratePage(QWidget):
    DEFAULT_TIME_LIMIT_SECONDS = 120
    DEFAULT_VARIANTS_COUNT = 1

    def __init__(self, container, open_variant_callback=None):
        super().__init__()
        self.container = container
        self.open_variant_callback = open_variant_callback

        self.calendar_repo = container.calendar_repo
        self.curriculum_repo = container.curriculum_repo
        self.save_variant_uc = container.save_variant_uc
        self.schedule_repo = container.schedule_repo

        self._process: Optional[QProcess] = None
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._last_result_payload: Optional[dict] = None
        self._last_error_payload: Optional[dict] = None

        self._generated_variant: Optional[dict] = None

        self._init_ui()
        self._load_calendars()
        self._on_calendar_changed()

    def _init_ui(self):
        layout = QVBoxLayout()

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Полугодие:"))
        self.calendar_combo = QComboBox()
        row1.addWidget(self.calendar_combo)
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.generate_button = QPushButton("Сгенерировать расписание")
        self.cancel_button = QPushButton("Отменить генерацию")
        self.cancel_button.setEnabled(False)

        row2.addWidget(self.generate_button)
        row2.addWidget(self.cancel_button)
        row2.addStretch()
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Сгенерированный вариант:"))
        self.generated_variant_combo = QComboBox()
        self.generated_variant_combo.setEnabled(False)

        self.preview_button = QPushButton("Предпросмотр")
        self.preview_button.setEnabled(False)

        self.open_button = QPushButton("Открыть в просмотре")
        self.open_button.setEnabled(False)

        self.approve_button = QPushButton("Утвердить и переименовать")
        self.approve_button.setEnabled(False)

        row3.addWidget(self.generated_variant_combo)
        row3.addWidget(self.preview_button)
        row3.addWidget(self.open_button)
        row3.addWidget(self.approve_button)
        row3.addStretch()
        layout.addLayout(row3)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.result_label = QLabel("Выберите полугодие и запустите генерацию.")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        self.setLayout(layout)

        self.generate_button.clicked.connect(self._on_generate)
        self.cancel_button.clicked.connect(self._on_cancel)
        self.calendar_combo.currentIndexChanged.connect(self._on_calendar_changed)
        self.generated_variant_combo.currentIndexChanged.connect(self._on_generated_selected)
        self.preview_button.clicked.connect(self._preview_selected_variant)
        self.open_button.clicked.connect(self._open_selected_variant)
        self.approve_button.clicked.connect(self._approve_selected_variant)

    def _get_calendar_plan_stats(self, calendar_id: int) -> tuple[int, int]:
        try:
            plans = self.curriculum_repo.get_semester_plans(int(calendar_id))
        except Exception:
            return 0, 0

        valid = [p for p in plans if int(getattr(p, "hours_in_semester", 0) or 0) > 0]
        total_hours = sum(int(getattr(p, "hours_in_semester", 0) or 0) for p in valid)
        return len(valid), total_hours

    def _load_calendars(self):
        self.calendar_combo.clear()
        calendars = self.calendar_repo.list_all()
        calendars = sorted(
            calendars,
            key=lambda x: (
                str(getattr(x, "academic_year", "")),
                int(getattr(x, "semester", 0)),
                int(getattr(x, "id_calendar", 0)),
            )
        )
        for c in calendars:
            self.calendar_combo.addItem(
                f"{c.academic_year} / Полугодие {c.semester}",
                userData=int(c.id_calendar),
            )

    def _on_calendar_changed(self):
        calendar_id = self.calendar_combo.currentData()
        if not calendar_id:
            self.info_label.setText("Полугодие не выбрано.")
            return

        plans_count, total_hours = self._get_calendar_plan_stats(int(calendar_id))
        self.info_label.setText(
            f"Для выбранного полугодия найдено дисциплин/частей плана с часами: {plans_count}. "
            f"Суммарные часы: {total_hours}."
        )

    def _set_busy(self, busy: bool):
        self.generate_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.calendar_combo.setEnabled(not busy)

    def _reload_generated_combo(self):
        self.generated_variant_combo.blockSignals(True)
        self.generated_variant_combo.clear()

        if self._generated_variant is not None:
            self.generated_variant_combo.addItem(
                f"{self._generated_variant['name']}",
                userData=int(self._generated_variant["variant_id"]),
            )

        self.generated_variant_combo.blockSignals(False)

        has_item = self.generated_variant_combo.count() > 0
        self.generated_variant_combo.setEnabled(has_item)
        self.preview_button.setEnabled(has_item)
        self.open_button.setEnabled(has_item)
        self.approve_button.setEnabled(has_item)

        if has_item:
            self.generated_variant_combo.setCurrentIndex(0)
            self._on_generated_selected()

    def _on_generated_selected(self):
        if self._generated_variant is None:
            return

        self.result_label.setText(
            f"Вариант: {self._generated_variant['name']}\n"
            f"ID варианта: {self._generated_variant['variant_id']}\n"
            f"Score: {self._generated_variant['score']}\n"
            f"Записей: {self._generated_variant['entries_count']}"
        )

    def _start_process(self, *, calendar_id: int, variants_count: int, time_limit_seconds: int):
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._last_result_payload = None
        self._last_error_payload = None

        process = QProcess(self)
        self._process = process

        project_root = Path(__file__).resolve().parents[3]
        process.setWorkingDirectory(str(project_root))
        process.setProgram(sys.executable)
        process.setArguments([
            "-u",
            "-m",
            "app.presentation.workers.generate_worker",
            str(calendar_id),
            str(variants_count),
            str(time_limit_seconds),
        ])

        process.readyReadStandardOutput.connect(self._on_process_stdout)
        process.readyReadStandardError.connect(self._on_process_stderr)
        process.finished.connect(self._on_process_finished)
        process.errorOccurred.connect(self._on_process_error)

        process.start()
        if not process.waitForStarted(3000):
            self._process = None
            raise RuntimeError("Не удалось запустить процесс генерации.")

    def _on_process_stdout(self):
        if self._process is None:
            return

        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._stdout_buffer += data

        while "\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                self.result_label.setText(f"Лог: {line}")
                continue

            self._handle_worker_payload(payload)

    def _on_process_stderr(self):
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        self._stderr_buffer += data

    def _handle_worker_payload(self, payload: dict):
        msg_type = payload.get("type")

        if msg_type == "progress":
            self.result_label.setText(str(payload.get("message", "Идёт генерация...")))
            return

        if msg_type == "result":
            self._last_result_payload = payload

            variant_ids = payload.get("variant_ids", []) or []
            variant_names = payload.get("variant_names", []) or []

            if variant_ids:
                variant_id = int(variant_ids[0])
                dto = self.schedule_repo.get_variant_dto(variant_id)

                self._generated_variant = {
                    "variant_id": variant_id,
                    "name": variant_names[0] if variant_names else dto.name,
                    "score": int(getattr(dto, "objective_score", 0) or 0),
                    "entries_count": len(getattr(dto, "entries", []) or []),
                }
                self._reload_generated_combo()
            return

        if msg_type == "error":
            self._last_error_payload = payload
            message = str(payload.get("message", "Неизвестная ошибка"))
            tb = str(payload.get("traceback", "") or "")
            QMessageBox.critical(self, "Ошибка генерации", f"{message}\n\n{tb}" if tb else message)

    def _on_process_finished(self, exit_code: int, exit_status):
        self._set_busy(False)
        self._process = None

        if self._last_error_payload is not None:
            self.result_label.setText(f"Генерация завершилась с ошибкой. Код: {exit_code}")
            return

        if exit_status == QProcess.ExitStatus.CrashExit:
            QMessageBox.critical(self, "Критический сбой", "Процесс генерации аварийно завершился.")
            self.result_label.setText("Процесс генерации аварийно завершился.")
            return

        if self._last_result_payload is not None:
            QMessageBox.information(
                self,
                "Готово",
                "Вариант сгенерирован. Теперь можно просмотреть, открыть и утвердить его на этой вкладке."
            )

    def _on_process_error(self, process_error):
        self._set_busy(False)
        self._process = None
        QMessageBox.critical(self, "Ошибка запуска процесса", f"{process_error}")

    def _on_generate(self):
        if self._process is not None:
            QMessageBox.information(self, "Генерация", "Генерация уже выполняется.")
            return

        calendar_id = self.calendar_combo.currentData()
        if not calendar_id:
            QMessageBox.warning(self, "Нет полугодия", "Выберите полугодие.")
            return

        self._set_busy(True)
        self.result_label.setText("Запуск внешнего процесса генерации...")
        self._start_process(
            calendar_id=int(calendar_id),
            variants_count=self.DEFAULT_VARIANTS_COUNT,
            time_limit_seconds=self.DEFAULT_TIME_LIMIT_SECONDS,
        )

    def _preview_selected_variant(self):
        if self._generated_variant is None:
            QMessageBox.warning(self, "Нет выбора", "Нет сгенерированного варианта.")
            return

        dto = self.schedule_repo.get_variant_dto(int(self._generated_variant["variant_id"]))
        QMessageBox.information(
            self,
            "Предпросмотр варианта",
            f"Название: {dto.name}\n"
            f"ID: {dto.id_variant}\n"
            f"Score: {dto.objective_score}\n"
            f"Количество записей: {len(dto.entries)}"
        )

    def _open_selected_variant(self):
        if self._generated_variant is None:
            QMessageBox.warning(self, "Нет выбора", "Нет сгенерированного варианта.")
            return

        variant_id = int(self._generated_variant["variant_id"])

        if self.open_variant_callback is not None:
            self.open_variant_callback(variant_id)
        else:
            QMessageBox.information(
                self,
                "Открытие недоступно",
                "Не настроен переход к просмотру варианта."
            )

    def _approve_selected_variant(self):
        if self._generated_variant is None:
            QMessageBox.warning(self, "Нет выбора", "Нет варианта для утверждения.")
            return

        dialog = ApproveGeneratedDialog(current_name=self._generated_variant["name"], parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_name = dialog.values()
        if not new_name:
            QMessageBox.warning(self, "Пустое название", "Введите название варианта.")
            return

        cmd = SaveVariantCommand(
            variant_id=int(self._generated_variant["variant_id"]),
            name=new_name,
            status="approved",
        )
        self.save_variant_uc.execute(cmd)

        self._generated_variant["name"] = new_name
        self._reload_generated_combo()
        QMessageBox.information(self, "Успешно", "Вариант утверждён.")

    def _on_cancel(self):
        if self._process is None:
            return
        self._process.kill()
        self._process.waitForFinished(3000)
        self._process = None
        self._set_busy(False)
        self.result_label.setText("Генерация отменена пользователем.")

    def closeEvent(self, event):
        try:
            if self._process is not None:
                self._process.kill()
                self._process.waitForFinished(3000)
                self._process = None
        finally:
            super().closeEvent(event)