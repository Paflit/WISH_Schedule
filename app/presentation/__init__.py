# app/presentation/__init__.py
"""
Presentation layer (GUI).

Назначение:
- Отображение данных пользователю
- Обработка пользовательских действий
- Вызов use-cases через DI-контейнер
- Отображение ошибок (DomainError → message box)

Важно:
- Presentation НЕ должен знать про SQLite
- Presentation НЕ должен напрямую вызывать solver
- Только через application/use-cases

Структура:
- main_window.py
- views/          → экраны (справочники, генерация, расписание)
- widgets/        → переиспользуемые UI-компоненты
- controllers/    → связывает UI и use-cases
"""

__all__ = [
    "main_window",
    "views",
    "widgets",
    "controllers",
]