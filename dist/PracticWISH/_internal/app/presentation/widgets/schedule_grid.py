# app/presentation/widgets/schedule_grid.py
"""
ScheduleGridWidget

Универсальный виджет сетки расписания:
- строки = пары (1..N)
- столбцы = дни недели (Пн..Сб)
- ячейки содержат текст + schedule_entry_id
- поддерживает выбор ячейки
- отдаёт сигнал cell_selected(schedule_entry_id)

Не знает про репозитории и use-cases.
Работает только с данными, переданными извне.

Используется:
- EditorPage
- (в будущем) SchedulePage
"""

from __future__ import annotations

from typing import Dict, Tuple, Optional

from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtCore import pyqtSignal, Qt


# Qt.UserRole = 32
USER_ROLE = 32


class ScheduleGridWidget(QTableWidget):

    cell_selected = pyqtSignal(int)  # schedule_entry_id

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(7)
        self.setHorizontalHeaderLabels(
            ["Пара", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]
        )

        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        self.itemSelectionChanged.connect(self._on_selection_changed)

    # ---------------------------------------------------------

    def set_schedule(
        self,
        max_pair: int,
        grid_map: Dict[Tuple[int, int], Dict],
    ):
        """
        grid_map:
            key = (day_of_week, pair_number)
            value = {
                "text": str,
                "schedule_entry_id": int | None,
                "locked": bool
            }
        """

        self.clearContents()
        self.setRowCount(max_pair)

        for pair in range(1, max_pair + 1):
            self.setItem(pair - 1, 0, QTableWidgetItem(str(pair)))

            for day in range(1, 7):
                cell_data = grid_map.get((day, pair))
                item = QTableWidgetItem()

                if cell_data:
                    item.setText(cell_data.get("text", ""))

                    entry_id = cell_data.get("schedule_entry_id")
                    if entry_id:
                        item.setData(USER_ROLE, entry_id)

                    if cell_data.get("locked"):
                        # подсветка locked-занятий
                        item.setBackground(Qt.GlobalColor.lightGray)

                self.setItem(pair - 1, day, item)

    # ---------------------------------------------------------

    def _on_selection_changed(self):
        selected = self.currentItem()
        if not selected:
            return

        entry_id = selected.data(USER_ROLE)
        if entry_id:
            self.cell_selected.emit(int(entry_id))