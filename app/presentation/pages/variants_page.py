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
    QLineEdit,
    QDialogButtonBox,
)

from app.application.use_cases.save_variant import SaveVariantCommand


class ApproveVariantDialog(QDialog):
    def __init__(self, current_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Утверждение варианта")
        self.setMinimumWidth(420)

        layout = QFormLayout(self)

        self.name_edit = QLineEdit()
        self.name_edit.setText(current_name)
        layout.addRow("Название варианта:", self.name_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> tuple[str]:
        return (self.name_edit.text().strip(),)


class VariantsPage(QWidget):
    def __init__(self, container, open_variant_callback=None):
        super().__init__()
        self.container = container
        self.open_variant_callback = open_variant_callback

        self.calendar_repo = container.calendar_repo
        self.schedule_repo = container.schedule_repo
        self.save_variant_uc = container.save_variant_uc

        self._init_ui()
        self._load_calendars()
        self.refresh()

    def _init_ui(self):
        layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        self.calendar_combo = QComboBox()
        self.btn_refresh = QPushButton("Обновить")
        self.btn_open = QPushButton("Открыть в просмотре")
        self.btn_approve = QPushButton("Утвердить / переименовать")

        top_layout.addWidget(QLabel("Семестр:"))
        top_layout.addWidget(self.calendar_combo)
        top_layout.addWidget(self.btn_refresh)
        top_layout.addWidget(self.btn_open)
        top_layout.addWidget(self.btn_approve)

        layout.addLayout(top_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "ID",
            "Название",
            "Score",
            "Статус",
            "Профиль",
        ])
        layout.addWidget(self.table)

        self.setLayout(layout)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_open.clicked.connect(self._open_selected)
        self.btn_approve.clicked.connect(self._approve_selected)
        self.calendar_combo.currentIndexChanged.connect(self.refresh)

    def _load_calendars(self):
        try:
            calendars = self.calendar_repo.list_all()
            self.calendar_combo.clear()

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
                    f"{c.academic_year} / Семестр {c.semester}",
                    userData=c.id_calendar
                )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def refresh(self):
        calendar_id = self.calendar_combo.currentData()
        if not calendar_id:
            self.table.setRowCount(0)
            return

        try:
            variants = self.schedule_repo.list_variants(calendar_id=calendar_id)
            self.table.setRowCount(len(variants))

            for row, v in enumerate(variants):
                self.table.setItem(row, 0, QTableWidgetItem(str(v["id_variant"])))
                self.table.setItem(row, 1, QTableWidgetItem(v["name"]))
                self.table.setItem(row, 2, QTableWidgetItem(str(v["objective_score"])))
                self.table.setItem(row, 3, QTableWidgetItem(v["status"]))
                self.table.setItem(row, 4, QTableWidgetItem(v.get("rule_profile_key", "")))

            self.table.resizeColumnsToContents()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка загрузки вариантов", str(e))

    def _selected_variant_id(self) -> int | None:
        selected = self.table.currentRow()
        if selected < 0:
            return None

        item = self.table.item(selected, 0)
        if not item:
            return None

        try:
            return int(item.text())
        except Exception:
            return None

    def _open_selected(self):
        variant_id = self._selected_variant_id()
        if variant_id is None:
            QMessageBox.warning(self, "Нет выбора", "Выберите вариант.")
            return

        if self.open_variant_callback is not None:
            self.open_variant_callback(variant_id)

    def _approve_selected(self):
        selected = self.table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Нет выбора", "Выберите вариант.")
            return

        variant_id_item = self.table.item(selected, 0)
        name_item = self.table.item(selected, 1)

        if not variant_id_item or not name_item:
            QMessageBox.warning(self, "Ошибка", "Не удалось прочитать выбранный вариант.")
            return

        variant_id = int(variant_id_item.text())
        current_name = name_item.text().strip()

        dialog = ApproveVariantDialog(current_name=current_name, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_name, = dialog.values()
        if not new_name:
            QMessageBox.warning(self, "Пустое название", "Введите название варианта.")
            return

        try:
            cmd = SaveVariantCommand(
                variant_id=variant_id,
                name=new_name,
                status="approved",
            )
            self.save_variant_uc.execute(cmd)
            QMessageBox.information(self, "Успешно", "Вариант утверждён.")
            self.refresh()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))