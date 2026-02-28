# app/infrastructure/import_export/__init__.py
"""
Import/Export layer.

Здесь находятся реализации:
- ExcelImportService  — загрузка справочников и учебного плана из Excel/CSV
- ExcelExportService  — выгрузка справочников и расписания

Этот слой:
- зависит от infrastructure.db (репозиториев)
- НЕ используется напрямую из GUI
- вызывается только через application/use-cases

Поддерживаемые форматы (MVP):
- xlsx (через openpyxl)
- csv (через стандартную библиотеку)

Принцип:
presentation -> use_case -> import/export service -> repositories
"""

__all__ = [
    "excel_import",
    "excel_export",
]