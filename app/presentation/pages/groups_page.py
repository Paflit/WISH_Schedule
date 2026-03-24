from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
)


class GroupEditDialog(QDialog):
    """
    Диалог создания / редактирования учебной группы.

    Актуальная модель:
    - ID не вводится руками;
    - курс задаётся через dropdown;
    - количество студентов задаётся числом.
    """

    def __init__(self, parent, group: Optional[object] = None):
        super().__init__(parent)
        self._group = group

        self.setWindowTitle(
            "Редактирование группы" if group is not None else "Добавление группы"
        )
        self.resize(420, 200)

        root = QVBoxLayout(self)

        form = QFormLayout()
        root.addLayout(form)

        self.name_combo = QComboBox()
        self.name_combo.setEditable(True)
        self.name_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.name_combo.setPlaceholderText("Введите название группы")
        form.addRow("Название группы:", self.name_combo)

        self.course_combo = QComboBox()
        self.course_combo.addItem("—", None)
        for year in range(1, 6):
            self.course_combo.addItem(str(year), year)
        form.addRow("Курс:", self.course_combo)

        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 1000)
        self.quantity_spin.setValue(25)
        form.addRow("Количество студентов:", self.quantity_spin)

        hint = QLabel("ID группы создаётся автоматически базой данных.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #667085;")
        root.addWidget(hint)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        root.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self._fill()

    def _fill(self) -> None:
        if self._group is None:
            return

        self.name_combo.addItem(str(getattr(self._group, "group_name", "") or ""))
        self.name_combo.setCurrentText(str(getattr(self._group, "group_name", "") or ""))

        year = getattr(self._group, "year", None)
        idx = self.course_combo.findData(int(year) if year is not None else None)
        if idx >= 0:
            self.course_combo.setCurrentIndex(idx)

        self.quantity_spin.setValue(int(getattr(self._group, "quantity", 25) or 25))

    def get_data(self) -> tuple[str, Optional[int], int]:
        group_name = self.name_combo.currentText().strip()
        year = self.course_combo.currentData()
        quantity = int(self.quantity_spin.value())
        return group_name, year, quantity


class GroupsPage(QWidget):
    """
    Страница учебных групп.

    Показывает:
    - ID
    - название группы
    - курс
    - количество студентов

    Важно:
    - ID не вводится вручную;
    - курс задаётся через dropdown;
    - при сохранении курс реально уходит в БД.
    """

    def __init__(self, groups_repo):
        super().__init__()
        self._groups_repo = groups_repo

        root = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        root.addLayout(toolbar)

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
            ["ID", "Название группы", "Курс", "Количество"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 240)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 110)
        root.addWidget(self.table)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.add_btn.clicked.connect(self._add_group)
        self.edit_btn.clicked.connect(self._edit_group)
        self.delete_btn.clicked.connect(self._delete_group)
        self.refresh_btn.clicked.connect(self.refresh)

        self.refresh()

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            "color: #b42318;" if error else "color: #344054;"
        )

    def _selected_group_id(self) -> Optional[int]:
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

    def _add_group(self) -> None:
        dlg = GroupEditDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        group_name, year, quantity = dlg.get_data()

        if not group_name:
            QMessageBox.warning(self, "Ошибка", "Название группы не может быть пустым.")
            return

        if int(quantity) <= 0:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Количество студентов должно быть больше 0.",
            )
            return

        try:
            self._groups_repo.create(
                group_name=group_name,
                year=int(year) if year is not None else None,
                quantity=int(quantity),
                education_form="full-time",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось добавить группу:\n{exc}")
            return

        self.refresh()
        self._set_status(f"Группа '{group_name}' добавлена.")

    def _edit_group(self) -> None:
        group_id = self._selected_group_id()
        if group_id is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите группу.")
            return

        group = self._groups_repo.get_by_id(int(group_id))
        if group is None:
            QMessageBox.warning(self, "Ошибка", "Группа не найдена.")
            self.refresh()
            return

        dlg = GroupEditDialog(self, group=group)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        group_name, year, quantity = dlg.get_data()

        if not group_name:
            QMessageBox.warning(self, "Ошибка", "Название группы не может быть пустым.")
            return

        if int(quantity) <= 0:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Количество студентов должно быть больше 0.",
            )
            return

        try:
            self._groups_repo.update(
                id_group=int(group_id),
                group_name=group_name,
                year=int(year) if year is not None else None,
                quantity=int(quantity),
                education_form="full-time",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось сохранить изменения группы:\n{exc}",
            )
            return

        self.refresh()
        self._set_status(f"Группа '{group_name}' обновлена.")

    def _delete_group(self) -> None:
        group_id = self._selected_group_id()
        if group_id is None:
            QMessageBox.information(self, "Не выбрано", "Сначала выберите группу.")
            return

        group = self._groups_repo.get_by_id(int(group_id))
        group_name = getattr(group, "group_name", f"id={group_id}") if group else f"id={group_id}"

        answer = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Удалить группу '{group_name}'?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self._groups_repo.delete(int(group_id))
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить группу:\n{exc}")
            return

        self.refresh()
        self._set_status(f"Группа '{group_name}' удалена.")

    def refresh(self) -> None:
        try:
            rows = self._groups_repo.list_all()
        except Exception as exc:
            self.table.setRowCount(0)
            self._set_status(f"Не удалось загрузить группы: {exc}", error=True)
            return

        self.table.setRowCount(0)

        for row_idx, group in enumerate(rows):
            self.table.insertRow(row_idx)

            id_group = int(getattr(group, "id_group", 0))
            group_name = str(getattr(group, "group_name", "") or "")
            year = getattr(group, "year", None)
            quantity = int(getattr(group, "quantity", 0) or 0)

            id_item = QTableWidgetItem(str(id_group))
            id_item.setData(Qt.ItemDataRole.UserRole, id_group)

            name_item = QTableWidgetItem(group_name)
            year_item = QTableWidgetItem(str(year) if year is not None else "—")
            quantity_item = QTableWidgetItem(str(quantity))

            self.table.setItem(row_idx, 0, id_item)
            self.table.setItem(row_idx, 1, name_item)
            self.table.setItem(row_idx, 2, year_item)
            self.table.setItem(row_idx, 3, quantity_item)

        self._set_status(f"Загружено групп: {len(rows)}")