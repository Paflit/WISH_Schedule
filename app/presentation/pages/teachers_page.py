# app/presentation/pages/teachers_page.py
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
    QLabel, QComboBox, QHeaderView, QListWidget, QListWidgetItem,
    QCheckBox
)


DAY_NAMES = {
    1: "Пн",
    2: "Вт",
    3: "Ср",
    4: "Чт",
    5: "Пт",
    6: "Сб",
}


class SubjectRuleDialog(QDialog):
    """
    Диалог настройки типов занятий по одной дисциплине.
    По умолчанию всё включено.
    """

    def __init__(
        self,
        parent=None,
        *,
        subject_name: str,
        rules: dict | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Настройка: {subject_name}")
        self.setMinimumWidth(320)

        rules = rules or {
            "can_lecture": True,
            "can_practice": True,
            "can_computer_practice": True,
            "can_lab": True,
        }

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Дисциплина: {subject_name}"))

        self.cb_lecture = QCheckBox("Лекции")
        self.cb_practice = QCheckBox("Практики")
        self.cb_lab = QCheckBox("Лабораторные")

        self.cb_lecture.setChecked(bool(rules.get("can_lecture", True)))
        # computer_practice считаем частью практик
        self.cb_practice.setChecked(
            bool(rules.get("can_practice", True) or rules.get("can_computer_practice", True))
        )
        self.cb_lab.setChecked(bool(rules.get("can_lab", True)))

        layout.addWidget(self.cb_lecture)
        layout.addWidget(self.cb_practice)
        layout.addWidget(self.cb_lab)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        if not (self.cb_lecture.isChecked() or self.cb_practice.isChecked() or self.cb_lab.isChecked()):
            QMessageBox.warning(self, "Проверка", "Нужно оставить хотя бы один тип занятий.")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "can_lecture": self.cb_lecture.isChecked(),
            "can_practice": self.cb_practice.isChecked(),
            "can_computer_practice": self.cb_practice.isChecked(),
            "can_lab": self.cb_lab.isChecked(),
        }


class TeacherDialog(QDialog):
    """
    Окно добавления/редактирования преподавателя:
    - ФИО
    - поиск дисциплин
    - множественный выбор дисциплин
    - настройка типов занятий по дисциплине отдельным окном
    - календарь недоступности
    """

    def __init__(
        self,
        parent=None,
        *,
        title: str,
        subjects: list,
        calendar_id: int | None,
        name_value: str = "",
        subject_rules: dict[int, dict] | None = None,
        unavailable_cells: set[tuple[int, int]] | None = None,
        include_saturday: bool = True,
        pairs_per_day: int = 8,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(1050, 800)

        self._calendar_id = calendar_id
        self._include_saturday = include_saturday
        self._pairs_per_day = pairs_per_day
        self._subjects = subjects
        self._subject_rules = subject_rules or {}
        self._unavailable_cells = unavailable_cells or set()

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setText(name_value)
        form.addRow("ФИО:", self.name_edit)
        layout.addLayout(form)

        layout.addWidget(QLabel("Поиск дисциплины:"))
        self.subject_search = QLineEdit()
        self.subject_search.setPlaceholderText("Начни вводить название дисциплины...")
        layout.addWidget(self.subject_search)

        layout.addWidget(QLabel("Дисциплины преподавателя:"))
        self.subjects_list = QListWidget()
        self.subjects_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        for s in subjects:
            item = QListWidgetItem(s.subject_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if s.id_subject in self._subject_rules else Qt.CheckState.Unchecked
            )
            item.setData(Qt.ItemDataRole.UserRole, s.id_subject)
            item.setToolTip(self._rules_to_text(self._subject_rules.get(s.id_subject)))
            self.subjects_list.addItem(item)

        layout.addWidget(self.subjects_list)

        btn_row = QHBoxLayout()
        self.btn_configure_subject = QPushButton("Настроить выбранную дисциплину")
        btn_row.addWidget(self.btn_configure_subject)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.subject_search.textChanged.connect(self._apply_subject_filter)
        self.btn_configure_subject.clicked.connect(self._configure_selected_subject)
        self.subjects_list.itemDoubleClicked.connect(lambda _: self._configure_selected_subject())

        layout.addWidget(QLabel("Календарь: выбери недопустимые слоты для ведения занятий"))

        self.calendar_table = QTableWidget()
        days = [1, 2, 3, 4, 5] + ([6] if include_saturday else [])
        self._days = days

        self.calendar_table.setRowCount(pairs_per_day)
        self.calendar_table.setColumnCount(len(days))
        self.calendar_table.setHorizontalHeaderLabels([DAY_NAMES[d] for d in days])
        self.calendar_table.setVerticalHeaderLabels([f"{i} пара" for i in range(1, pairs_per_day + 1)])
        self.calendar_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.calendar_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        for row in range(pairs_per_day):
            for col, day in enumerate(days):
                item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.calendar_table.setItem(row, col, item)

                if day == 6:
                    self._mark_unavailable(row, col)

                if (day, row + 1) in self._unavailable_cells:
                    self._mark_unavailable(row, col)

        self.calendar_table.cellClicked.connect(self.toggle_calendar_cell)
        layout.addWidget(self.calendar_table)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _rules_to_text(self, rules: dict | None) -> str:
        if not rules:
            return "По умолчанию: лекции, практики, лабораторные"
        parts = []
        if rules.get("can_lecture"):
            parts.append("Л")
        if rules.get("can_practice") or rules.get("can_computer_practice"):
            parts.append("П")
        if rules.get("can_lab"):
            parts.append("Лаб")
        return ", ".join(parts) if parts else "Не выбрано"

    def _apply_subject_filter(self):
        query = self.subject_search.text().strip().lower()
        for i in range(self.subjects_list.count()):
            item = self.subjects_list.item(i)
            self.subjects_list.setRowHidden(i, query not in item.text().lower())

    def _configure_selected_subject(self):
        item = self.subjects_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Нет выбора", "Выбери дисциплину из списка.")
            return

        subject_id = int(item.data(Qt.ItemDataRole.UserRole))
        subject_name = item.text()

        current_rules = self._subject_rules.get(
            subject_id,
            {
                "can_lecture": True,
                "can_practice": True,
                "can_computer_practice": True,
                "can_lab": True,
            },
        )

        dlg = SubjectRuleDialog(
            self,
            subject_name=subject_name,
            rules=current_rules,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._subject_rules[subject_id] = dlg.values()
        item.setCheckState(Qt.CheckState.Checked)
        item.setToolTip(self._rules_to_text(self._subject_rules[subject_id]))

    def _mark_unavailable(self, row: int, col: int):
        item = self.calendar_table.item(row, col)
        if item:
            item.setText("X")
            item.setBackground(Qt.GlobalColor.lightGray)

    def _mark_available(self, row: int, col: int):
        item = self.calendar_table.item(row, col)
        if item:
            item.setText("")
            item.setBackground(Qt.GlobalColor.white)

    def toggle_calendar_cell(self, row: int, col: int):
        item = self.calendar_table.item(row, col)
        if not item:
            return
        if item.text() == "X":
            self._mark_available(row, col)
        else:
            self._mark_unavailable(row, col)

    def _on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Проверка", "ФИО не может быть пустым.")
            return

        selected_any = False
        for i in range(self.subjects_list.count()):
            item = self.subjects_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_any = True
                subject_id = int(item.data(Qt.ItemDataRole.UserRole))
                if subject_id not in self._subject_rules:
                    self._subject_rules[subject_id] = {
                        "can_lecture": True,
                        "can_practice": True,
                        "can_computer_practice": True,
                        "can_lab": True,
                    }

        if not selected_any:
            QMessageBox.warning(self, "Проверка", "Выбери хотя бы одну дисциплину.")
            return

        self.accept()

    def values(self):
        name = self.name_edit.text().strip()

        subject_rules = []
        for i in range(self.subjects_list.count()):
            item = self.subjects_list.item(i)
            if item.checkState() != Qt.CheckState.Checked:
                continue

            subject_id = int(item.data(Qt.ItemDataRole.UserRole))
            rules = self._subject_rules.get(
                subject_id,
                {
                    "can_lecture": True,
                    "can_practice": True,
                    "can_computer_practice": True,
                    "can_lab": True,
                },
            )

            subject_rules.append({
                "subject_id": subject_id,
                "can_lecture": bool(rules.get("can_lecture", True)),
                "can_practice": bool(rules.get("can_practice", True)),
                "can_computer_practice": bool(rules.get("can_computer_practice", True)),
                "can_lab": bool(rules.get("can_lab", True)),
            })

        unavailable = set()
        for row in range(self._pairs_per_day):
            for col, day in enumerate(self._days):
                item = self.calendar_table.item(row, col)
                if item and item.text() == "X":
                    unavailable.add((day, row + 1))

        return name, subject_rules, unavailable


class TeachersPage(QWidget):
    def __init__(self, container):
        super().__init__()
        self.container = container
        self.teachers_repo = container.teachers_repo
        self.calendar_repo = container.calendar_repo
        self.curriculum_repo = container.curriculum_repo

        self._init_ui()
        self._load_calendars()
        self.refresh()

    def _init_ui(self):
        layout = QVBoxLayout()

        top = QHBoxLayout()

        top.addWidget(QLabel("Календарь:"))
        self.calendar_combo = QComboBox()
        top.addWidget(self.calendar_combo)

        self.btn_refresh = QPushButton("Обновить")
        self.btn_add = QPushButton("Добавить")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_delete = QPushButton("Удалить")

        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_delete)
        top.addStretch()

        layout.addLayout(top)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["ID", "ФИО", "Список дисциплин"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.table)
        self.setLayout(layout)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_add.clicked.connect(self.add_teacher)
        self.btn_edit.clicked.connect(self.edit_teacher)
        self.btn_delete.clicked.connect(self.delete_teacher)
        self.calendar_combo.currentIndexChanged.connect(self.refresh)

    def _load_calendars(self):
        self.calendar_combo.blockSignals(True)
        try:
            current_id = self.calendar_combo.currentData()
            self.calendar_combo.clear()

            calendars = self.calendar_repo.list_all()
            for c in calendars:
                label = f"{getattr(c, 'academic_year', '—')} / семестр {getattr(c, 'semester', '—')}"
                self.calendar_combo.addItem(label, getattr(c, "id_calendar", None))

            if current_id is not None:
                idx = self.calendar_combo.findData(current_id)
                if idx >= 0:
                    self.calendar_combo.setCurrentIndex(idx)
        finally:
            self.calendar_combo.blockSignals(False)

    def _get_subjects_from_curriculum(self):
        with self.curriculum_repo._session_factory() as conn:
            conn.row_factory = lambda cur, row: {cur.description[i][0]: row[i] for i in range(len(row))}
            cur = conn.execute(
                """
                SELECT DISTINCT s.id_subject, s.subject_name
                FROM CurriculumItems ci
                JOIN Subjects s ON s.id_subject = ci.subject_id
                ORDER BY s.subject_name
                """
            )
            rows = cur.fetchall()

        class SubjectObj:
            def __init__(self, id_subject, subject_name):
                self.id_subject = id_subject
                self.subject_name = subject_name

        return [SubjectObj(r["id_subject"], r["subject_name"]) for r in rows]

    def refresh(self):
        try:
            teachers = self.teachers_repo.list_all()
            subjects = self._get_subjects_from_curriculum()
            subject_map = {s.id_subject: s.subject_name for s in subjects}

            self.table.setRowCount(len(teachers))

            for row, t in enumerate(teachers):
                rules = self.teachers_repo.get_teacher_subject_rules(t.id_teacher)

                subject_lines = []
                for sid, rule in rules.items():
                    if sid not in subject_map:
                        continue
                    parts = []
                    if rule.get("can_lecture"):
                        parts.append("Л")
                    if rule.get("can_practice") or rule.get("can_computer_practice"):
                        parts.append("П")
                    if rule.get("can_lab"):
                        parts.append("Лаб")
                    suffix = f" [{', '.join(parts)}]" if parts else ""
                    subject_lines.append(f"{subject_map[sid]}{suffix}")

                subjects_text = "[\n" + ",\n".join(subject_lines) + "\n]" if subject_lines else "[]"

                self.table.setItem(row, 0, QTableWidgetItem(str(t.id_teacher)))
                self.table.setItem(row, 1, QTableWidgetItem(t.full_name))
                self.table.setItem(row, 2, QTableWidgetItem(subjects_text))

            self.table.resizeRowsToContents()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return int(item.text()) if item else None

    def add_teacher(self):
        try:
            subjects = self._get_subjects_from_curriculum()
            calendar_id = self.calendar_combo.currentData()

            dlg = TeacherDialog(
                self,
                title="Добавить преподавателя",
                subjects=subjects,
                calendar_id=calendar_id,
                include_saturday=True,
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            name, subject_rules, unavailable = dlg.values()

            teacher_id = self.teachers_repo.create(full_name=name, commentary=None)
            self.teachers_repo.replace_teacher_subject_rules(teacher_id, subject_rules)

            if calendar_id:
                self.teachers_repo.replace_teacher_availability_grid(
                    teacher_id=teacher_id,
                    calendar_id=int(calendar_id),
                    unavailable_cells=unavailable,
                )

            self.refresh()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def edit_teacher(self):
        try:
            teacher_id = self._selected_id()
            if teacher_id is None:
                QMessageBox.warning(self, "Нет выбора", "Выбери преподавателя.")
                return

            row = self.table.currentRow()
            current_name = self.table.item(row, 1).text() if self.table.item(row, 1) else ""

            subjects = self._get_subjects_from_curriculum()
            calendar_id = self.calendar_combo.currentData()

            subject_rules = self.teachers_repo.get_teacher_subject_rules(teacher_id)
            unavailable = set()
            if calendar_id:
                unavailable = self.teachers_repo.get_teacher_unavailable_slots(
                    teacher_id=teacher_id,
                    calendar_id=int(calendar_id),
                )

            dlg = TeacherDialog(
                self,
                title="Редактировать преподавателя",
                subjects=subjects,
                calendar_id=calendar_id,
                name_value=current_name,
                subject_rules=subject_rules,
                unavailable_cells=unavailable,
                include_saturday=True,
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            name, subject_rules, unavailable = dlg.values()

            self.teachers_repo.update(
                id_teacher=teacher_id,
                full_name=name,
                hard_max=6,
                soft_max=4,
                needs_method_day=True,
                commentary=None,
            )
            self.teachers_repo.replace_teacher_subject_rules(teacher_id, subject_rules)

            if calendar_id:
                self.teachers_repo.replace_teacher_availability_grid(
                    teacher_id=teacher_id,
                    calendar_id=int(calendar_id),
                    unavailable_cells=unavailable,
                )

            self.refresh()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def delete_teacher(self):
        try:
            teacher_id = self._selected_id()
            if teacher_id is None:
                QMessageBox.warning(self, "Нет выбора", "Выбери преподавателя.")
                return

            self.teachers_repo.delete(teacher_id)
            self.refresh()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))