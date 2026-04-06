from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
)
from PyQt6.QtCore import Qt


class MetricValue(QLabel):
    def __init__(self, text: str = ""):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                padding: 8px;
            }
        """)


class MetricLabel(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #555;
            }
        """)


class MetricsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()


    def _init_ui(self):
        layout = QVBoxLayout()

        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)

        grid = QGridLayout()

        # Метрики
        self.score_value = MetricValue("-")
        self.violations_value = MetricValue("-")
        self.avg_students_value = MetricValue("-")
        self.avg_teachers_value = MetricValue("-")
        self.gaps_value = MetricValue("-")
        self.soft_over_value = MetricValue("-")

        grid.addWidget(self.score_value, 0, 0)
        grid.addWidget(self.violations_value, 0, 1)
        grid.addWidget(self.avg_students_value, 0, 2)
        grid.addWidget(self.avg_teachers_value, 0, 3)
        grid.addWidget(self.gaps_value, 0, 4)
        grid.addWidget(self.soft_over_value, 0, 5)

        grid.addWidget(MetricLabel("Score"), 1, 0)
        grid.addWidget(MetricLabel("Soft нарушений"), 1, 1)
        grid.addWidget(MetricLabel("Средн. нагрузка студентов"), 1, 2)
        grid.addWidget(MetricLabel("Средн. нагрузка преподавателей"), 1, 3)
        grid.addWidget(MetricLabel("Окна"), 1, 4)
        grid.addWidget(MetricLabel("Превышения soft"), 1, 5)

        frame.setLayout(grid)
        layout.addWidget(frame)

        self.setLayout(layout)


    def set_metrics(
        self,
        metrics: Optional[dict] = None,
        score: Optional[int] = None,
        soft_violations: Optional[int] = None,
        avg_students_load: Optional[float] = None,
        avg_teachers_load: Optional[float] = None,
        total_gaps: Optional[int] = None,
        soft_overloads: Optional[int] = None,
    ):

        data = dict(metrics or {})

        if score is None:
            score = data.get("score")
        if score is None:
            score = data.get("objective_score")
        if score is None:
            score = data.get("best_objective_score")

        if soft_violations is None:
            soft_violations = data.get("soft_violations")
        if soft_violations is None:
            soft_violations = data.get("entries_count")
        if soft_violations is None:
            soft_violations = data.get("variants_count")

        if avg_students_load is None:
            avg_students_load = data.get("avg_students_load")
        if avg_students_load is None:
            avg_students_load = data.get("groups_count")
        if avg_students_load is None:
            avg_students_load = data.get("best_entries_count")

        if avg_teachers_load is None:
            avg_teachers_load = data.get("avg_teachers_load")
        if avg_teachers_load is None:
            avg_teachers_load = data.get("teachers_count")
        if avg_teachers_load is None:
            avg_teachers_load = data.get("best_variant_id")

        if total_gaps is None:
            total_gaps = data.get("total_gaps")
        if total_gaps is None:
            total_gaps = data.get("rooms_count")

        if soft_overloads is None:
            soft_overloads = data.get("soft_overloads")
        if soft_overloads is None:
            soft_overloads = data.get("locked_entries")

        self.score_value.setText(str(score) if score is not None else "-")
        self.violations_value.setText(str(soft_violations) if soft_violations is not None else "-")

        self.avg_students_value.setText(
            f"{avg_students_load:.2f}" if avg_students_load is not None else "-"
        )
        self.avg_teachers_value.setText(
            f"{avg_teachers_load:.2f}" if avg_teachers_load is not None else "-"
        )

        self.gaps_value.setText(str(total_gaps) if total_gaps is not None else "-")
        self.soft_over_value.setText(str(soft_overloads) if soft_overloads is not None else "-")
