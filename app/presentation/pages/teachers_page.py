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
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.presentation.widgets.availability_calendar import AvailabilityCalendar


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


class TeacherEditDialog(QDialog):
    def __init__(
        self,
        parent,
        subjects_repo,
        calendar_repo,
        teacher: Optional[object] = None,
        selected_subject_ids: Optional[list[int]] = None,
        selected_subject_rules: Optional[dict[int, dict]] = None,
        current_calendar_id: Optional[int] = None,
    ):
        super().__init__(parent)
        self._subjects_repo = subjects_repo
        self._calendar_repo = calendar_repo
        self._teacher = teacher
        self._selected_subject_ids = set(selected_subject_ids or [])
        self._selected_subject_rules = selected_subject_rules or {}
        self._current_calendar_id = current_calendar_id
        self._subject_rule_widgets: dict[int, dict[str, QCheckBox]] = {}

        self.setWindowTitle(
            "Редактирование преподавателя" if teacher is not None else "Добавление преподавателя"
        )
        self.resize(700, 600)

        root = QVBoxLayout(self)

        form = QFormLayout()
        root.addLayout(form)

        self.name_combo = QComboBox()
        self.name_combo.setEditable(True)
        self.name_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.name_combo.setPlaceholderText("Введите ФИО преподавателя")
        form.addRow("ФИО:", self.name_combo)

        # Вкладки для дисциплин и календаря
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        # Вкладка 1: Дисциплины
        subjects_tab = QWidget()
        subjects_layout = QVBoxLayout(subjects_tab)

        subjects_layout.addWidget(QLabel("Дисциплины и типы занятий преподавателя:"))

        self.subjects_scroll = QScrollArea()
        self.subjects_scroll.setWidgetResizable(True)
        self.subjects_container = QWidget()
        self.subjects_grid = QGridLayout(self.subjects_container)
        self.subjects_grid.setContentsMargins(0, 0, 0, 0)
        self.subjects_grid.setColumnStretch(0, 3)
        self.subjects_grid.setColumnStretch(1, 1)
        self.subjects_grid.setColumnStretch(2, 2)
        self.subjects_grid.setColumnStretch(3, 1)
        self.subjects_scroll.setWidget(self.subjects_container)
        subjects_layout.addWidget(self.subjects_scroll, 1)

        buttons_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Выбрать все")
        self.clear_all_btn = QPushButton("Снять все")
        buttons_row.addWidget(self.select_all_btn)
        buttons_row.addWidget(self.clear_all_btn)
        buttons_row.addStretch(1)
        subjects_layout.addLayout(buttons_row)

        tabs.addTab(subjects_tab, "Дисциплины")

        # Вкладка 2: Календарь доступности
        calendar_tab = QWidget()
        calendar_layout = QVBoxLayout(calendar_tab)

        # Получаем параметры календаря
        pairs_per_day = 8
        include_saturday = True
        
        if self._current_calendar_id:
            try:
                calendar = self._calendar_repo.get_calendar(self._current_calendar_id)
                # Определяем количество пар из слотов
                slots = self._calendar_repo.list_time_slots(self._current_calendar_id)
                if slots:
                    pairs_per_day = max(slot.pair_number for slot in slots)
                    # Проверяем наличие субботы
                    include_saturday = any(slot.day_of_week == 6 for slot in slots)
            except:
                pass

        self.availability_calendar = AvailabilityCalendar(
            pairs_per_day=pairs_per_day,
            include_saturday=include_saturday
        )
        
        scroll = QScrollArea()
        scroll.setWidget(self.availability_calendar)
        scroll.setWidgetResizable(True)
        calendar_layout.addWidget(scroll)

        tabs.addTab(calendar_tab, "Календарь доступности")

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
        while self.subjects_grid.count():
            item = self.subjects_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._subject_rule_widgets.clear()

        headers = ["Дисциплина", "Лекция", "Практика", "Лаб."]
        for col, title in enumerate(headers):
            label = QLabel(title)
            label.setStyleSheet("font-weight: 600;")
            self.subjects_grid.addWidget(label, 0, col)

        practice_hint = QLabel("Учеб. / Комп.")
        practice_hint.setStyleSheet("color: #667085; font-size: 11px;")
        practice_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subjects_grid.addWidget(practice_hint, 1, 2)

        subjects = self._subjects_repo.list_all()
        for row, subj in enumerate(subjects, start=2):
            subject_id = int(subj.id_subject)
            subject_name = str(subj.subject_name)
            is_selected = subject_id in self._selected_subject_ids
            rules = self._selected_subject_rules.get(subject_id, {})

            subject_checkbox = QCheckBox(subject_name)
            subject_checkbox.setChecked(is_selected)
            self.subjects_grid.addWidget(subject_checkbox, row, 0)

            lecture_cb = QCheckBox()
            lecture_cb.setChecked(bool(rules.get("can_lecture", True)))
            self.subjects_grid.addWidget(lecture_cb, row, 1, alignment=Qt.AlignmentFlag.AlignCenter)

            practice_widget = QWidget()
            practice_layout = QHBoxLayout(practice_widget)
            practice_layout.setContentsMargins(0, 0, 0, 0)
            practice_layout.setSpacing(8)

            practice_cb = QCheckBox()
            practice_cb.setChecked(bool(rules.get("can_practice", True)))
            practice_cb.setToolTip("Учебная практика")

            computer_cb = QCheckBox()
            computer_cb.setChecked(bool(rules.get("can_computer_practice", True)))
            computer_cb.setToolTip("Компьютерная практика")

            practice_label = QLabel("Учеб.")
            practice_label.setStyleSheet("color: #344054;")
            computer_label = QLabel("Комп.")
            computer_label.setStyleSheet("color: #344054;")

            practice_layout.addWidget(practice_label)
            practice_layout.addWidget(practice_cb)
            practice_layout.addSpacing(8)
            practice_layout.addWidget(computer_label)
            practice_layout.addWidget(computer_cb)
            practice_layout.addStretch(1)

            self.subjects_grid.addWidget(practice_widget, row, 2)

            lab_cb = QCheckBox()
            lab_cb.setChecked(bool(rules.get("can_lab", True)))
            self.subjects_grid.addWidget(lab_cb, row, 3, alignment=Qt.AlignmentFlag.AlignCenter)

            def sync_enabled(checked: bool, boxes=(lecture_cb, practice_cb, computer_cb, lab_cb)):
                for box in boxes:
                    box.setEnabled(checked)

            subject_checkbox.toggled.connect(sync_enabled)
            sync_enabled(is_selected)

            self._subject_rule_widgets[subject_id] = {
                "subject": subject_checkbox,
                "can_lecture": lecture_cb,
                "can_practice": practice_cb,
                "can_computer_practice": computer_cb,
                "can_lab": lab_cb,
            }

    def _fill_teacher(self) -> None:
        if self._teacher is None:
            return
        self.name_combo.addItem(str(getattr(self._teacher, "full_name", "") or ""))
        self.name_combo.setCurrentText(str(getattr(self._teacher, "full_name", "") or ""))

    def _select_all_subjects(self) -> None:
        for widgets in self._subject_rule_widgets.values():
            widgets["subject"].setChecked(True)

    def _clear_all_subjects(self) -> None:
        for widgets in self._subject_rule_widgets.values():
            widgets["subject"].setChecked(False)

    def get_data(self) -> tuple[str, list[dict], list[tuple[int, int]]]:
        full_name = self.name_combo.currentText().strip()
        subject_rules: list[dict] = []

        for subject_id, widgets in self._subject_rule_widgets.items():
            if not widgets["subject"].isChecked():
                continue
            subject_rules.append(
                {
                    "subject_id": int(subject_id),
                    "can_lecture": widgets["can_lecture"].isChecked(),
                    "can_practice": widgets["can_practice"].isChecked(),
                    "can_computer_practice": widgets["can_computer_practice"].isChecked(),
                    "can_lab": widgets["can_lab"].isChecked(),
                }
            )

        # Получаем доступность из календаря
        availability = self.availability_calendar.get_availability()

        return full_name, subject_rules, availability


class TeachersPage(QWidget):
    calendarCreated = pyqtSignal(int)

    def __init__(self, teachers_repo, subjects_repo, calendar_repo):
        super().__init__()
        self._teachers_repo = teachers_repo
        self._subjects_repo = subjects_repo
        self._calendar_repo = calendar_repo

        self._current_calendar_id: Optional[int] = None
        self._all_rows: list[object] = []
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
        self.table.horizontalHeader().sectionClicked.connect(self._toggle_sort)
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
        self.search_edit.textChanged.connect(self._apply_filters)

        self._load_calendars()
        self.refresh()

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
        previous_calendar_id = self._current_calendar_id
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
            if previous_calendar_id is not None:
                idx = self.calendar_combo.findData(int(previous_calendar_id))
                if idx >= 0:
                    self.calendar_combo.setCurrentIndex(idx)
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
        self.calendarCreated.emit(int(calendar_id))

    def refresh_calendars(self, selected_calendar_id: Optional[int] = None) -> None:
        self._load_calendars()
        if selected_calendar_id is not None:
            self._select_calendar_by_id(int(selected_calendar_id))
        self.refresh()

    def _calendar_changed(self) -> None:
        value = self.calendar_combo.currentData()
        self._current_calendar_id = int(value) if value is not None else None
        self.refresh()

    def _add_teacher(self) -> None:
        dlg = TeacherEditDialog(
            self,
            subjects_repo=self._subjects_repo,
            calendar_repo=self._calendar_repo,
            teacher=None,
            selected_subject_ids=[],
            selected_subject_rules={},
            current_calendar_id=self._current_calendar_id,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        full_name, subject_rules, availability = dlg.get_data()

        if not full_name:
            QMessageBox.warning(self, "Ошибка", "ФИО не может быть пустым.")
            return

        try:
            existing_teacher = self._teachers_repo.get_by_full_name(full_name)
            if existing_teacher is not None:
                existing_rules = self._teachers_repo.get_teacher_subject_rules(
                    int(existing_teacher.id_teacher)
                )
                existing_subject_ids = set(existing_rules.keys())
                new_subject_ids = {int(item["subject_id"]) for item in subject_rules}
                missing_subject_ids = new_subject_ids - existing_subject_ids

                if missing_subject_ids:
                    answer = QMessageBox.question(
                        self,
                        "Преподаватель уже существует",
                        "Преподаватель с таким ФИО уже есть в базе.\n"
                        "Добавить новые дисциплины к существующему преподавателю?",
                    )
                    if answer != QMessageBox.StandardButton.Yes:
                        return

                    merged_rules = dict(existing_rules)
                    for item in subject_rules:
                        merged_rules[int(item["subject_id"])] = {
                            "can_lecture": bool(item.get("can_lecture", True)),
                            "can_practice": bool(item.get("can_practice", True)),
                            "can_computer_practice": bool(item.get("can_computer_practice", True)),
                            "can_lab": bool(item.get("can_lab", True)),
                        }

                    merged_subject_rules = [
                        {"subject_id": sid, **rules}
                        for sid, rules in merged_rules.items()
                    ]

                    self._teachers_repo.replace_teacher_subject_rules(
                        int(existing_teacher.id_teacher),
                        merged_subject_rules,
                    )

                    if self._current_calendar_id and availability:
                        all_slots = set()
                        for day in range(1, 7):
                            for pair in range(1, 9):
                                all_slots.add((day, pair))
                        available_slots = set(availability)
                        unavailable_slots = all_slots - available_slots
                        self._teachers_repo.replace_teacher_availability_grid(
                            teacher_id=int(existing_teacher.id_teacher),
                            calendar_id=int(self._current_calendar_id),
                            unavailable_cells=unavailable_slots,
                        )

                    self.refresh()
                    self._set_status(
                        f"К существующему преподавателю '{full_name}' добавлены новые дисциплины."
                    )
                    return

                QMessageBox.information(
                    self,
                    "Без изменений",
                    "Преподаватель с таким ФИО уже существует, и все выбранные дисциплины уже назначены.",
                )
                return

            teacher_id = self._teachers_repo.create(
                full_name=full_name,
                hard_max=6,
                soft_max=4,
                needs_method_day=True,
                commentary=None,
            )

            self._teachers_repo.replace_teacher_subject_rules(
                int(teacher_id),
                subject_rules,
            )

            # Сохраняем доступность преподавателя
            if self._current_calendar_id and availability:
                # Преобразуем список доступных слотов в набор недоступных
                all_slots = set()
                for day in range(1, 7):  # Пн-Сб
                    for pair in range(1, 9):  # 1-8 пар
                        all_slots.add((day, pair))
                
                available_slots = set(availability)
                unavailable_slots = all_slots - available_slots
                
                self._teachers_repo.replace_teacher_availability_grid(
                    teacher_id=int(teacher_id),
                    calendar_id=int(self._current_calendar_id),
                    unavailable_cells=unavailable_slots,
                )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось добавить преподавателя:\n{exc}",
            )
            return

        self.refresh()
        self._set_status("Преподаватель добавлен.")

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
        selected_subject_rules = self._teachers_repo.get_teacher_subject_rules(int(teacher_id))

        dlg = TeacherEditDialog(
            self,
            subjects_repo=self._subjects_repo,
            calendar_repo=self._calendar_repo,
            teacher=teacher,
            selected_subject_ids=selected_subject_ids,
            selected_subject_rules=selected_subject_rules,
            current_calendar_id=self._current_calendar_id,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        full_name, subject_rules, availability = dlg.get_data()

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
            self._teachers_repo.replace_teacher_subject_rules(
                int(teacher_id),
                subject_rules,
            )
            
            # Обновляем доступность преподавателя
            if self._current_calendar_id and availability:
                # Преобразуем список доступных слотов в набор недоступных
                all_slots = set()
                for day in range(1, 7):  # Пн-Сб
                    for pair in range(1, 9):  # 1-8 пар
                        all_slots.add((day, pair))
                
                available_slots = set(availability)
                unavailable_slots = all_slots - available_slots
                
                self._teachers_repo.replace_teacher_availability_grid(
                    teacher_id=int(teacher_id),
                    calendar_id=int(self._current_calendar_id),
                    unavailable_cells=unavailable_slots,
                )
                
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

    def refresh(self) -> None:
        try:
            self._all_rows = list(
                self._teachers_repo.list_with_subjects_and_days(self._current_calendar_id)
            )
        except Exception as exc:
            self.table.setRowCount(0)
            self._set_status(f"Не удалось загрузить преподавателей: {exc}", error=True)
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
            for teacher in rows:
                haystack = " ".join(
                    [
                        str(getattr(teacher, "id_teacher", "") or ""),
                        str(getattr(teacher, "full_name", "") or ""),
                        str(getattr(teacher, "working_days", "") or ""),
                        str(getattr(teacher, "subjects", "") or ""),
                    ]
                ).lower()
                if query in haystack:
                    filtered.append(teacher)
            rows = filtered

        if self._sort_column is not None and self._sort_order != 0:
            key_map = {
                0: lambda x: int(getattr(x, "id_teacher", 0) or 0),
                1: lambda x: str(getattr(x, "full_name", "") or "").lower(),
                2: lambda x: str(getattr(x, "working_days", "") or "").lower(),
                3: lambda x: str(getattr(x, "subjects", "") or "").lower(),
            }
            rows.sort(key=key_map[self._sort_column], reverse=self._sort_order < 0)

        self._update_header_labels()
        self._render_rows(rows)

    def _update_header_labels(self) -> None:
        base_headers = ["ID", "ФИО", "Рабочие дни", "Список дисциплин"]
        headers = []
        for idx, title in enumerate(base_headers):
            if self._sort_column == idx:
                if self._sort_order > 0:
                    headers.append(f"{title} ▲")
                elif self._sort_order < 0:
                    headers.append(f"{title} ▼")
                else:
                    headers.append(title)
            else:
                headers.append(title)
        self.table.setHorizontalHeaderLabels(headers)

    def _render_rows(self, rows: list[object]) -> None:
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
