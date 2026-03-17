from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QDialog,
    QFormLayout,
    QSpinBox,
    QDialogButtonBox,
)

from app.application.use_cases.apply_manual_edit import ApplyManualEditCommand


class EditEntryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование занятия")
        self.setMinimumWidth(420)

        layout = QFormLayout(self)

        self.slot_spin = QSpinBox()
        self.slot_spin.setMaximum(10**9)

        self.teacher_spin = QSpinBox()
        self.teacher_spin.setMaximum(10**9)

        self.room_spin = QSpinBox()
        self.room_spin.setMaximum(10**9)

        layout.addRow("Новый slot_id:", self.slot_spin)
        layout.addRow("Новый teacher_id:", self.teacher_spin)
        layout.addRow("Новый room_id:", self.room_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self):
        return (
            self.slot_spin.value() if self.slot_spin.value() != 0 else None,
            self.teacher_spin.value() if self.teacher_spin.value() != 0 else None,
            self.room_spin.value() if self.room_spin.value() != 0 else None,
        )


class EditorPage(QWidget):
    VIEW_GROUP = "group"
    VIEW_TEACHER = "teacher"
    VIEW_ROOM = "room"

    def __init__(self, container):
        super().__init__()
        self.container = container

        self.schedule_repo = container.schedule_repo
        self.apply_edit_uc = container.apply_manual_edit_uc

        self._current_variant = None

        self._init_ui()
        self._load_variants()

    def _init_ui(self):
        layout = QVBoxLayout()

        top = QHBoxLayout()

        top.addWidget(QLabel("Вариант:"))
        self.variants_combo = QComboBox()
        top.addWidget(self.variants_combo)

        top.addWidget(QLabel("Режим просмотра:"))
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItem("По группе", self.VIEW_GROUP)
        self.view_mode_combo.addItem("По преподавателю", self.VIEW_TEACHER)
        self.view_mode_combo.addItem("По аудитории", self.VIEW_ROOM)
        top.addWidget(self.view_mode_combo)

        top.addWidget(QLabel("Фильтр:"))
        self.entity_combo = QComboBox()
        top.addWidget(self.entity_combo)

        self.refresh_button = QPushButton("Обновить")
        self.edit_button = QPushButton("Редактировать выбранное")

        top.addWidget(self.refresh_button)
        top.addWidget(self.edit_button)

        layout.addLayout(top)

        self.info_label = QLabel("Выберите вариант и режим просмотра.")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.grid = QTableWidget()
        self.grid.setColumnCount(7)
        self.grid.setHorizontalHeaderLabels([
            "Пара/День", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"
        ])
        layout.addWidget(self.grid)

        self.setLayout(layout)

        self.refresh_button.clicked.connect(self._refresh_grid)
        self.variants_combo.currentIndexChanged.connect(self._on_variant_changed)
        self.view_mode_combo.currentIndexChanged.connect(self._rebuild_entity_filter)
        self.entity_combo.currentIndexChanged.connect(self._refresh_grid)
        self.edit_button.clicked.connect(self._edit_selected_entry)

    def _load_variants(self):
        try:
            variants = self.schedule_repo.list_variants()
            self.variants_combo.clear()

            for v in variants:
                self.variants_combo.addItem(
                    f"{v['name']} (score={v['objective_score']})",
                    userData=v["id_variant"],
                )

            if self.variants_combo.count() > 0:
                self._on_variant_changed()
            else:
                self.entity_combo.clear()
                self.grid.setRowCount(0)
                self.info_label.setText("Нет доступных вариантов.")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка загрузки вариантов", str(e))

    def _on_variant_changed(self):
        variant_id = self.variants_combo.currentData()
        if not variant_id:
            self._current_variant = None
            self.entity_combo.clear()
            self.grid.setRowCount(0)
            return

        try:
            self._current_variant = self.schedule_repo.get_variant(int(variant_id))
            self._rebuild_entity_filter()
        except Exception as e:
            self._current_variant = None
            QMessageBox.critical(self, "Ошибка загрузки варианта", str(e))

    def _rebuild_entity_filter(self):
        self.entity_combo.clear()

        if self._current_variant is None:
            return

        variant_id = int(self._current_variant.id_variant)
        mode = self.view_mode_combo.currentData()

        try:
            if mode == self.VIEW_GROUP:
                rows = self.schedule_repo.list_groups_for_variant(variant_id)
                for r in rows:
                    self.entity_combo.addItem(str(r.group_name), userData=int(r.group_id))

            elif mode == self.VIEW_TEACHER:
                rows = self.schedule_repo.list_teachers_for_variant(variant_id)
                for r in rows:
                    self.entity_combo.addItem(str(r.teacher_name), userData=int(r.teacher_id))

            else:
                rows = self.schedule_repo.list_rooms_for_variant(variant_id)
                for r in rows:
                    self.entity_combo.addItem(str(r.room_number), userData=int(r.room_id))

            self._refresh_grid()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка фильтра", str(e))

    def _load_filtered_entries(self):
        if self._current_variant is None:
            return [], ""

        variant_id = int(self._current_variant.id_variant)
        mode = self.view_mode_combo.currentData()
        entity_id = self.entity_combo.currentData()

        if not entity_id:
            return [], ""

        entity_id = int(entity_id)

        if mode == self.VIEW_GROUP:
            entries = self.schedule_repo.get_variant_entries_filtered(
                variant_id=variant_id,
                group_id=entity_id,
            )
            title = f"Группа: {self.entity_combo.currentText()}"

        elif mode == self.VIEW_TEACHER:
            entries = self.schedule_repo.get_variant_entries_filtered(
                variant_id=variant_id,
                teacher_id=entity_id,
            )
            title = f"Преподаватель: {self.entity_combo.currentText()}"

        else:
            entries = self.schedule_repo.get_variant_entries_filtered(
                variant_id=variant_id,
                room_id=entity_id,
            )
            title = f"Аудитория: {self.entity_combo.currentText()}"

        return entries, title

    def _entry_text(self, e) -> str:
        subject = str(getattr(e, "subject_name", "") or "")
        part = str(getattr(e, "part_type", "") or "")
        group = str(getattr(e, "group_name", "") or "")
        teacher = str(getattr(e, "teacher_name", "") or "")
        room = str(getattr(e, "room_number", "") or "")

        mode = self.view_mode_combo.currentData()

        if mode == self.VIEW_GROUP:
            return f"{subject} [{part}]\n{teacher}\nауд. {room}"
        if mode == self.VIEW_TEACHER:
            return f"{subject} [{part}]\n{group}\nауд. {room}"
        return f"{subject} [{part}]\n{group}\n{teacher}"

    def _refresh_grid(self):
        if self._current_variant is None:
            self.grid.setRowCount(0)
            return

        entries, title = self._load_filtered_entries()
        if not entries:
            self.grid.setRowCount(0)
            self.info_label.setText("Нет данных для отображения.")
            return

        self.info_label.setText(
            f"{title} | Вариант: {self._current_variant.name} | Записей: {len(entries)}"
        )

        cells: Dict[Tuple[int, int], List] = defaultdict(list)
        max_pair = 0

        for e in entries:
            day = int(getattr(e, "day_of_week", 0) or 0)
            pair = int(getattr(e, "pair_number", 0) or 0)
            if day <= 0 or pair <= 0:
                continue

            max_pair = max(max_pair, pair)
            cells[(day, pair)].append(e)

        self.grid.setRowCount(max_pair)

        for row in range(max_pair):
            self.grid.setItem(row, 0, QTableWidgetItem(str(row + 1)))

        for day in range(1, 7):
            for pair in range(1, max_pair + 1):
                items = cells.get((day, pair), [])
                if not items:
                    self.grid.setItem(pair - 1, day, QTableWidgetItem(""))
                    continue

                texts = [self._entry_text(e) for e in items]
                merged_text = "\n---\n".join(texts)

                item = QTableWidgetItem(merged_text)
                first = items[0]
                item.setData(Qt.ItemDataRole.UserRole, int(first.id_schedule))
                self.grid.setItem(pair - 1, day, item)

        self.grid.resizeColumnsToContents()
        self.grid.resizeRowsToContents()

    def _edit_selected_entry(self):
        variant_id = self.variants_combo.currentData()
        if not variant_id:
            return

        selected = self.grid.currentItem()
        if not selected:
            QMessageBox.warning(self, "Нет выбора", "Выберите ячейку с занятием.")
            return

        schedule_entry_id = selected.data(Qt.ItemDataRole.UserRole)
        if not schedule_entry_id:
            QMessageBox.warning(self, "Нет записи", "В этой ячейке нет занятия для редактирования.")
            return

        dialog = EditEntryDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        slot_id, teacher_id, room_id = dialog.get_values()

        try:
            cmd = ApplyManualEditCommand(
                variant_id=int(variant_id),
                schedule_entry_id=int(schedule_entry_id),
                new_slot_id=slot_id,
                new_teacher_id=teacher_id,
                new_room_id=room_id,
                lock_after_edit=True,
                edited_by="admin",
            )
            self.apply_edit_uc.execute(cmd)

            QMessageBox.information(self, "Успешно", "Изменения сохранены.")
            self._refresh_grid()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка редактирования", str(e))

    def set_variant(self, variant_id: int):
        for i in range(self.variants_combo.count()):
            if int(self.variants_combo.itemData(i)) == int(variant_id):
                self.variants_combo.setCurrentIndex(i)
                self._on_variant_changed()
                return