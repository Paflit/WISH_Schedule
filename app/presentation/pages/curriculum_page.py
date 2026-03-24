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
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


PART_TYPE_LABELS = {
    "lecture": "Лекция",
    "practice": "Практика",
    "computer_practice": "Компьютерная практика",
    "lab": "Лабораторная",
}


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


class CurriculumEditDialog(QDialog):
    """
    Диалог добавления / редактирования записи учебного плана.

    Логика данных остаётся прежней:
    - группа
    - дисциплина
    - тип занятия
    - тип аудитории
    - часы в семестре
    - часы за год
    - комментарий

    Но в таблице часть полей не отображается.
    """

    PART_TYPES = [
        ("Лекция", "lecture"),
        ("Практика", "practice"),
        ("Компьютерная практика", "computer_practice"),
        ("Лабораторная", "lab"),
    ]

    ROOM_TYPES = [
        ("Лекционная", "lecture"),
        ("Обычная аудитория", "classroom"),
        ("Компьютерный класс", "computer"),
        ("Лаборатория", "lab"),
    ]

    def __init__(
        self,
        parent,
        *,
        groups_repo,
        subjects_repo,
        record: Optional[dict] = None,
    ):
        super().__init__(parent)
        self._groups_repo = groups_repo
        self._subjects_repo = subjects_repo
        self._record = record or {}

        self.setWindowTitle(
            "Редактирование записи учебного плана"
            if record
            else "Добавление записи учебного плана"
        )
        self.resize(520, 380)

        root = QVBoxLayout(self)

        form = QFormLayout()
        root.addLayout(form)

        self.group_combo = QComboBox()
        form.addRow("Группа:", self.group_combo)

        self.subject_combo = QComboBox()
        self.subject_combo.setEditable(True)
        self.subject_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        form.addRow("Дисциплина:", self.subject_combo)

        self.part_type_combo = QComboBox()
        for label, value in self.PART_TYPES:
            self.part_type_combo.addItem(label, value)
        form.addRow("Тип занятия:", self.part_type_combo)

        self.room_type_combo = QComboBox()
        for label, value in self.ROOM_TYPES:
            self.room_type_combo.addItem(label, value)
        form.addRow("Тип аудитории:", self.room_type_combo)

        self.hours_semester_spin = QSpinBox()
        self.hours_semester_spin.setRange(0, 2000)
        self.hours_semester_spin.setValue(36)
        form.addRow("Часы в семестре:", self.hours_semester_spin)

        self.hours_year_spin = QSpinBox()
        self.hours_year_spin.setRange(0, 4000)
        self.hours_year_spin.setValue(72)
        form.addRow("Часы за год:", self.hours_year_spin)

        self.comment_combo = QComboBox()
        self.comment_combo.setEditable(True)
        self.comment_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        form.addRow("Комментарий:", self.comment_combo)

        hint = QLabel(
            "В таблице скрыты технические поля: ID, тип аудитории, часы за год и комментарий."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #667085;")
        root.addWidget(hint)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        root.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.part_type_combo.currentIndexChanged.connect(self._sync_default_room_type)

        self._load_groups()
        self._load_subjects()
        self._fill()

    def _load_groups(self) -> None:
        self.group_combo.clear()
        groups = self._groups_repo.list_all()
        for group in groups:
            label = f"{group.group_name} ({group.quantity} чел.)"
            self.group_combo.addItem(label, int(group.id_group))

    def _load_subjects(self) -> None:
        self.subject_combo.clear()
        subjects = self._subjects_repo.list_all()
        for subj in subjects:
            self.subject_combo.addItem(str(subj.subject_name), int(subj.id_subject))

    def _sync_default_room_type(self) -> None:
        part_type = self.part_type_combo.currentData()
        mapping = {
            "lecture": "lecture",
            "practice": "classroom",
            "computer_practice": "computer",
            "lab": "lab",
        }
        room_type = mapping.get(str(part_type), "classroom")
        idx = self.room_type_combo.findData(room_type)
        if idx >= 0:
            self.room_type_combo.setCurrentIndex(idx)

    def _fill(self) -> None:
        if not self._record:
            self._sync_default_room_type()
            return

        group_id = self._record.get("group_id")
        subject_name = str(self._record.get("subject_name", "") or "")
        subject_id = self._record.get("subject_id")
        part_type = str(self._record.get("part_type", "") or "")
        room_type = str(self._record.get("required_room_type", "") or "")
        hours_in_semester = int(self._record.get("hours_in_semester", 0) or 0)
        hours_total_year = int(self._record.get("hours_total_year", 0) or 0)
        comment = str(self._record.get("comment", "") or "")

        idx = self.group_combo.findData(int(group_id) if group_id is not None else None)
        if idx >= 0:
            self.group_combo.setCurrentIndex(idx)

        idx = self.subject_combo.findData(int(subject_id) if subject_id is not None else None)
        if idx >= 0:
            self.subject_combo.setCurrentIndex(idx)
        elif subject_name:
            self.subject_combo.addItem(subject_name, None)
            self.subject_combo.setCurrentText(subject_name)

        idx = self.part_type_combo.findData(part_type)
        if idx >= 0:
            self.part_type_combo.setCurrentIndex(idx)

        idx = self.room_type_combo.findData(room_type)
        if idx >= 0:
            self.room_type_combo.setCurrentIndex(idx)

        self.hours_semester_spin.setValue(hours_in_semester)
        self.hours_year_spin.setValue(hours_total_year)

        if comment:
            self.comment_combo.addItem(comment)
            self.comment_combo.setCurrentText(comment)

    def get_data(self) -> dict:
        return {
            "group_id": self.group_combo.currentData(),
            "subject_id": self.subject_combo.currentData(),
            "subject_name": self.subject_combo.currentText().strip(),
            "part_type": self.part_type_combo.currentData(),
            "required_room_type": self.room_type_combo.currentData(),
            "hours_in_semester": int(self.hours_semester_spin.value()),
            "hours_total_year": int(self.hours_year_spin.value()),
            "comment": self.comment_combo.currentText().strip() or None,
        }


class CurriculumPage(QWidget):
    """
    Страница учебного плана.

    В таблице показываются только:
    - группа
    - дисциплина
    - тип занятия
    - часы/семестр

    Технические поля:
    - id_curriculum
    - required_room_type
    - hours_total_year
    - comment

    остаются в логике, но не отображаются в таблице.
    """

    COL_GROUP = 0
    COL_SUBJECT = 1
    COL_PART_TYPE = 2
    COL_HOURS_SEMESTER = 3

    def __init__(self, curriculum_repo, groups_repo, subjects_repo, calendar_repo):
        super().__init__()
        self._curriculum_repo = curriculum_repo
        self._groups_repo = groups_repo
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
            [
                "Группа",
                "Дисциплина",
                "Тип занятия",
                "Часы/семестр",
            ]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(self.COL_GROUP, 180)
        self.table.setColumnWidth(self.COL_SUBJECT, 260)
        self.table.setColumnWidth(self.COL_PART_TYPE, 170)
        self.table.setColumnWidth(self.COL_HOURS_SEMESTER, 110)
        root.addWidget(self.table)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.add_btn.clicked.connect(self._add_record)
        self.edit_btn.clicked.connect(self._edit_record)
        self.delete_btn.clicked.connect(self._delete_record)
        self.refresh_btn.clicked.connect(self.refresh)
        self.calendar_combo.currentIndexChanged.connect(self._calendar_changed)
        self.add_calendar_btn.clicked.connect(self._create_calendar_dialog)

        self._load_calendars()
        self.refresh()

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            "color: #b42318;" if error else "color: #344054;"
        )

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

    def _selected_record(self) -> Optional[dict]:
        row = self.table.currentRow()
        if row < 0:
            return None

        item = self.table.item(row, self.COL_GROUP)
        if item is None:
            return None

        raw = item.data(Qt.ItemDataRole.UserRole)
        return raw if isinstance(raw, dict) else None

    def _ensure_subject(self, subject_name: str, subject_id: Optional[int]) -> int:
        if subject_id is not None:
            return int(subject_id)

        subject_name = subject_name.strip()
        if not subject_name:
            raise ValueError("Название дисциплины не может быть пустым.")

        with self._curriculum_repo._session_factory() as conn:
            row = conn.execute(
                """
                SELECT id_subject
                FROM Subjects
                WHERE subject_name=?
                """,
                (subject_name,),
            ).fetchone()

            if row:
                return int(row[0])

            cur = conn.execute(
                """
                INSERT INTO Subjects(subject_name)
                VALUES (?)
                """,
                (subject_name,),
            )
            conn.commit()
            return int(cur.lastrowid)

    def _fetch_rows(self) -> list[dict]:
        if self._current_calendar_id is None:
            return []

        with self._curriculum_repo._session_factory() as conn:
            conn.row_factory = sqlite_dict_factory
            rows = conn.execute(
                """
                SELECT
                    ci.id_curriculum,
                    ci.group_id,
                    sg.group_name,
                    ci.subject_id,
                    s.subject_name,
                    ci.part_type,
                    ci.required_room_type,
                    ci.hours_total_year,
                    ci.comment,
                    csp.id_plan,
                    csp.hours_in_semester,
                    csp.calendar_id
                FROM CurriculumSemesterPlan csp
                JOIN CurriculumItems ci ON ci.id_curriculum = csp.curriculum_id
                JOIN StudentGroups sg ON sg.id_group = ci.group_id
                JOIN Subjects s ON s.id_subject = ci.subject_id
                WHERE csp.calendar_id=?
                ORDER BY sg.group_name, s.subject_name, ci.part_type, ci.id_curriculum
                """,
                (int(self._current_calendar_id),),
            ).fetchall()
        return rows

    def _add_record(self) -> None:
        if self._current_calendar_id is None:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите календарь.")
            return

        dlg = CurriculumEditDialog(
            self,
            groups_repo=self._groups_repo,
            subjects_repo=self._subjects_repo,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()

        if data["group_id"] is None:
            QMessageBox.warning(self, "Ошибка", "Нужно выбрать группу.")
            return

        if not data["subject_name"]:
            QMessageBox.warning(self, "Ошибка", "Нужно указать дисциплину.")
            return

        if int(data["hours_in_semester"]) <= 0:
            QMessageBox.warning(self, "Ошибка", "Часы в семестре должны быть больше 0.")
            return

        try:
            subject_id = self._ensure_subject(
                subject_name=str(data["subject_name"]),
                subject_id=data["subject_id"],
            )

            curriculum_id = self._curriculum_repo.create_curriculum_item(
                group_id=int(data["group_id"]),
                subject_id=int(subject_id),
                part_type=str(data["part_type"]),
                required_room_type=str(data["required_room_type"]),
                hours_total_year=int(data["hours_total_year"]),
                comment=data["comment"],
            )
            self._curriculum_repo.create_semester_plan(
                curriculum_id=int(curriculum_id),
                calendar_id=int(self._current_calendar_id),
                hours_in_semester=int(data["hours_in_semester"]),
                credits=None,
                spread_mode="auto_even",
                comment=data["comment"],
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось добавить запись учебного плана:\n{exc}",
            )
            return

        self.refresh()
        self._set_status("Запись учебного плана добавлена.")

    def _edit_record(self) -> None:
        record = self._selected_record()
        if record is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите запись.")
            return

        dlg = CurriculumEditDialog(
            self,
            groups_repo=self._groups_repo,
            subjects_repo=self._subjects_repo,
            record=record,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()

        if data["group_id"] is None:
            QMessageBox.warning(self, "Ошибка", "Нужно выбрать группу.")
            return

        if not data["subject_name"]:
            QMessageBox.warning(self, "Ошибка", "Нужно указать дисциплину.")
            return

        if int(data["hours_in_semester"]) <= 0:
            QMessageBox.warning(self, "Ошибка", "Часы в семестре должны быть больше 0.")
            return

        try:
            subject_id = self._ensure_subject(
                subject_name=str(data["subject_name"]),
                subject_id=data["subject_id"],
            )

            self._curriculum_repo.upsert_curriculum_item(
                curriculum_id=int(record["id_curriculum"]),
                group_id=int(data["group_id"]),
                subject_id=int(subject_id),
                part_type=str(data["part_type"]),
                required_room_type=str(data["required_room_type"]),
                hours_total_year=int(data["hours_total_year"]),
                comment=data["comment"],
            )

            with self._curriculum_repo._session_factory() as conn:
                conn.execute(
                    """
                    UPDATE CurriculumSemesterPlan
                    SET hours_in_semester=?,
                        comment=?
                    WHERE id_plan=?
                    """,
                    (
                        int(data["hours_in_semester"]),
                        data["comment"],
                        int(record["id_plan"]),
                    ),
                )
                conn.commit()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось сохранить изменения:\n{exc}",
            )
            return

        self.refresh()
        self._set_status("Запись учебного плана обновлена.")

    def _delete_record(self) -> None:
        record = self._selected_record()
        if record is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите запись.")
            return

        answer = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Удалить запись '{record.get('subject_name', '')}' "
            f"для группы '{record.get('group_name', '')}'?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            with self._curriculum_repo._session_factory() as conn:
                conn.execute(
                    "DELETE FROM CurriculumSemesterPlan WHERE id_plan=?",
                    (int(record["id_plan"]),),
                )
                conn.execute(
                    "DELETE FROM CurriculumItems WHERE id_curriculum=?",
                    (int(record["id_curriculum"]),),
                )
                conn.commit()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось удалить запись:\n{exc}",
            )
            return

        self.refresh()
        self._set_status("Запись учебного плана удалена.")

    def refresh(self) -> None:
        if self._current_calendar_id is None:
            self.table.setRowCount(0)
            self._set_status("Календарь не выбран.", error=True)
            return

        try:
            rows = self._fetch_rows()
        except Exception as exc:
            self.table.setRowCount(0)
            self._set_status(
                f"Не удалось загрузить учебный план: {exc}",
                error=True,
            )
            return

        self.table.setRowCount(0)

        for row_idx, record in enumerate(rows):
            self.table.insertRow(row_idx)

            group_name = str(record.get("group_name", "") or "")
            subject_name = str(record.get("subject_name", "") or "")
            part_type = str(record.get("part_type", "") or "")
            hours_in_semester = int(record.get("hours_in_semester", 0) or 0)

            group_item = QTableWidgetItem(group_name)
            group_item.setData(Qt.ItemDataRole.UserRole, record)

            subject_item = QTableWidgetItem(subject_name)
            part_type_item = QTableWidgetItem(
                PART_TYPE_LABELS.get(part_type, part_type or "—")
            )
            hours_item = QTableWidgetItem(str(hours_in_semester))

            self.table.setItem(row_idx, self.COL_GROUP, group_item)
            self.table.setItem(row_idx, self.COL_SUBJECT, subject_item)
            self.table.setItem(row_idx, self.COL_PART_TYPE, part_type_item)
            self.table.setItem(row_idx, self.COL_HOURS_SEMESTER, hours_item)

        self._set_status(f"Загружено записей учебного плана: {len(rows)}")


def sqlite_dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}