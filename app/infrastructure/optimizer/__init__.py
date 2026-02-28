# app/infrastructure/optimizer/__init__.py
"""
Optimizer layer.

Здесь находятся компоненты, отвечающие за:
- построение списка Event из учебного плана (event_builder)
- построение и решение модели CP-SAT (solver)
- адаптер к domain.port ScheduleSolverPort

Этот слой:
- зависит от domain (models, rules, ports)
- может зависеть от внешних библиотек (OR-Tools)
- НЕ должен зависеть от Qt или GUI

Структура:
- event_builder.py      → превращает CurriculumSemesterPlan + WeeklyLoadPlan в Event[]
- cp_sat_solver.py      → реализация ScheduleSolverPort через OR-Tools
"""

__all__ = [
    "event_builder",
    "cp_sat_solver",
]