# app/presentation/widgets/__init__.py
"""
Reusable UI widgets.

Назначение:
- вынести переиспользуемые компоненты
- уменьшить дублирование кода в pages
- упростить поддержку

Планируемые виджеты:
- schedule_grid_widget.py      → универсальная сетка расписания
- variant_selector_widget.py   → выбор варианта
- loading_overlay.py           → индикатор загрузки
- confirm_dialog.py            → диалог подтверждения
- profile_selector_widget.py   → выбор профиля правил

Widgets:
- не содержат бизнес-логики
- не знают про use-cases
- принимают данные и отображают их
"""

__all__ = [
    # "schedule_grid_widget",
    # "variant_selector_widget",
    # "loading_overlay",
    # "confirm_dialog",
    # "profile_selector_widget",
]