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
    QLineEdit,
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


class CurriculumAddDialog(QDialog):

    PART_TYPES = [
        ("Лекция", "lecture"),
        ("Практика", "practice"),
        ("Компьютерная практика", "computer_practice"),
        ("Лабораторная", "lab"),
    ]

    def __init__(self, parent, *, groups_repo, subjects_repo, last_group_id=None):
        super().__init__(parent)
        self._groups_repo = groups_repo
        self._subjects_repo = subjects_repo
        self._last_group_id = last_group_id

        self.setWindowTitle("Добавление записи учебного плана")
        self.resize(520, 400)

        root = QVBoxLayout(self)

        form = QFormLayout()
        root.addLayout(form)

        self.group_combo = QComboBox()
        form.addRow("Группа:", self.group_combo)

        self.subject_combo = QComboBox()
        self.subject_combo.setEditable(True)
        self.subject_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.subject_combo.setPlaceholderText("Введите название дисциплины")
        form.addRow("Дисциплина:", self.subject_combo)

        form.addRow(QLabel(""))
        form.addRow(QLabel("Типы занятий:"))

        self.part_type_widgets = {}
        for label, value in self.PART_TYPES:
            checkbox = QCheckBox(label)
            spinbox = QSpinBox()
            spinbox.setRange(0, 500)
            spinbox.setValue(36)
            spinbox.setEnabled(False)
            
            checkbox.toggled.connect(lambda checked, sb=spinbox: sb.setEnabled(checked))
            
            row_layout = QHBoxLayout()
            row_layout.addWidget(checkbox)
            row_layout.addWidget(QLabel("Часы:"))
            row_layout.addWidget(spinbox)
            row_layout.addStretch()
            
            form.addRow(row_layout)
            
            self.part_type_widgets[value] = {
                "checkbox": checkbox,
                "spinbox": spinbox,
            }

        # Чекбокс для деления группы на подгруппы
        form.addRow(QLabel(""))
        self.split_subgroups_checkbox = QCheckBox("Делить группу на подгруппы (А и Б)")
        form.addRow(self.split_subgroups_checkbox)

        hint = QLabel(
            "Отметьте нужные типы занятий и укажите количество часов для каждого. "
            "Тип аудитории определяется автоматически по типу занятия.\n\n"
            "При делении группы на подгруппы будут созданы две записи с половиной студентов в каждой."
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

        self._load_groups()
        self._load_subjects()
        
        # Устанавливаем последнюю выбранную группу
        if self._last_group_id is not None:
            idx = self.group_combo.findData(self._last_group_id)
            if idx >= 0:
                self.group_combo.setCurrentIndex(idx)

    def _load_groups(self) -> None:
        self.group_combo.clear()
        groups = self._groups_repo.list_all()
        for group in groups:
            label = f"{group.group_name} ({group.quantity} чел.)"
            self.group_combo.addItem(label, int(group.id_group))

    def _load_subjects(self) -> None:
        self.subject_combo.clear()
        # Добавляем пустой элемент по умолчанию
        self.subject_combo.addItem("", None)
        subjects = self._subjects_repo.list_all()
        for subj in subjects:
            self.subject_combo.addItem(str(subj.subject_name), int(subj.id_subject))

    def get_data(self) -> dict:
        selected_types = []
        
        for part_type, widgets in self.part_type_widgets.items():
            if widgets["checkbox"].isChecked():
                hours = widgets["spinbox"].value()
                if hours > 0:
                    selected_types.append({
                        "part_type": part_type,
                        "hours_in_semester": hours,
                    })
        
        return {
            "group_id": self.group_combo.currentData(),
            "subject_id": self.subject_combo.currentData(),
            "subject_name": self.subject_combo.currentText().strip(),
            "selected_types": selected_types,
            "split_into_subgroups": self.split_subgroups_checkbox.isChecked(),
        }


class CurriculumEditDialog(QDialog):

    PART_TYPES = [
        ("Лекция", "lecture"),
        ("Практика", "practice"),
        ("Компьютерная практика", "computer_practice"),
        ("Лабораторная", "lab"),
    ]

    def __init__(
        self,
        parent,
        *,
        groups_repo,
        subjects_repo,
        record: dict,
    ):
        super().__init__(parent)
        self._groups_repo = groups_repo
        self._subjects_repo = subjects_repo
        self._record = record

        self.setWindowTitle("Редактирование записи учебного плана")
        self.resize(450, 280)

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

        self.hours_semester_spin = QSpinBox()
        self.hours_semester_spin.setRange(0, 500)
        self.hours_semester_spin.setValue(36)
        form.addRow("Часы в семестре:", self.hours_semester_spin)

        hint = QLabel(
            "Тип аудитории определяется автоматически по типу занятия."
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
        # Добавляем пустой элемент по умолчанию
        self.subject_combo.addItem("", None)
        subjects = self._subjects_repo.list_all()
        for subj in subjects:
            self.subject_combo.addItem(str(subj.subject_name), int(subj.id_subject))

    def _fill(self) -> None:
        group_id = self._record.get("group_id")
        subject_name = str(self._record.get("subject_name", "") or "")
        subject_id = self._record.get("subject_id")
        part_type = str(self._record.get("part_type", "") or "")
        hours_in_semester = int(self._record.get("hours_in_semester", 0) or 0)

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

        self.hours_semester_spin.setValue(hours_in_semester)

    def get_data(self) -> dict:
        part_type = self.part_type_combo.currentData()
        
        # Автоматическое определение типа аудитории
        room_type_mapping = {
            "lecture": "lecture",
            "practice": "classroom",
            "computer_practice": "computer",
            "lab": "lab",
        }
        
        return {
            "group_id": self.group_combo.currentData(),
            "subject_id": self.subject_combo.currentData(),
            "subject_name": self.subject_combo.currentText().strip(),
            "part_type": part_type,
            "required_room_type": room_type_mapping.get(str(part_type), "classroom"),
            "hours_in_semester": int(self.hours_semester_spin.value()),
        }


class CurriculumPage(QWidget):

    COL_ID = 0
    COL_GROUP = 1
    COL_SUBJECT = 2
    COL_PART_TYPE = 3
    COL_HOURS_SEMESTER = 4

    def __init__(self, curriculum_repo, groups_repo, subjects_repo, calendar_repo):
        super().__init__()
        self._curriculum_repo = curriculum_repo
        self._groups_repo = groups_repo
        self._subjects_repo = subjects_repo
        self._calendar_repo = calendar_repo

        self._current_calendar_id: Optional[int] = None
        self._last_selected_group_id: Optional[int] = None  # Запоминаем последнюю группу
        self._all_rows: list[dict] = []
        self._sort_column: Optional[int] = None
        self._sort_order: int = 0

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

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по таблице...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMaximumWidth(260)
        toolbar.addWidget(self.search_edit)

        toolbar.addStretch(1)

        self.add_btn = QPushButton("Добавить")
        self.edit_btn = QPushButton("Редактировать")
        self.delete_btn = QPushButton("Удалить")
        self.refresh_btn = QPushButton("Обновить")

        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.edit_btn)
        toolbar.addWidget(self.delete_btn)
        toolbar.addWidget(self.refresh_btn)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
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
        self.table.horizontalHeader().sectionClicked.connect(self._toggle_sort)
        self.table.setColumnWidth(self.COL_ID, 70)
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
        self.search_edit.textChanged.connect(self._apply_filters)

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
            # Ищем дисциплину без учета регистра и лишних пробелов
            row = conn.execute(
                """
                SELECT id_subject
                FROM Subjects
                WHERE LOWER(TRIM(subject_name))=LOWER(?)
                """,
                (subject_name,),
            ).fetchone()

            if row:
                return int(row[0])

            # Создаем новую дисциплину
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

        dlg = CurriculumAddDialog(
            self,
            groups_repo=self._groups_repo,
            subjects_repo=self._subjects_repo,
            last_group_id=self._last_selected_group_id,  # Передаем последнюю группу
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

        if not data["selected_types"]:
            QMessageBox.warning(self, "Ошибка", "Нужно выбрать хотя бы один тип занятия.")
            return

        try:
            # Запоминаем выбранную группу
            self._last_selected_group_id = data["group_id"]
            
            subject_id = self._ensure_subject(
                subject_name=str(data["subject_name"]),
                subject_id=data["subject_id"],
            )

            # Автоматическое определение типа аудитории по типу занятия
            room_type_mapping = {
                "lecture": "lecture",
                "practice": "classroom",
                "computer_practice": "computer",
                "lab": "lab",
            }

            # Создаем записи для каждого выбранного типа занятия
            added_count = 0
            split_into_subgroups = data.get("split_into_subgroups", False)
            
            for type_data in data["selected_types"]:
                part_type = type_data["part_type"]
                hours_in_semester = type_data["hours_in_semester"]
                required_room_type = room_type_mapping.get(part_type, "classroom")

                if split_into_subgroups:
                    # Создаем две записи для подгрупп А и Б
                    for subgroup_label in ["A", "B"]:
                        curriculum_id = self._curriculum_repo.create_curriculum_item(
                            group_id=int(data["group_id"]),
                            subject_id=int(subject_id),
                            part_type=str(part_type),
                            required_room_type=str(required_room_type),
                            hours_total_year=0,
                            comment=f"Подгруппа {subgroup_label}",
                        )
                        self._curriculum_repo.create_semester_plan(
                            curriculum_id=int(curriculum_id),
                            calendar_id=int(self._current_calendar_id),
                            hours_in_semester=int(hours_in_semester),
                            credits=None,
                            spread_mode="auto_even",
                            comment=f"Подгруппа {subgroup_label}",
                        )
                        added_count += 1
                else:
                    # Создаем одну запись для всей группы
                    curriculum_id = self._curriculum_repo.create_curriculum_item(
                        group_id=int(data["group_id"]),
                        subject_id=int(subject_id),
                        part_type=str(part_type),
                        required_room_type=str(required_room_type),
                        hours_total_year=0,
                        comment=None,
                    )
                    self._curriculum_repo.create_semester_plan(
                        curriculum_id=int(curriculum_id),
                        calendar_id=int(self._current_calendar_id),
                        hours_in_semester=int(hours_in_semester),
                        credits=None,
                        spread_mode="auto_even",
                        comment=None,
                    )
                    added_count += 1

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось добавить запись учебного плана:\n{exc}",
            )
            return

        self.refresh()
        self._set_status(f"Добавлено записей учебного плана: {added_count}")

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
                hours_total_year=0,  # Не используется
                comment=None,
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
                        None,
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
            self._all_rows = list(self._fetch_rows())
        except Exception as exc:
            self.table.setRowCount(0)
            self._set_status(
                f"Не удалось загрузить учебный план: {exc}",
                error=True,
            )
            return

        self._apply_filters()

    def _toggle_sort(self, column: int) -> None:
        if self._sort_column != column:
            self._sort_column = column
            self._sort_order = 1
        elif self._sort_order == 1:
            self._sort_order = -1
        else:
            self._sort_column = None
            self._sort_order = 0

        self._apply_filters()

    def _apply_filters(self) -> None:
        rows = list(self._all_rows)
        query = self.search_edit.text().strip().lower()

        if query:
            filtered = []
            for record in rows:
                haystack = " ".join(
                    [
                        str(record.get("group_name", "") or ""),
                        str(record.get("subject_name", "") or ""),
                        str(record.get("part_type", "") or ""),
                        str(record.get("hours_in_semester", "") or ""),
                        str(record.get("comment", "") or ""),
                    ]
                ).lower()
                if query in haystack:
                    filtered.append(record)
            rows = filtered

        if self._sort_column is not None and self._sort_order != 0:
            key_map = {
                self.COL_ID: lambda x: int(x.get("id_curriculum", 0) or 0),
                self.COL_GROUP: lambda x: str(x.get("group_name", "") or "").lower(),
                self.COL_SUBJECT: lambda x: str(x.get("subject_name", "") or "").lower(),
                self.COL_PART_TYPE: lambda x: str(x.get("part_type", "") or "").lower(),
                self.COL_HOURS_SEMESTER: lambda x: int(x.get("hours_in_semester", 0) or 0),
            }
            rows.sort(key=key_map[self._sort_column], reverse=self._sort_order < 0)

        self._update_header_labels()
        self._render_rows(rows)

    def _update_header_labels(self) -> None:
        base_headers = ["ID", "Группа", "Дисциплина", "Тип занятия", "Часы/семестр"]
        headers = []
        for idx, title in enumerate(base_headers):
            if self._sort_column == idx:
                headers.append(f"{title} {'▲' if self._sort_order > 0 else '▼' if self._sort_order < 0 else ''}".strip())
            else:
                headers.append(title)
        self.table.setHorizontalHeaderLabels(headers)

    def _render_rows(self, rows: list[dict]) -> None:
        self.table.clearSpans()
        self.table.setRowCount(0)

        for row_idx, record in enumerate(rows):
            self.table.insertRow(row_idx)

            id_curriculum = int(record.get("id_curriculum", 0) or 0)
            group_name = str(record.get("group_name", "") or "")
            subject_name = str(record.get("subject_name", "") or "")
            part_type = str(record.get("part_type", "") or "")
            hours_in_semester = int(record.get("hours_in_semester", 0) or 0)

            id_item = QTableWidgetItem(str(id_curriculum))
            group_item = QTableWidgetItem(group_name)
            group_item.setData(Qt.ItemDataRole.UserRole, record)

            subject_item = QTableWidgetItem(subject_name)
            part_type_item = QTableWidgetItem(
                PART_TYPE_LABELS.get(part_type, part_type or "—")
            )
            hours_item = QTableWidgetItem(str(hours_in_semester))

            self.table.setItem(row_idx, self.COL_ID, id_item)
            self.table.setItem(row_idx, self.COL_GROUP, group_item)
            self.table.setItem(row_idx, self.COL_SUBJECT, subject_item)
            self.table.setItem(row_idx, self.COL_PART_TYPE, part_type_item)
            self.table.setItem(row_idx, self.COL_HOURS_SEMESTER, hours_item)

        # Объединение ячеек с одинаковыми значениями
        self._merge_duplicate_cells(rows)

        self._set_status(f"Загружено записей учебного плана: {len(rows)}")

    def _merge_duplicate_cells(self, rows: list[dict]) -> None:
        if not rows:
            return

        # Объединение для столбца "Группа"
        self._merge_column_cells(rows, self.COL_GROUP, "group_name")
        
        # Объединение для столбца "Дисциплина" (с учетом группы)
        self._merge_column_cells_with_context(
            rows, 
            self.COL_SUBJECT, 
            "subject_name",
            context_key="group_name"
        )

    def _merge_column_cells(self, rows: list[dict], col_idx: int, key: str) -> None:
        if not rows:
            return

        start_row = 0
        current_value = rows[0].get(key)

        for row_idx in range(1, len(rows)):
            value = rows[row_idx].get(key)
            
            if value != current_value:
                # Объединяем предыдущий диапазон
                if row_idx - start_row > 1:
                    self.table.setSpan(start_row, col_idx, row_idx - start_row, 1)
                
                # Начинаем новый диапазон
                start_row = row_idx
                current_value = value

        # Объединяем последний диапазон
        if len(rows) - start_row > 1:
            self.table.setSpan(start_row, col_idx, len(rows) - start_row, 1)

    def _merge_column_cells_with_context(
        self, 
        rows: list[dict], 
        col_idx: int, 
        key: str,
        context_key: str
    ) -> None:
        if not rows:
            return

        start_row = 0
        current_value = rows[0].get(key)
        current_context = rows[0].get(context_key)

        for row_idx in range(1, len(rows)):
            value = rows[row_idx].get(key)
            context = rows[row_idx].get(context_key)
            
            # Если изменился контекст или значение
            if value != current_value or context != current_context:
                # Объединяем предыдущий диапазон
                if row_idx - start_row > 1:
                    self.table.setSpan(start_row, col_idx, row_idx - start_row, 1)
                
                # Начинаем новый диапазон
                start_row = row_idx
                current_value = value
                current_context = context

        # Объединяем последний диапазон
        if len(rows) - start_row > 1:
            self.table.setSpan(start_row, col_idx, len(rows) - start_row, 1)


def sqlite_dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
