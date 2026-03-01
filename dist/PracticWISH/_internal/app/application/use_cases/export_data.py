# app/application/use_cases/export_data.py
"""
Use-case: экспорт данных и/или расписания.

Назначение:
- экспортировать справочники (преподаватели, группы, дисциплины, аудитории)
- экспортировать расписание выбранного варианта (сеткой и таблицей)
- не содержит логики Excel: это responsibility ExcelExportService (infrastructure)

Возвращает путь(и) к созданным файлам, чтобы GUI мог показать уведомление/открыть папку.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ------------------------------------------------------------
# Команда экспорта
# ------------------------------------------------------------

@dataclass(frozen=True)
class ExportDataCommand:
    """
    Что экспортируем:
    - dictionaries: справочники
    - schedule: расписание
    Можно выбрать одно или оба.

    variant_id нужен, если export_schedule=True.
    """
    export_dictionaries: bool = True
    export_schedule: bool = True

    variant_id: Optional[int] = None

    # Формат/куда
    format: str = "xlsx"   # "xlsx" | "csv"
    out_dir: Optional[Path] = None

    # Настройки экспорта
    include_metrics: bool = True
    include_grid_view: bool = True
    include_table_view: bool = True


# ------------------------------------------------------------
# Результат экспорта
# ------------------------------------------------------------

@dataclass(frozen=True)
class ExportDataResult:
    dictionaries_file: Optional[Path]
    schedule_file: Optional[Path]


# ------------------------------------------------------------
# Use-case
# ------------------------------------------------------------

class ExportDataUseCase:
    def __init__(self, excel_export):
        """
        excel_export: ExcelExportService (infrastructure)
        """
        self._excel_export = excel_export

    def execute(self, command: ExportDataCommand) -> ExportDataResult:
        """
        Выполняет экспорт согласно команде.
        """
        out_dir = command.out_dir or self._excel_export.get_default_export_dir()

        dict_file: Optional[Path] = None
        schedule_file: Optional[Path] = None

        if command.export_dictionaries:
            dict_file = self._excel_export.export_dictionaries(
                out_dir=out_dir,
                fmt=command.format,
            )

        if command.export_schedule:
            if command.variant_id is None:
                raise ValueError("variant_id обязателен для экспорта расписания.")
            schedule_file = self._excel_export.export_schedule_variant(
                variant_id=command.variant_id,
                out_dir=out_dir,
                fmt=command.format,
                include_metrics=command.include_metrics,
                include_grid_view=command.include_grid_view,
                include_table_view=command.include_table_view,
            )

        return ExportDataResult(
            dictionaries_file=dict_file,
            schedule_file=schedule_file,
        )