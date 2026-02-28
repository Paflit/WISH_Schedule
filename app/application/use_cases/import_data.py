# app/application/use_cases/import_data.py
"""
Use-case: импорт данных (справочников и учебного плана) из Excel/CSV.

Назначение:
- принять путь к файлу
- передать выполнение в инфраструктурный сервис импорта
- вернуть краткий отчёт, который покажет GUI

Важно:
- Валидация формата/структуры файла выполняется в ExcelImportService.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ------------------------------------------------------------
# Команда импорта
# ------------------------------------------------------------

@dataclass(frozen=True)
class ImportDataCommand:
    file_path: Path
    format: str = "xlsx"  # "xlsx" | "csv"

    import_teachers: bool = True
    import_subjects: bool = True
    import_groups: bool = True
    import_rooms: bool = True
    import_calendar: bool = True
    import_curriculum: bool = True
    import_availability: bool = True


# ------------------------------------------------------------
# Результат импорта
# ------------------------------------------------------------

@dataclass(frozen=True)
class ImportDataResult:
    teachers_imported: int = 0
    subjects_imported: int = 0
    groups_imported: int = 0
    rooms_imported: int = 0
    calendar_rows_imported: int = 0
    curriculum_rows_imported: int = 0
    availability_rows_imported: int = 0

    warnings: Optional[str] = None


# ------------------------------------------------------------
# Use-case
# ------------------------------------------------------------

class ImportDataUseCase:
    def __init__(self, excel_import):
        """
        excel_import: ExcelImportService (infrastructure)
        """
        self._excel_import = excel_import

    def execute(self, command: ImportDataCommand) -> ImportDataResult:
        """
        Импортирует данные и возвращает статистику.
        """
        stats = self._excel_import.import_all(
            file_path=command.file_path,
            fmt=command.format,
            flags={
                "teachers": command.import_teachers,
                "subjects": command.import_subjects,
                "groups": command.import_groups,
                "rooms": command.import_rooms,
                "calendar": command.import_calendar,
                "curriculum": command.import_curriculum,
                "availability": command.import_availability,
            },
        )

        # stats — обычный dict, приводим к DTO
        return ImportDataResult(
            teachers_imported=stats.get("teachers", 0),
            subjects_imported=stats.get("subjects", 0),
            groups_imported=stats.get("groups", 0),
            rooms_imported=stats.get("rooms", 0),
            calendar_rows_imported=stats.get("calendar", 0),
            curriculum_rows_imported=stats.get("curriculum", 0),
            availability_rows_imported=stats.get("availability", 0),
            warnings=stats.get("warnings"),
        )