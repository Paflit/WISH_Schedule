from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class AvailabilityCalendar(QWidget):

    DAYS = [
        ("Понедельник", 1),
        ("Вторник", 2),
        ("Среда", 3),
        ("Четверг", 4),
        ("Пятница", 5),
        ("Суббота", 6),
    ]

    def __init__(self, pairs_per_day: int = 8, include_saturday: bool = True):
        super().__init__()
        self._pairs_per_day = pairs_per_day
        self._include_saturday = include_saturday
        self._checkboxes = {}  # {(day, pair): QCheckBox}

        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        group_box = QGroupBox("Календарь доступности")
        group_layout = QVBoxLayout(group_box)

        # Кнопки быстрого выбора
        buttons_layout = QVBoxLayout()
        
        select_all_btn = QPushButton("Выбрать все")
        select_all_btn.clicked.connect(self._select_all)
        buttons_layout.addWidget(select_all_btn)

        clear_all_btn = QPushButton("Очистить все")
        clear_all_btn.clicked.connect(self._clear_all)
        buttons_layout.addWidget(clear_all_btn)

        group_layout.addLayout(buttons_layout)

        # Сетка чекбоксов
        grid = QGridLayout()
        grid.setSpacing(5)

        # Заголовок: номера пар
        grid.addWidget(QLabel(""), 0, 0)  # Пустая ячейка в углу
        for pair in range(1, self._pairs_per_day + 1):
            pair_btn = QPushButton(str(pair))
            pair_btn.setStyleSheet("font-weight: bold;")
            pair_btn.clicked.connect(lambda _=False, p=pair: self._invert_pair_column(p))
            grid.addWidget(pair_btn, 0, pair)

        # Строки: дни недели
        days_to_show = self.DAYS if self._include_saturday else self.DAYS[:5]
        
        for row_idx, (day_name, day_num) in enumerate(days_to_show, start=1):
            # Название дня
            day_btn = QPushButton(day_name)
            day_btn.setStyleSheet("font-weight: bold;")
            day_btn.clicked.connect(lambda _=False, d=day_num: self._invert_day_row(d))
            grid.addWidget(day_btn, row_idx, 0)

            # Чекбоксы для каждой пары
            for pair in range(1, self._pairs_per_day + 1):
                checkbox = QCheckBox()
                checkbox.setChecked(day_num <= 5)  # По умолчанию доступны все, кроме субботы
                grid.addWidget(checkbox, row_idx, pair)
                self._checkboxes[(day_num, pair)] = checkbox

        group_layout.addLayout(grid)
        root.addWidget(group_box)

    def _select_all(self) -> None:
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(True)

    def _clear_all(self) -> None:
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(False)

    def _invert_day_row(self, day: int) -> None:
        for (d, _pair), checkbox in self._checkboxes.items():
            if d == day:
                checkbox.setChecked(not checkbox.isChecked())

    def _invert_pair_column(self, pair: int) -> None:
        for (_day, p), checkbox in self._checkboxes.items():
            if p == pair:
                checkbox.setChecked(not checkbox.isChecked())

    def get_availability(self) -> list[tuple[int, int]]:
        available = []
        for (day, pair), checkbox in self._checkboxes.items():
            if checkbox.isChecked():
                available.append((day, pair))
        return available

    def set_availability(self, slots: list[tuple[int, int]]) -> None:
        # Сначала очищаем все
        self._clear_all()
        
        # Затем отмечаем указанные слоты
        for day, pair in slots:
            checkbox = self._checkboxes.get((day, pair))
            if checkbox:
                checkbox.setChecked(True)

    def get_availability_dict(self) -> dict[int, list[int]]:
        result = {}
        for (day, pair), checkbox in self._checkboxes.items():
            if checkbox.isChecked():
                if day not in result:
                    result[day] = []
                result[day].append(pair)
        return result
