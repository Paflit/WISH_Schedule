from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


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


class TeacherEditDialog(QDialog):
    """
    Диалог создания / редактирования преподавателя.

    Актуальная модель страницы:
    - ФИО
    - дисциплины
    - рабочие дни отображаются вычисляемо из availability и здесь не редактируются
    - ID руками не вводится
    """

    def __init__(
        self,
        parent,
        subjects_repo,
        teacher: Optional[object] = None,
        selected_subject_ids: Optional[list[int]] = None,
    ):
        super().__init__(parent)
        self._subjects_repo = subjects_repo
        self._teacher = teacher
        self._selected_subject_ids = set(selected_subject_ids or [])

        self.setWindowTitle(
            "Редактирование преподавателя" if teacher is not None else "Добавление преподавателя"
        )
        self.resize(520, 520)

        root = QVBoxLayout(self)

        form = QFormLayout()
        root.addLayout(form)

        self.name_combo = QComboBox()
        self.name_combo.setEditable(True)
        self.name_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.name_combo.setPlaceholderText("Введите ФИО преподавателя")
        form.addRow("ФИО:", self.name_combo)

        hint = QLabel(
            "Рабочие дни здесь не редактируются. Они рассчитываются автоматически "
            "по доступности преподавателя в календаре."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #667085;")
        root.addWidget(hint)

        root.addWidget(QLabel("Дисциплины преподавателя:"))

        self.subjects_list = QListWidget()
        self.subjects_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        root.addWidget(self.subjects_list, 1)

        buttons_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Выбрать все")
        self.clear_all_btn = QPushButton("Снять все")
        buttons_row.addWidget(self.select_all_btn)
        buttons_row.addWidget(self.clear_all_btn)
        buttons_row.addStretch(1)
        root.addLayout(buttons_row)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        root.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.select_all_btn.clicked.connect(self._select_all_subjects)
        self.clear_all_btn.clicked.connect(self._clear_all_subjects)

        self._load_subjects()
        self._fill_teacher()

    def _load_subjects(self) -> None:
        self.subjects_list.clear()

        subjects = self._subjects_repo.list_all()
        for subj in subjects:
            item = QListWidgetItem(str(subj.subject_name))
            item.setData(Qt.ItemDataRole.UserRole, int(subj.id_subject))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if int(subj.id_subject) in self._selected_subject_ids
                else Qt.CheckState.Unchecked
            )
            self.subjects_list.addItem(item)

    def _fill_teacher(self) -> None:
        if self._teacher is None:
            return
        self.name_combo.addItem(str(getattr(self._teacher, "full_name", "") or ""))
        self.name_combo.setCurrentText(str(getattr(self._teacher, "full_name", "") or ""))

    def _select_all_subjects(self) -> None:
        for i in range(self.subjects_list.count()):
            self.subjects_list.item(i).setCheckState(Qt.CheckState.Checked)

    def _clear_all_subjects(self) -> None:
        for i in range(self.subjects_list.count()):
            self.subjects_list.item(i).setCheckState(Qt.CheckState.Unchecked)

    def get_data(self) -> tuple[str, list[int]]:
        full_name = self.name_combo.currentText().strip()
        subject_ids: list[int] = []

        for i in range(self.subjects_list.count()):
            item = self.subjects_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                subject_ids.append(int(item.data(Qt.ItemDataRole.UserRole)))

        return full_name, subject_ids


class TeachersPage(QWidget):
    """
    Актуальная страница преподавателей.

    Показывает:
    - ID
    - ФИО
    - рабочие дни
    - дисциплины

    Важно:
    - ID не вводится вручную;
    - старые поля hard/soft/method day не торчат в UI;
    - рабочие дни берутся из list_with_subjects_and_days(...);
    - рядом с выбором календаря можно создать новый семестр.
    """

    def __init__(self, teachers_repo, subjects_repo, calendar_repo):
        super().__init__()
        self._teachers_repo = teachers_repo
        self._subjects_repo = subjects_repo
        self._calendar_repo = calendar_repo

        self._current_calendar_id: Optional[int] = None

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

        self.add_btn = QPushButton("Добавить")
        self.edit_btn = QPushButton("Редактировать")
        self.delete_btn = QPushButton("Удалить")
        self.refresh_btn = QPushButton("Обновить")

        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.edit_btn)
        toolbar.addWidget(self.delete_btn)
        toolbar.addWidget(self.refresh_btn)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["ID", "ФИО", "Рабочие дни", "Список дисциплин"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 250)
        self.table.setColumnWidth(2, 150)
        root.addWidget(self.table)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.add_btn.clicked.connect(self._add_teacher)
        self.edit_btn.clicked.connect(self._edit_teacher)
        self.delete_btn.clicked.connect(self._delete_teacher)
        self.refresh_btn.clicked.connect(self.refresh)
        self.calendar_combo.currentIndexChanged.connect(self._calendar_changed)
        self.add_calendar_btn.clicked.connect(self._create_calendar_dialog)

        self._load_calendars()
        self.refresh()

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            "color: #b42318;" if error else "color: #344054;"
        )

    def _selected_teacher_id(self) -> Optional[int]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        try:
            return int(item.data(Qt.ItemDataRole.UserRole))
        except (TypeError, ValueError):
            return None

    def _select_calendar_by_id(self, calendar_id: int) -> None:
        idx = self.calendar_combo.findData(int(calendar_id))
        if idx >= 0:
            self.calendar_combo.setCurrentIndex(idx)
            self._current_calendar_id = int(calendar_id)

    def _load_calendars(self) -> None:
        self.calendar_combo.blockSignals(True)
        self.calendar_combo.clear()

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

        if self.calendar_combo.count() > 0:
            self._current_calendar_id = int(self.calendar_combo.currentData())
        else:
            self._current_calendar_id = None

        self.calendar_combo.blockSignals(False)

        if self.calendar_combo.count() == 0:
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
        self.refresh()
        self._set_status("Семестр успешно создан.")

    def _calendar_changed(self) -> None:
        value = self.calendar_combo.currentData()
        self._current_calendar_id = int(value) if value is not None else None
        self.refresh()

    # ---------------------------------------------------------
    # CRUD
    # ---------------------------------------------------------
    def _add_teacher(self) -> None:
        dlg = TeacherEditDialog(
            self,
            subjects_repo=self._subjects_repo,
            teacher=None,
            selected_subject_ids=[],
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        full_name, subject_ids = dlg.get_data()

        if not full_name:
            QMessageBox.warning(self, "Ошибка", "ФИО преподавателя не может быть пустым.")
            return

        try:
            teacher_id = self._teachers_repo.create(
                full_name=full_name,
                hard_max=6,
                soft_max=4,
                needs_method_day=True,
                commentary=None,
            )
            self._teachers_repo.replace_teacher_subjects(teacher_id, subject_ids)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось добавить преподавателя:\n{exc}")
            return

        self.refresh()
        self._set_status(f"Преподаватель '{full_name}' добавлен.")

    def _edit_teacher(self) -> None:
        teacher_id = self._selected_teacher_id()
        if teacher_id is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите преподавателя.")
            return

        teacher = self._teachers_repo.get_by_id(int(teacher_id))
        if teacher is None:
            QMessageBox.warning(self, "Ошибка", "Преподаватель не найден.")
            self.refresh()
            return

        selected_subject_ids = self._teachers_repo.get_teacher_subject_ids(int(teacher_id))

        dlg = TeacherEditDialog(
            self,
            subjects_repo=self._subjects_repo,
            teacher=teacher,
            selected_subject_ids=selected_subject_ids,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        full_name, subject_ids = dlg.get_data()

        if not full_name:
            QMessageBox.warning(self, "Ошибка", "ФИО преподавателя не может быть пустым.")
            return

        try:
            self._teachers_repo.update(
                id_teacher=int(teacher_id),
                full_name=full_name,
                hard_max=int(getattr(teacher, "hard_max_pairs_per_day", 6)),
                soft_max=int(getattr(teacher, "soft_max_pairs_per_day", 4)),
                needs_method_day=bool(getattr(teacher, "needs_method_day", True)),
                commentary=None,
            )
            self._teachers_repo.replace_teacher_subjects(int(teacher_id), subject_ids)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось сохранить изменения преподавателя:\n{exc}",
            )
            return

        self.refresh()
        self._set_status(f"Преподаватель '{full_name}' обновлён.")

    def _delete_teacher(self) -> None:
        teacher_id = self._selected_teacher_id()
        if teacher_id is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите преподавателя.")
            return

        teacher = self._teachers_repo.get_by_id(int(teacher_id))
        teacher_name = getattr(teacher, "full_name", f"id={teacher_id}") if teacher else f"id={teacher_id}"

        answer = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Удалить преподавателя '{teacher_name}'?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self._teachers_repo.delete(int(teacher_id))
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить преподавателя:\n{exc}")
            return

        self.refresh()
        self._set_status(f"Преподаватель '{teacher_name}' удалён.")

    # ---------------------------------------------------------
    # Refresh
    # ---------------------------------------------------------
    def refresh(self) -> None:
        try:
            rows = self._teachers_repo.list_with_subjects_and_days(self._current_calendar_id)
        except Exception as exc:
            self.table.setRowCount(0)
            self._set_status(f"Не удалось загрузить преподавателей: {exc}", error=True)
            return

        self.table.setRowCount(0)

        for row_idx, teacher in enumerate(rows):
            self.table.insertRow(row_idx)

            id_teacher = int(getattr(teacher, "id_teacher", 0))
            full_name = str(getattr(teacher, "full_name", "") or "")
            working_days = str(getattr(teacher, "working_days", "—") or "—")
            subjects = str(getattr(teacher, "subjects", "—") or "—")

            id_item = QTableWidgetItem(str(id_teacher))
            id_item.setData(Qt.ItemDataRole.UserRole, id_teacher)

            name_item = QTableWidgetItem(full_name)
            days_item = QTableWidgetItem(working_days)
            subjects_item = QTableWidgetItem(subjects)

            self.table.setItem(row_idx, 0, id_item)
            self.table.setItem(row_idx, 1, name_item)
            self.table.setItem(row_idx, 2, days_item)
            self.table.setItem(row_idx, 3, subjects_item)

        self._set_status(f"Загружено преподавателей: {len(rows)}")