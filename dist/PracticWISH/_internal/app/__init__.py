# app/__init__.py
"""
Корневой пакет приложения PracticWISH.

Назначение:
- объединяет все слои архитектуры:
    - presentation (GUI, Qt, ViewModel)
    - application (use-cases)
    - domain (бизнес-логика, правила, модели)
    - infrastructure (БД, импорт/экспорт, оптимизатор)

Этот файл может:
- хранить версию приложения
- предоставлять базовые метаданные
- не должен содержать бизнес-логики
"""

from __future__ import annotations

__all__ = [
    "__version__",
    "__app_name__",
]

__version__ = "0.1.0"
__app_name__ = "PracticWISH — Schedule Optimizer"