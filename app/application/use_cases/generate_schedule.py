# app/application/use_cases/generate_schedule.py
"""
Use-case: генерация расписания (несколько вариантов) на основе:
- календарного учебного графика (AcademicCalendar + SemesterWeeks + TimeSlots)
- учебного плана на семестр (CurriculumSemesterPlan + WeeklyLoadPlan)
- справочников (teachers, groups, rooms, subjects)
- пожеланий преподавателей (TeacherAvailability)
- правил/весов (SchedulingRules / профили оптимизации)

Use-case НЕ строит модель OR-Tools напрямую.
Он:
1) Загружает данные через репозитории
2) Строит список Event через EventBuilder
3) Вызывает solver (CPSatScheduleSolver)
4) Сохраняет варианты в БД (ScheduleVariants + ScheduleEntries)
5) Возвращает DTO для GUI
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

from app.application.dto.schedule_dto import (
    GenerationResultDTO,
    ScheduleVariantDTO,
)
from app.domain.exceptions import ValidationError


# ------------------------------------------------------------
# Команда генерации
# ------------------------------------------------------------

@dataclass(frozen=True)
class GenerateScheduleCommand:
    calendar_id: int

    # профили правил: "students", "teachers", "balanced", ...
    rule_profile_key: str = "balanced"

    # сколько вариантов хотим
    variants_count: Optional[int] = None

    # лимит времени на один запуск решателя
    time_limit_seconds: Optional[int] = None

    # random seed (для разнообразия)
    random_seed: Optional[int] = None

    # если True — учитывать локи (ScheduleLocks) как hard constraints
    respect_locks: bool = True

    # имя префикса для создаваемых вариантов
    variant_name_prefix: str = "Auto"

    # кто запускает
    created_by: str = "admin"


# ------------------------------------------------------------
# Use-case
# ------------------------------------------------------------

class GenerateScheduleUseCase:
    def __init__(
        self,
        teachers_repo,
        subjects_repo,
        groups_repo,
        rooms_repo,
        calendar_repo,
        curriculum_repo,
        schedule_repo,
        event_builder,
        solver,
        rule_profiles,
        config,
    ):
        self._teachers_repo = teachers_repo
        self._subjects_repo = subjects_repo
        self._groups_repo = groups_repo
        self._rooms_repo = rooms_repo
        self._calendar_repo = calendar_repo
        self._curriculum_repo = curriculum_repo
        self._schedule_repo = schedule_repo
        self._event_builder = event_builder
        self._solver = solver
        self._rule_profiles = rule_profiles
        self._config = config

    # --------------------------------------------------------

    def execute(self, command: GenerateScheduleCommand) -> GenerationResultDTO:
        # 1) Проверим календарь
        calendar = self._calendar_repo.get_calendar(command.calendar_id)
        if calendar is None:
            raise ValidationError("Календарь/семестр не найден.")

        # 2) Возьмём правила/веса по профилю
        rules = self._rule_profiles.get(command.rule_profile_key)
        if rules is None:
            raise ValidationError(f"Профиль правил '{command.rule_profile_key}' не найден.")

        variants_count = command.variants_count or self._config.solver_variants_count
        time_limit = command.time_limit_seconds or self._config.solver_time_limit_seconds
        random_seed = command.random_seed or self._config.solver_random_seed

        # 3) Загрузим справочники и данные семестра
        teachers = self._teachers_repo.list_all()
        groups = self._groups_repo.list_all()
        rooms = self._rooms_repo.list_all()
        slots = self._calendar_repo.list_time_slots(calendar_id=command.calendar_id)

        if not slots:
            raise ValidationError("Нет таймслотов для выбранного семестра. Заполните календарный график/сетку пар.")

        # учебный план (на семестр)
        curriculum_items = self._curriculum_repo.list_curriculum_items(calendar_id=command.calendar_id)
        if not curriculum_items:
            raise ValidationError("Нет учебного плана на семестр. Заполните CurriculumItems/CurriculumSemesterPlan.")

        curriculum_map = {c.id_curriculum: c for c in curriculum_items}

        # связи преподаватель-предмет
        teacher_subjects = self._teachers_repo.get_teacher_subject_matrix()  # dict[(teacher_id, subject_id)] -> bool

        # доступность преподавателей (по слотам)
        teacher_availability = self._teachers_repo.get_availability_matrix(calendar_id=command.calendar_id)
        # dict[(teacher_id, slot_id)] -> bool

        # 4) Локи (если есть) — передадим в event_builder/solver
        locks = []
        if command.respect_locks:
            locks = self._schedule_repo.list_locks_for_calendar(calendar_id=command.calendar_id)

        # 5) Сформируем Events из семестрового плана (учитывая WeeklyLoadPlan)
        # event_builder вернёт список domain-сущностей Event (не DTO)
        events = self._event_builder.build_events(
            calendar_id=command.calendar_id,
            hours_per_pair=self._config.hours_per_pair,
            locks=locks,
        )

        if not events:
            raise ValidationError("Список событий (занятий) пуст. Проверьте часы в семестровом плане/недельном плане.")

        # 6) Запустим solver: получим K решений
        solutions = self._solver.solve(
            teachers=teachers,
            groups=groups,
            rooms=rooms,
            slots=slots,
            curriculum=curriculum_map,
            events=events,
            teacher_subjects=teacher_subjects,
            teacher_availability=teacher_availability,
            rules=rules,
            k_solutions=variants_count,
            time_limit_seconds=time_limit,
            random_seed=random_seed,
            locks=locks if command.respect_locks else None,
        )

        if not solutions:
            raise ValidationError("Не удалось построить ни одного варианта. Проверьте ограничения/доступность/аудитории.")

        # 7) Сохраним варианты в БД и соберём DTO для GUI
        variant_dtos: List[ScheduleVariantDTO] = []
        for idx, sol in enumerate(solutions, start=1):
            variant_name = f"{command.variant_name_prefix} #{idx} ({command.rule_profile_key})"
            variant_id = self._schedule_repo.create_variant(
                calendar_id=command.calendar_id,
                rule_profile_key=command.rule_profile_key,
                name=variant_name,
                objective_score=sol.objective_value,
                created_by=command.created_by,
            )

            self._schedule_repo.save_solution_entries(
                variant_id=variant_id,
                solution_entries=sol.entries,   # list[SolutionEntry] (event_id, slot_id, teacher_id, room_id)
            )

            # Переводим в DTO (репозиторий знает имена, предметы, и т.д.)
            dto = self._schedule_repo.get_variant_dto(variant_id)
            variant_dtos.append(dto)

        return GenerationResultDTO(variants=variant_dtos)