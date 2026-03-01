# app/presentation/pages/editor_page.py
"""
EditorPage

Экран ручной корректировки расписания.

Функции:
- выбрать вариант расписания
- отобразить его сеткой (день/пара)
- при клике на занятие открыть "Edit dialog":
    * сменить слот
    * сменить аудиторию
    * сменить преподавателя
    * закрепить (lock) запись
- сохранять изменения через ApplyManualEditUseCase
- после правок обновлять отображение

MVP:
- список вариантов (combo)
- таблица расписания (grid)
- кнопка "Обновить"
- кнопка "Снять lock" / "Закрепить" (в диалоге)

Важно:
- все изменения проходят через use-case (application слой)
"""

from __future__ import annotations

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
    """
    Диалог редактирования одной записи расписания.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование занятия")
        self.setMinimumWidth(400)

        self.new_slot_id = None
        self.new_teacher_id = None
        self.new_room_id = None
        self.lock_after_edit = True

        layout = QFormLayout()

        self.slot_spin = QSpinBox()
        self.slot_spin.setMaximum(10**9)

        self.teacher_spin = QSpinBox()
        self.teacher_spin.setMaximum(10**9)

        self.room_spin = QSpinBox()
        self.room_spin.setMaximum(10**9)

        layout.addRow("Новый slot_id:", self.slot_spin)
        layout.addRow("Новый teacher_id:", self.teacher_spin)
        layout.addRow("Новый room_id:", self.room_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addRow(buttons)
        self.setLayout(layout)

    def get_values(self):
        return (
            self.slot_spin.value() if self.slot_spin.value() != 0 else None,
            self.teacher_spin.value() if self.teacher_spin.value() != 0 else None,
            self.room_spin.value() if self.room_spin.value() != 0 else None,
        )


class EditorPage(QWidget):

    def __init__(self, container):
        super().__init__()
        self.container = container

        self.schedule_repo = container.schedule_repo
        self.apply_edit_uc = container.apply_manual_edit_uc

        self._init_ui()
        self._load_variants()

    # ---------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        self.variants_combo = QComboBox()
        self.refresh_button = QPushButton("Обновить")
        self.edit_button = QPushButton("Редактировать выбранное")

        top_layout.addWidget(QLabel("Вариант:"))
        top_layout.addWidget(self.variants_combo)
        top_layout.addWidget(self.refresh_button)
        top_layout.addWidget(self.edit_button)

        layout.addLayout(top_layout)

        # Grid table
        self.grid = QTableWidget()
        self.grid.setColumnCount(7)
        self.grid.setHorizontalHeaderLabels([
            "Пара/День", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"
        ])

        layout.addWidget(self.grid)
        self.setLayout(layout)

        # Signals
        self.refresh_button.clicked.connect(self._refresh_grid)
        self.variants_combo.currentIndexChanged.connect(self._refresh_grid)
        self.edit_button.clicked.connect(self._edit_selected_entry)

    # ---------------------------------------------------------

    def _load_variants(self):
        """
        Загружает список вариантов расписания из репозитория.
        """
        try:
            variants = self.schedule_repo.list_variants()

            self.variants_combo.clear()
            for v in variants:
                self.variants_combo.addItem(
                    f"{v['name']} (score={v['objective_score']})",
                    userData=v["id_variant"]
                )

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    # ---------------------------------------------------------

    def _refresh_grid(self):
        """
        Отображает расписание выбранного варианта.
        """
        variant_id = self.variants_combo.currentData()
        if not variant_id:
            return

        try:
            variant = self.schedule_repo.get_variant_dto(variant_id)

            # группируем по (day_of_week, pair)
            cells = {}
            max_pair = 0

            for e in variant.entries:
                key = (e.day_of_week, e.pair_number)
                max_pair = max(max_pair, e.pair_number)

                text = f"{e.group_name}\n{e.subject_name}\n{e.teacher_name}\n{e.room_number}"
                cells.setdefault(key, []).append((e, text))

            self.grid.setRowCount(max_pair)

            for pair in range(1, max_pair + 1):
                self.grid.setItem(pair - 1, 0, QTableWidgetItem(str(pair)))

                for day in range(1, 7):
                    items = cells.get((day, pair), [])
                    if not items:
                        self.grid.setItem(pair - 1, day, QTableWidgetItem(""))
                        continue

                    # если несколько занятий в одной ячейке (например разные группы) — объединяем
                    merged = "\n---\n".join([t for (_, t) in items])
                    cell_item = QTableWidgetItem(merged)

                    # сохраняем id первой записи как "выбранную"
                    cell_item.setData(32, items[0][0].event_id)  # Qt.UserRole = 32

                    self.grid.setItem(pair - 1, day, cell_item)

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    # ---------------------------------------------------------

    def _edit_selected_entry(self):
        """
        Открывает диалог редактирования для выделенной ячейки.
        """
        variant_id = self.variants_combo.currentData()
        if not variant_id:
            return

        selected = self.grid.currentItem()
        if not selected:
            QMessageBox.warning(self, "Нет выбора", "Выберите ячейку с занятием.")
            return

        schedule_entry_id = selected.data(32)
        if not schedule_entry_id:
            QMessageBox.warning(self, "Нет записи", "В этой ячейке нет занятия для редактирования.")
            return

        dialog = EditEntryDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        slot_id, teacher_id, room_id = dialog.get_values()

        try:
            cmd = ApplyManualEditCommand(
                variant_id=variant_id,
                schedule_entry_id=schedule_entry_id,
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