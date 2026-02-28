# app/application/dto/__init__.py
"""
DTO (Data Transfer Objects) для application слоя.

Назначение:
- использовать простые структуры данных для передачи информации
  между слоями (presentation <-> application <-> infrastructure)
- не тащить ORM-модели или Qt-объекты наружу
- изолировать доменные сущности от UI

Примеры DTO:
- ScheduleVariantDTO
- ScheduleEntryDTO
- TeacherDTO
- GroupDTO
- GenerationResultDTO

DTO:
- не содержит бизнес-логики
- может быть dataclass
- может быть Pydantic-модель (если нужно)
"""

__all__ = [
    "schedule_dto",
]