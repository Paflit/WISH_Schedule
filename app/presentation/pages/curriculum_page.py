from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QTableWidget, QTableWidgetItem,
    QMessageBox, QDialog, QFormLayout, QLineEdit,
    QSpinBox, QDialogButtonBox, QGridLayout, QGroupBox
)


@dataclass
class PlanDialogResult:
    group_id: int
    subject_name: str
    lec_h1: int; lec_h2: int
    pr_h1: int; pr_h2: int
    cpr_h1: int; cpr_h2: int
    lab_h1: int; lab_h2: int


class PlanEntryDialog(QDialog):
    """
    Диалог добавления/редактирования:
    - группа + дисциплина
    - сетка: 2 колонки (П1/П2) × 4 строки (лек/уч.практ/комп.практ/лаб)
    """

    def __init__(
        self,
        parent,
        *,
        title: str,
        groups: list,
        preset: PlanDialogResult | None = None,
        enable_h1: bool = True,
        enable_h2: bool = True,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(680)

        root = QVBoxLayout(self)

        form = QFormLayout()
        self.group_combo = QComboBox()
        for g in groups:
            self.group_combo.addItem(g.group_name, g.id_group)

        self.subject_edit = QLineEdit()
        self.subject_edit.setPlaceholderText("Например: Математика")

        form.addRow("Группа:", self.group_combo)
        form.addRow("Дисциплина:", self.subject_edit)
        root.addLayout(form)

        box = QGroupBox("Часы по полугодиям")
        grid = QGridLayout(box)

        def spin(disabled: bool = False):
            s = QSpinBox()
            s.setRange(0, 500)
            s.setEnabled(not disabled)
            return s

        grid.addWidget(QLabel(""), 0, 0)
        grid.addWidget(QLabel("Полугодие 1"), 0, 1)
        grid.addWidget(QLabel("Полугодие 2"), 0, 2)

        grid.addWidget(QLabel("Лекция"), 1, 0)
        self.lec_h1 = spin(disabled=not enable_h1)
        self.lec_h2 = spin(disabled=not enable_h2)
        grid.addWidget(self.lec_h1, 1, 1)
        grid.addWidget(self.lec_h2, 1, 2)

        grid.addWidget(QLabel("Учебная практика"), 2, 0)
        self.pr_h1 = spin(disabled=not enable_h1)
        self.pr_h2 = spin(disabled=not enable_h2)
        grid.addWidget(self.pr_h1, 2, 1)
        grid.addWidget(self.pr_h2, 2, 2)

        grid.addWidget(QLabel("Компьютерная практика"), 3, 0)
        self.cpr_h1 = spin(disabled=not enable_h1)
        self.cpr_h2 = spin(disabled=not enable_h2)
        grid.addWidget(self.cpr_h1, 3, 1)
        grid.addWidget(self.cpr_h2, 3, 2)

        grid.addWidget(QLabel("Лабораторная"), 4, 0)
        self.lab_h1 = spin(disabled=not enable_h1)
        self.lab_h2 = spin(disabled=not enable_h2)
        grid.addWidget(self.lab_h1, 4, 1)
        grid.addWidget(self.lab_h2, 4, 2)

        root.addWidget(box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if preset:
            idx = self.group_combo.findData(preset.group_id)
            if idx >= 0:
                self.group_combo.setCurrentIndex(idx)

            self.subject_edit.setText(preset.subject_name)

            self.lec_h1.setValue(preset.lec_h1); self.lec_h2.setValue(preset.lec_h2)
            self.pr_h1.setValue(preset.pr_h1); self.pr_h2.setValue(preset.pr_h2)
            self.cpr_h1.setValue(preset.cpr_h1); self.cpr_h2.setValue(preset.cpr_h2)
            self.lab_h1.setValue(preset.lab_h1); self.lab_h2.setValue(preset.lab_h2)

    def result_data(self) -> PlanDialogResult:
        return PlanDialogResult(
            group_id=int(self.group_combo.currentData()),
            subject_name=self.subject_edit.text().strip(),
            lec_h1=int(self.lec_h1.value()), lec_h2=int(self.lec_h2.value()),
            pr_h1=int(self.pr_h1.value()), pr_h2=int(self.pr_h2.value()),
            cpr_h1=int(self.cpr_h1.value()), cpr_h2=int(self.cpr_h2.value()),
            lab_h1=int(self.lab_h1.value()), lab_h2=int(self.lab_h2.value()),
        )


class CurriculumPage(QWidget):
    # columns
    COL_GROUP = 0
    COL_SUBJECT = 1
    COL_LEC_H1 = 2
    COL_LEC_H2 = 3
    COL_PR_H1 = 4
    COL_PR_H2 = 5
    COL_CPR_H1 = 6
    COL_CPR_H2 = 7
    COL_LAB_H1 = 8
    COL_LAB_H2 = 9
    COL_GID_HIDDEN = 10
    COL_SUBJ_HIDDEN = 11

    FILTER_H1 = "h1"
    FILTER_H2 = "h2"
    FILTER_BOTH = "both"

    def __init__(self, container):
        super().__init__()
        self.container = container
        self.calendar_repo = container.calendar_repo
        self.groups_repo = container.groups_repo
        self.curriculum_repo = container.curriculum_repo

        self._init_ui()
        self.refresh_table()

    def _init_ui(self):
        layout = QVBoxLayout()

        top = QHBoxLayout()
        top.addWidget(QLabel("Фильтр:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("Полугодие 1", self.FILTER_H1)
        self.filter_combo.addItem("Полугодие 2", self.FILTER_H2)
        self.filter_combo.addItem("Оба", self.FILTER_BOTH)
        self.filter_combo.setCurrentIndex(2)  # default: Оба
        top.addWidget(self.filter_combo)

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
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels([
            "Группа",
            "Дисциплина",
            "Лек П1", "Лек П2",
            "Уч.практ П1", "Уч.практ П2",
            "Комп.практ П1", "Комп.практ П2",
            "Лаб П1", "Лаб П2",
            "group_id (скрыто)",
            "subject_name (скрыто)",
        ])
        self.table.setColumnHidden(self.COL_GID_HIDDEN, True)
        self.table.setColumnHidden(self.COL_SUBJ_HIDDEN, True)

        layout.addWidget(self.table)
        self.setLayout(layout)

        self.btn_refresh.clicked.connect(self.refresh_table)
        self.filter_combo.currentIndexChanged.connect(self.refresh_table)

        self.btn_add.clicked.connect(self.add_dialog)
        self.btn_edit.clicked.connect(self.edit_dialog)
        self.btn_delete.clicked.connect(self.delete_selected)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_dialog())

    # ---------- calendar helpers ----------

    def _ensure_calendars_and_get_ids(self) -> tuple[int, int]:
        """
        Гарантирует, что в AcademicCalendar есть записи semester=1 и semester=2.
        Возвращает "актуальные" id_calendar: последние по id для 1 и 2.
        """
        with self.curriculum_repo._session_factory() as conn:
            conn.row_factory = lambda cur, row: {cur.description[i][0]: row[i] for i in range(len(row))}

            cur = conn.execute("SELECT * FROM AcademicCalendar ORDER BY id_calendar DESC")
            rows = cur.fetchall()

            if rows:
                # возьмём academic_year последней записи
                ay = rows[0].get("academic_year") or "2025/2026"
            else:
                ay = "2025/2026"

            sems = set()
            for r in rows:
                try:
                    sems.add(int(r.get("semester", 0)))
                except Exception:
                    pass

            if 1 not in sems:
                conn.execute(
                    "INSERT INTO AcademicCalendar(academic_year, semester, week_type_mode) VALUES (?, 1, 1)",
                    (ay,),
                )
            if 2 not in sems:
                conn.execute(
                    "INSERT INTO AcademicCalendar(academic_year, semester, week_type_mode) VALUES (?, 2, 1)",
                    (ay,),
                )
            conn.commit()

            # теперь возьмём последние id для каждого семестра
            cur = conn.execute(
                "SELECT id_calendar FROM AcademicCalendar WHERE semester=1 ORDER BY id_calendar DESC LIMIT 1"
            )
            h1 = int(cur.fetchone()["id_calendar"])

            cur = conn.execute(
                "SELECT id_calendar FROM AcademicCalendar WHERE semester=2 ORDER BY id_calendar DESC LIMIT 1"
            )
            h2 = int(cur.fetchone()["id_calendar"])

            return h1, h2

    # ---------- columns visibility ----------

    def _apply_column_visibility(self, mode: str):
        show_h1 = mode in (self.FILTER_H1, self.FILTER_BOTH)
        show_h2 = mode in (self.FILTER_H2, self.FILTER_BOTH)

        for col in [self.COL_LEC_H1, self.COL_PR_H1, self.COL_CPR_H1, self.COL_LAB_H1]:
            self.table.setColumnHidden(col, not show_h1)

        for col in [self.COL_LEC_H2, self.COL_PR_H2, self.COL_CPR_H2, self.COL_LAB_H2]:
            self.table.setColumnHidden(col, not show_h2)

    # ---------- filter rules ----------

    @staticmethod
    def _sum_half(row: dict, half: int) -> int:
        if half == 1:
            return int(row.get("lec_h1", 0)) + int(row.get("pr_h1", 0)) + int(row.get("cpr_h1", 0)) + int(row.get("lab_h1", 0))
        return int(row.get("lec_h2", 0)) + int(row.get("pr_h2", 0)) + int(row.get("cpr_h2", 0)) + int(row.get("lab_h2", 0))

    # ---------- main table refresh ----------

    def refresh_table(self):
        mode = str(self.filter_combo.currentData())
        self._apply_column_visibility(mode)

        # гарантируем существование календарей и берём id
        cal_h1_id, cal_h2_id = self._ensure_calendars_and_get_ids()

        try:
            # В режиме "Оба" — показываем ВСЕ дисциплины (включая полностью нулевые)
            # => используем НЕ filtered, а "полный" вывод по обоим календарям.
            if mode == self.FILTER_BOTH:
                rows = self.curriculum_repo.list_subject_bundle_table(cal_h1_id, cal_h2_id)

            # В режиме П1/П2 — показываем только дисциплины, где в выбранном полугодии НЕ все 0
            elif mode == self.FILTER_H1:
                rows = self.curriculum_repo.list_subject_bundle_table(cal_h1_id, cal_h2_id)
                rows = [r for r in rows if self._sum_half(r, 1) > 0]

            else:  # FILTER_H2
                rows = self.curriculum_repo.list_subject_bundle_table(cal_h1_id, cal_h2_id)
                rows = [r for r in rows if self._sum_half(r, 2) > 0]

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return

        self.table.setRowCount(len(rows))

        for i, r in enumerate(rows):
            self.table.setItem(i, self.COL_GROUP, QTableWidgetItem(r["group_name"]))
            self.table.setItem(i, self.COL_SUBJECT, QTableWidgetItem(r["subject_name"]))

            self.table.setItem(i, self.COL_LEC_H1, QTableWidgetItem(str(r.get("lec_h1", 0))))
            self.table.setItem(i, self.COL_LEC_H2, QTableWidgetItem(str(r.get("lec_h2", 0))))
            self.table.setItem(i, self.COL_PR_H1, QTableWidgetItem(str(r.get("pr_h1", 0))))
            self.table.setItem(i, self.COL_PR_H2, QTableWidgetItem(str(r.get("pr_h2", 0))))
            self.table.setItem(i, self.COL_CPR_H1, QTableWidgetItem(str(r.get("cpr_h1", 0))))
            self.table.setItem(i, self.COL_CPR_H2, QTableWidgetItem(str(r.get("cpr_h2", 0))))
            self.table.setItem(i, self.COL_LAB_H1, QTableWidgetItem(str(r.get("lab_h1", 0))))
            self.table.setItem(i, self.COL_LAB_H2, QTableWidgetItem(str(r.get("lab_h2", 0))))

            self.table.setItem(i, self.COL_GID_HIDDEN, QTableWidgetItem(str(r["group_id"])))
            self.table.setItem(i, self.COL_SUBJ_HIDDEN, QTableWidgetItem(str(r["subject_name"])))

        self._merge_group_cells()

    def _merge_group_cells(self):
        self.table.clearSpans()

        current = None
        start = 0
        count = 0

        for row in range(self.table.rowCount()):
            val = self.table.item(row, self.COL_GROUP).text() if self.table.item(row, self.COL_GROUP) else ""
            if val != current:
                if current is not None and count > 1:
                    self.table.setSpan(start, self.COL_GROUP, count, 1)
                    for r in range(start + 1, start + count):
                        self.table.setItem(r, self.COL_GROUP, QTableWidgetItem(""))
                current = val
                start = row
                count = 1
            else:
                count += 1

        if current is not None and count > 1:
            self.table.setSpan(start, self.COL_GROUP, count, 1)
            for r in range(start + 1, start + count):
                self.table.setItem(r, self.COL_GROUP, QTableWidgetItem(""))

    # ---------- selection helpers ----------

    def _selected_key(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        gid_item = self.table.item(row, self.COL_GID_HIDDEN)
        subj_item = self.table.item(row, self.COL_SUBJ_HIDDEN)
        if not gid_item or not subj_item:
            return None
        return int(gid_item.text()), subj_item.text()

    def _row_to_preset(self) -> PlanDialogResult | None:
        key = self._selected_key()
        if not key:
            return None
        gid, subject = key
        row = self.table.currentRow()

        def get_int(col: int) -> int:
            it = self.table.item(row, col)
            return int(it.text()) if it and it.text().strip() else 0

        return PlanDialogResult(
            group_id=gid,
            subject_name=subject,
            lec_h1=get_int(self.COL_LEC_H1), lec_h2=get_int(self.COL_LEC_H2),
            pr_h1=get_int(self.COL_PR_H1), pr_h2=get_int(self.COL_PR_H2),
            cpr_h1=get_int(self.COL_CPR_H1), cpr_h2=get_int(self.COL_CPR_H2),
            lab_h1=get_int(self.COL_LAB_H1), lab_h2=get_int(self.COL_LAB_H2),
        )

    def _validate_bundle(self, d: PlanDialogResult) -> tuple[bool, str]:
        if not d.subject_name:
            return False, "Название дисциплины не может быть пустым."
        total = (
            d.lec_h1 + d.lec_h2 +
            d.pr_h1 + d.pr_h2 +
            d.cpr_h1 + d.cpr_h2 +
            d.lab_h1 + d.lab_h2
        )
        if total <= 0:
            return False, "Укажи часы хотя бы в одном поле."
        return True, ""

    # ---------- actions ----------

    def add_dialog(self):
        groups = self.groups_repo.list_all()
        if not groups:
            QMessageBox.warning(self, "Нет групп", "Сначала добавь группы.")
            return

        mode = str(self.filter_combo.currentData())
        enable_h1 = mode in (self.FILTER_H1, self.FILTER_BOTH)
        enable_h2 = mode in (self.FILTER_H2, self.FILTER_BOTH)

        dlg = PlanEntryDialog(
            self,
            title="Добавить дисциплину",
            groups=groups,
            enable_h1=enable_h1,
            enable_h2=enable_h2,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.result_data()
        ok, msg = self._validate_bundle(data)
        if not ok:
            QMessageBox.warning(self, "Проверка", msg)
            return

        cal_h1_id, cal_h2_id = self._ensure_calendars_and_get_ids()

        try:
            self.curriculum_repo.upsert_subject_bundle(
                group_id=data.group_id,
                subject_name=data.subject_name,
                cal_h1_id=int(cal_h1_id) if enable_h1 else 0,
                cal_h2_id=int(cal_h2_id) if enable_h2 else 0,
                lec_h1=data.lec_h1 if enable_h1 else 0,
                lec_h2=data.lec_h2 if enable_h2 else 0,
                pr_h1=data.pr_h1 if enable_h1 else 0,
                pr_h2=data.pr_h2 if enable_h2 else 0,
                cpr_h1=data.cpr_h1 if enable_h1 else 0,
                cpr_h2=data.cpr_h2 if enable_h2 else 0,
                lab_h1=data.lab_h1 if enable_h1 else 0,
                lab_h2=data.lab_h2 if enable_h2 else 0,
            )
            self.refresh_table()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def edit_dialog(self):
        key = self._selected_key()
        if not key:
            QMessageBox.warning(self, "Нет выбора", "Выбери строку дисциплины.")
            return

        groups = self.groups_repo.list_all()
        preset = self._row_to_preset()

        mode = str(self.filter_combo.currentData())
        enable_h1 = mode in (self.FILTER_H1, self.FILTER_BOTH)
        enable_h2 = mode in (self.FILTER_H2, self.FILTER_BOTH)

        dlg = PlanEntryDialog(
            self,
            title="Редактировать дисциплину",
            groups=groups,
            preset=preset,
            enable_h1=enable_h1,
            enable_h2=enable_h2,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.result_data()
        ok, msg = self._validate_bundle(data)
        if not ok:
            QMessageBox.warning(self, "Проверка", msg)
            return

        cal_h1_id, cal_h2_id = self._ensure_calendars_and_get_ids()

        try:
            self.curriculum_repo.upsert_subject_bundle(
                group_id=data.group_id,
                subject_name=data.subject_name,
                cal_h1_id=int(cal_h1_id) if enable_h1 else 0,
                cal_h2_id=int(cal_h2_id) if enable_h2 else 0,
                lec_h1=data.lec_h1 if enable_h1 else 0,
                lec_h2=data.lec_h2 if enable_h2 else 0,
                pr_h1=data.pr_h1 if enable_h1 else 0,
                pr_h2=data.pr_h2 if enable_h2 else 0,
                cpr_h1=data.cpr_h1 if enable_h1 else 0,
                cpr_h2=data.cpr_h2 if enable_h2 else 0,
                lab_h1=data.lab_h1 if enable_h1 else 0,
                lab_h2=data.lab_h2 if enable_h2 else 0,
            )
            self.refresh_table()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def delete_selected(self):
        key = self._selected_key()
        if not key:
            QMessageBox.warning(self, "Нет выбора", "Выбери строку дисциплины.")
            return

        gid, subject = key
        try:
            self.curriculum_repo.delete_subject_bundle(group_id=int(gid), subject_name=subject)
            self.refresh_table()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))