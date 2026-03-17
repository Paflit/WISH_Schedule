from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from app.application.dto.schedule_dto import (
    GenerationResultDTO,
    ScheduleVariantDTO,
)
from app.domain.exceptions import ValidationError


ProgressCallback = Optional[Callable[[str, dict], None]]


@dataclass(frozen=True)
class GenerateScheduleCommand:
    calendar_id: int
    variants_count: int
    time_limit_seconds: int


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

    def _emit(self, progress_cb: ProgressCallback, stage: str, **payload):
        if progress_cb is not None:
            progress_cb(stage, payload)

    def execute(
        self,
        command: GenerateScheduleCommand,
        progress_cb: ProgressCallback = None,
    ) -> GenerationResultDTO:
        self._emit(
            progress_cb,
            "start",
            calendar_id=int(command.calendar_id),
            variants_count=int(command.variants_count),
            time_limit_seconds=int(command.time_limit_seconds),
        )

        calendar = self._calendar_repo.get_calendar(int(command.calendar_id))
        if calendar is None:
            raise ValidationError(f"Календарь id={command.calendar_id} не найден.")

        self._emit(
            progress_cb,
            "calendar_loaded",
            academic_year=str(getattr(calendar, "academic_year", "")),
            semester=int(getattr(calendar, "semester", 0) or 0),
        )

        semester_plans = self._curriculum_repo.get_semester_plans(int(command.calendar_id))
        semester_plans = [
            p for p in semester_plans
            if int(getattr(p, "hours_in_semester", 0) or 0) > 0
        ]

        self._emit(
            progress_cb,
            "semester_plans_loaded",
            semester_plans_count=len(semester_plans),
            total_semester_hours=sum(
                int(getattr(p, "hours_in_semester", 0) or 0) for p in semester_plans
            ),
        )

        if not semester_plans:
            raise ValidationError(
                "Для выбранного полугодия в учебном плане нет дисциплин с часами."
            )

        weekly_plans = self._curriculum_repo.get_weekly_plans(int(command.calendar_id))
        weekly_plans = [
            w for w in weekly_plans
            if int(getattr(w, "hours_this_week", 0) or 0) > 0
        ]

        self._emit(
            progress_cb,
            "weekly_plans_loaded",
            weekly_plans_count=len(weekly_plans),
            weekly_total_hours=sum(
                int(getattr(w, "hours_this_week", 0) or 0) for w in weekly_plans
            ),
        )

        teachers = self._teachers_repo.list_all()
        groups = self._groups_repo.list_all()
        rooms = self._rooms_repo.list_all()
        slots = self._calendar_repo.list_time_slots(int(command.calendar_id))

        self._emit(
            progress_cb,
            "reference_data_loaded",
            teachers_count=len(teachers),
            groups_count=len(groups),
            rooms_count=len(rooms),
            slots_count=len(slots),
        )

        if not teachers:
            raise ValidationError("Нет преподавателей.")
        if not groups:
            raise ValidationError("Нет групп.")
        if not rooms:
            raise ValidationError("Нет аудиторий.")
        if not slots:
            raise ValidationError("Нет временных слотов для выбранного полугодия.")

        # Один общий набор правил для единого согласованного расписания
        rules = self._rule_profiles.get("balanced")
        if rules is None:
            raise ValidationError("Не найден базовый профиль правил 'balanced'.")

        locks = self._schedule_repo.list_locks_for_calendar(int(command.calendar_id))

        self._emit(
            progress_cb,
            "rules_loaded",
            rules_profile="balanced",
            locks_count=len(locks),
        )

        curriculum_map = self._curriculum_repo.get_curriculum_items_for_plans(semester_plans)

        self._emit(
            progress_cb,
            "curriculum_map_loaded",
            curriculum_items_count=len(curriculum_map),
        )

        if not curriculum_map:
            raise ValidationError(
                "Не найдено элементов учебного плана для выбранного полугодия."
            )

        teacher_subjects = self._teachers_repo.get_teacher_part_matrix()
        teacher_availability = self._teachers_repo.get_availability_matrix(int(command.calendar_id))

        self._emit(
            progress_cb,
            "availability_loaded",
            teacher_subject_links=len(teacher_subjects),
            availability_links=len(teacher_availability),
        )

        self._emit(progress_cb, "building_events")

        events = self._event_builder.build_events(
            calendar_id=int(command.calendar_id),
            hours_per_pair=int(getattr(self._config, "hours_per_pair", 2)),
            locks=locks,
        )

        self._emit(
            progress_cb,
            "events_built",
            events_count=len(events),
        )

        if not events:
            raise ValidationError("Не удалось построить события для генерации.")

        self._schedule_repo.set_generation_events(events)

        self._emit(
            progress_cb,
            "solver_started",
            k_solutions=int(command.variants_count),
            time_limit_seconds=int(command.time_limit_seconds),
            random_seed=int(getattr(self._config, "random_seed", 1)),
        )

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
            k_solutions=int(command.variants_count),
            time_limit_seconds=int(command.time_limit_seconds),
            random_seed=int(getattr(self._config, "random_seed", 1)),
            locks=locks,
        )

        self._emit(
            progress_cb,
            "solver_finished",
            solutions_count=len(solutions),
        )

        if not solutions:
            raise ValidationError("Solver не нашёл ни одного допустимого варианта.")

        variants: list[ScheduleVariantDTO] = []

        semester = int(getattr(calendar, "semester", 0) or 0)
        year = str(getattr(calendar, "academic_year", "") or "")

        for idx, solution in enumerate(solutions, start=1):
            variant_name = f"{year}_semester_{semester}_variant_{idx}"

            self._emit(
                progress_cb,
                "saving_variant",
                variant_index=idx,
                entries_count=len(getattr(solution, "entries", []) or []),
                objective_value=int(getattr(solution, "objective_value", 0) or 0),
            )

            variant_id = self._schedule_repo.create_variant(
                calendar_id=int(command.calendar_id),
                rule_profile_key="balanced",
                name=variant_name,
                objective_score=int(getattr(solution, "objective_value", 0) or 0),
                created_by="generator",
            )

            self._schedule_repo.save_solution_entries(
                variant_id=variant_id,
                solution_entries=list(getattr(solution, "entries", []) or []),
            )

            variant_dto = self._schedule_repo.get_variant_dto(int(variant_id))
            variants.append(variant_dto)

            self._emit(
                progress_cb,
                "variant_saved",
                variant_index=idx,
                variant_id=int(variant_id),
                variant_name=str(getattr(variant_dto, "name", "") or ""),
                dto_entries_count=len(getattr(variant_dto, "entries", []) or []),
            )

        self._emit(
            progress_cb,
            "done",
            variants_count=len(variants),
        )

        return GenerationResultDTO(variants=variants)