# app/infrastructure/__init__.py
"""
Infrastructure слой.

Назначение:
- Реализация портов (из app.domain.ports)
- Работа с внешними системами:
    - БД (SQLite)
    - Excel (импорт/экспорт)
    - Оптимизатор (OR-Tools)
- Любая техническая интеграция

ВАЖНО:
- infrastructure может зависеть от domain
- domain НЕ должен зависеть от infrastructure
- presentation НЕ должен напрямую использовать infrastructure
  (только через use-cases и DI)

Подмодули:
- db            → реализация репозиториев (SQLite)
- import_export → Excel/CSV
- optimizer     → CP-SAT solver + event builder
"""

__all__ = [
    "db",
    "import_export",
    "optimizer",
]