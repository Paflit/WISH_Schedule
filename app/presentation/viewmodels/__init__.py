# app/presentation/viewmodels/__init__.py
"""
ViewModels layer (MVVM для Qt).

Назначение:
- отделить UI (pages) от application/use-cases
- хранить состояние экрана
- вызывать use-cases
- обрабатывать ошибки
- отдавать "готовые данные" в представление

Почему это важно:
Сейчас pages напрямую используют repo/use-cases.
ViewModel позволит:
- упростить тестирование
- убрать бизнес-логику из QWidget
- перейти к более чистой архитектуре

Структура:
- generate_viewmodel.py
- variants_viewmodel.py
- editor_viewmodel.py
- calendar_viewmodel.py
- curriculum_viewmodel.py
"""

__all__ = [
    "generate_viewmodel",
    "variants_viewmodel",
    "editor_viewmodel",
    "calendar_viewmodel",
    "curriculum_viewmodel",
]