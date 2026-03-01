# app/application/use_cases/__init__.py
"""
Use-Cases (Application слой).

Здесь находятся сценарии работы системы.
Каждый use-case — это один законченный бизнес-сценарий,
который координирует:
    - репозитории (через domain ports)
    - доменные правила
    - оптимизатор
    - импорт/экспорт
    - сохранение изменений

Use-case НЕ содержит:
    - Qt-кода
    - SQL-запросов
    - конкретных ORM-моделей
    - прямой работы с OR-Tools

Примеры:
    - ImportDataUseCase
    - ExportDataUseCase
    - GenerateScheduleUseCase
    - SaveVariantUseCase
    - ApplyManualEditUseCase
"""

__all__ = [
    "import_data",
    "export_data",
    "generate_schedule",
    "save_variant",
    "apply_manual_edit",
]