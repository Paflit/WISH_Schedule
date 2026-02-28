# app/presentation/widgets/table_view.py
"""
SimpleTableView

Универсальный табличный виджет для отображения списков (dict rows):
- принимает список колонок (ключ, заголовок)
- принимает данные как list[dict]
- умеет обновлять таблицу без знания бизнес-логики

Использование:
    columns = [("id", "ID"), ("name", "Название")]
    table.set_columns(columns)
    table.set_rows(rows)

Не зависит от репозиториев/use-cases.
"""

from __future__ import annotations

from typing import List, Dict, Tuple, Any, Optional

from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtCore import Qt


class SimpleTableView(QTableWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns: List[Tuple[str, str]] = []

        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

    # ---------------------------------------------------------

    def set_columns(self, columns: List[Tuple[str, str]]):
        """
        columns: [(key, header_title), ...]
        """
        self._columns = columns
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels([title for _, title in columns])

    # ---------------------------------------------------------

    def set_rows(self, rows: List[Dict[str, Any]]):
        """
        rows: list of dicts with keys from columns.
        """
        if not self._columns:
            raise ValueError("Columns are not set for SimpleTableView")

        self.setRowCount(len(rows))

        for row_idx, row in enumerate(rows):
            for col_idx, (key, _title) in enumerate(self._columns):
                value = row.get(key, "")
                item = QTableWidgetItem("" if value is None else str(value))

                # выравнивание чисел
                if isinstance(value, (int, float)):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                self.setItem(row_idx, col_idx, item)

    # ---------------------------------------------------------

    def get_selected_row(self) -> Optional[int]:
        """
        Возвращает индекс выбранной строки, или None
        """
        row = self.currentRow()
        return None if row < 0 else row