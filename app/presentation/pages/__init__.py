# app/presentation/pages/__init__.py
"""
Pages (экраны) приложения.

Каждый экран:
- отвечает только за UI
- не содержит бизнес-логики
- вызывает контроллеры / use-cases через DI

Структура:
- dictionaries_page.py
- generate_page.py
- schedule_page.py
- import_export_page.py

Важно:
Page ≠ Controller.
Page = визуальный слой.
Controller = связывает UI и application слой.
"""

__all__ = [
    "dictionaries_page",
    "generate_page",
    "schedule_page",
    "import_export_page",
]