# app/di.py
"""
DI (Dependency Injection) контейнер.

Задачи:
- собрать инфраструктурные зависимости (БД, репозитории, импорт/экспорт, оптимизатор)
- собрать use-cases (application слой)
- отдать "container" (словарь) для GUI слоя, чтобы presentation ничего не знала
  про конкретные реализации инфраструктуры.

Контейнер сделан максимально простым: обычный dict[str, object].
При желании легко заменить на dependency-injector / punq и т.п.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.config import AppConfig

# Infrastructure
from app.infrastructure.db.sqlite import create_engine_and_session_factory
from app.infrastructure.db.repositories import (
    SqliteTeachersRepository,
    SqliteSubjectsRepository,
    SqliteGroupsRepository,
    SqliteRoomsRepository,
    SqliteCalendarRepository,
    SqliteCurriculumRepository,
    SqliteScheduleRepository,
)

from app.infrastructure.import_export.excel_import import ExcelImportService
from app.infrastructure.import_export.excel_export import ExcelExportService

from app.infrastructure.optimizer.cp_sat_solver import CPSatScheduleSolver
from app.infrastructure.optimizer.event_builder import EventBuilder

# Application (use-cases)
from app.application.use_cases.import_data import ImportDataUseCase
from app.application.use_cases.export_data import ExportDataUseCase
from app.application.use_cases.generate_schedule import GenerateScheduleUseCase
from app.application.use_cases.save_variant import SaveVariantUseCase
from app.application.use_cases.apply_manual_edit import ApplyManualEditUseCase

# Domain
from app.domain.rules import DefaultRuleProfiles


@dataclass(frozen=True)
class Container:
    """
    Тонкая типизированная обёртка над dict-контейнером.
    В GUI можно использовать container.xxx вместо container["xxx"].
    """
    config: AppConfig

    # Repositories
    teachers_repo: Any
    subjects_repo: Any
    groups_repo: Any
    rooms_repo: Any
    calendar_repo: Any
    curriculum_repo: Any
    schedule_repo: Any

    # Services
    excel_import: ExcelImportService
    excel_export: ExcelExportService
    event_builder: EventBuilder
    solver: CPSatScheduleSolver

    # Use-cases
    import_data_uc: ImportDataUseCase
    export_data_uc: ExportDataUseCase
    generate_schedule_uc: GenerateScheduleUseCase
    save_variant_uc: SaveVariantUseCase
    apply_manual_edit_uc: ApplyManualEditUseCase

    # Domain profiles (weights presets)
    rule_profiles: DefaultRuleProfiles


def build_container() -> Container:
    """
    Собирает все зависимости приложения.

    Стратегия:
    - AppConfig читает настройки (путь к БД и т.п.)
    - создаём engine + session_factory (SQLite)
    - создаём репозитории (каждый получает session_factory)
    - создаём сервисы (solver, import/export, event_builder)
    - создаём use-cases, передавая им порты (репозитории/сервисы)
    """

    # 1) Config
    config = AppConfig.load()

    # 2) DB core
    engine, session_factory = create_engine_and_session_factory(config.db_url)

    # 3) Repositories (SQLite implementations)
    teachers_repo = SqliteTeachersRepository(session_factory)
    subjects_repo = SqliteSubjectsRepository(session_factory)
    groups_repo = SqliteGroupsRepository(session_factory)
    rooms_repo = SqliteRoomsRepository(session_factory)
    calendar_repo = SqliteCalendarRepository(session_factory)
    curriculum_repo = SqliteCurriculumRepository(session_factory)
    schedule_repo = SqliteScheduleRepository(session_factory)

    # 4) Domain profiles (готовые наборы весов/правил для UI)
    rule_profiles = DefaultRuleProfiles()

    # 5) Infrastructure services
    excel_import = ExcelImportService(
        teachers_repo=teachers_repo,
        subjects_repo=subjects_repo,
        groups_repo=groups_repo,
        rooms_repo=rooms_repo,
        calendar_repo=calendar_repo,
        curriculum_repo=curriculum_repo,
    )
    excel_export = ExcelExportService(
        teachers_repo=teachers_repo,
        subjects_repo=subjects_repo,
        groups_repo=groups_repo,
        rooms_repo=rooms_repo,
        calendar_repo=calendar_repo,
        curriculum_repo=curriculum_repo,
        schedule_repo=schedule_repo,
    )

    event_builder = EventBuilder(
        curriculum_repo=curriculum_repo,
        calendar_repo=calendar_repo,
        rules_repo=calendar_repo,  # MVP: правила храним/читаем через calendar_repo или отдельный repo
    )

    solver = CPSatScheduleSolver()

    # 6) Use-cases
    import_data_uc = ImportDataUseCase(
        excel_import=excel_import
    )

    export_data_uc = ExportDataUseCase(
        excel_export=excel_export
    )

    generate_schedule_uc = GenerateScheduleUseCase(
        teachers_repo=teachers_repo,
        subjects_repo=subjects_repo,
        groups_repo=groups_repo,
        rooms_repo=rooms_repo,
        calendar_repo=calendar_repo,
        curriculum_repo=curriculum_repo,
        schedule_repo=schedule_repo,
        event_builder=event_builder,
        solver=solver,
        rule_profiles=rule_profiles,
        config=config,
    )

    save_variant_uc = SaveVariantUseCase(
        schedule_repo=schedule_repo
    )

    apply_manual_edit_uc = ApplyManualEditUseCase(
        schedule_repo=schedule_repo,
        teachers_repo=teachers_repo,
        rooms_repo=rooms_repo,
        calendar_repo=calendar_repo,
    )

    return Container(
        config=config,

        teachers_repo=teachers_repo,
        subjects_repo=subjects_repo,
        groups_repo=groups_repo,
        rooms_repo=rooms_repo,
        calendar_repo=calendar_repo,
        curriculum_repo=curriculum_repo,
        schedule_repo=schedule_repo,

        excel_import=excel_import,
        excel_export=excel_export,
        event_builder=event_builder,
        solver=solver,

        import_data_uc=import_data_uc,
        export_data_uc=export_data_uc,
        generate_schedule_uc=generate_schedule_uc,
        save_variant_uc=save_variant_uc,
        apply_manual_edit_uc=apply_manual_edit_uc,

        rule_profiles=rule_profiles,
    )