# app/application/__init__.py
"""
Application слой (Use-Cases).

Назначение слоя:
- реализует сценарии использования системы (что делает пользователь),
  но НЕ содержит:
    - UI-кода (это presentation)
    - конкретных реализаций БД (это infrastructure)
    - логики решателя (это infrastructure/optimizer)

Application:
- координирует репозитории
- вызывает доменные сервисы
- вызывает оптимизатор
- сохраняет результаты

Примеры use-cases:
- ImportDataUseCase
- ExportDataUseCase
- GenerateScheduleUseCase
- SaveVariantUseCase
- ApplyManualEditUseCase
"""

__all__ = [
    "use_cases",
    "dto",
]