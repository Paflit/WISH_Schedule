from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from app.application.dto.schedule_dto import GenerationResultDTO, ScheduleVariantDTO
from app.domain.exceptions import SolverError, ValidationError

ProgressCallback = Optional[Callable[[str, dict], None]]


@dataclass(frozen=True)
class GenerateScheduleCommand:
    """
    Единая команда генерации расписания.

    Важно:
    - Никаких rule_profile_key / random_seed / created_by снаружи.
    - UseCase сам определяет базовый профиль правил и технические параметры.
    """

    calendar_id: int
    variants_count: int
    time_limit_seconds: int

    def __post_init__(self) -> None:
        if int(self.calendar_id) <= 0:
            raise ValidationError("calendar_id должен быть положительным числом.")
        if int(self.variants_count) <= 0:
            raise ValidationError("Количество вариантов должно быть больше 0.")
        if int(self.time_limit_seconds) <= 0:
            raise ValidationError("Лимит времени должен быть больше 0.")


class GenerateScheduleUseCase:
    """
    Единый сценарий генерации расписания.

    Последовательность:
    1. Валидация входных данных.
    2. Загрузка календаря и справочников.
    3. Загрузка semester/weekly plan.
    4. Построение generation events.
    5. Запуск solver.
    6. Сохранение вариантов в БД.
    7. Возврат DTO результата.
    """

    BASE_RULE_PROFILE_KEY = "balanced"
    GENERATED_BY = "generator"

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

    def _emit(self, progress_cb: ProgressCallback, stage: str, **payload) -> None:
        if progress_cb is not None:
            progress_cb(stage, payload)

    @staticmethod
    def _positive_int(value, default: int = 0) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError):
            return int(default)
        return result

    def _get_rules(self):
        if hasattr(self._rule_profiles, "get"):
            return self._rule_profiles.get(self.BASE_RULE_PROFILE_KEY)

        try:
            return self._rule_profiles[self.BASE_RULE_PROFILE_KEY]
        except Exception:
            return None

    def _validate_reference_data(
        self,
        *,
        teachers,
        groups,
        rooms,
        slots,
        semester_plans,
        weekly_plans,
        curriculum_map,
    ) -> None:
        if not semester_plans:
            raise ValidationError(
                "Для выбранного полугодия в учебном плане нет дисциплин с часами."
            )

        if not weekly_plans:
            raise ValidationError(
                "Для выбранного полугодия не сформирован недельный учебный план."
            )

        if not curriculum_map:
            raise ValidationError(
                "Не найдено элементов учебного плана для выбранного полугодия."
            )

        if not teachers:
            raise ValidationError("В системе нет преподавателей.")

        if not groups:
            raise ValidationError("В системе нет учебных групп.")

        if not rooms:
            raise ValidationError("В системе нет аудиторий.")

        if not slots:
            raise ValidationError(
                "Для выбранного полугодия отсутствуют временные слоты."
            )

    def execute(
        self,
        command: GenerateScheduleCommand,
        progress_cb: ProgressCallback = None,
    ) -> GenerationResultDTO:
        calendar_id = int(command.calendar_id)
        variants_count = int(command.variants_count)
        time_limit_seconds = int(command.time_limit_seconds)

        self._emit(
            progress_cb,
            "start",
            calendar_id=calendar_id,
            variants_count=variants_count,
            time_limit_seconds=time_limit_seconds,
        )

        calendar = self._calendar_repo.get_calendar(calendar_id)
        if calendar is None:
            raise ValidationError(f"Календарь id={calendar_id} не найден.")

        academic_year = str(getattr(calendar, "academic_year", "") or "")
        semester = self._positive_int(getattr(calendar, "semester", 0))

        self._emit(
            progress_cb,
            "calendar_loaded",
            academic_year=academic_year,
            semester=semester,
        )

        semester_plans = [
            p
            for p in self._curriculum_repo.get_semester_plans(calendar_id)
            if self._positive_int(getattr(p, "hours_in_semester", 0)) > 0
        ]
        self._emit(
            progress_cb,
            "semester_plans_loaded",
            semester_plans_count=len(semester_plans),
            total_semester_hours=sum(
                self._positive_int(getattr(p, "hours_in_semester", 0))
                for p in semester_plans
            ),
        )

        weekly_plans = [
            w
            for w in self._curriculum_repo.get_weekly_plans(calendar_id)
            if self._positive_int(getattr(w, "hours_this_week", 0)) > 0
        ]
        self._emit(
            progress_cb,
            "weekly_plans_loaded",
            weekly_plans_count=len(weekly_plans),
            weekly_total_hours=sum(
                self._positive_int(getattr(w, "hours_this_week", 0))
                for w in weekly_plans
            ),
        )

        teachers = self._teachers_repo.list_all()
        groups = self._groups_repo.list_all()
        rooms = self._rooms_repo.list_all()
        slots = self._calendar_repo.list_time_slots(calendar_id)

        self._emit(
            progress_cb,
            "reference_data_loaded",
            teachers_count=len(teachers),
            groups_count=len(groups),
            rooms_count=len(rooms),
            slots_count=len(slots),
        )

        curriculum_map = self._curriculum_repo.get_curriculum_items_for_plans(
            semester_plans
        )
        self._emit(
            progress_cb,
            "curriculum_map_loaded",
            curriculum_items_count=len(curriculum_map),
        )

        self._validate_reference_data(
            teachers=teachers,
            groups=groups,
            rooms=rooms,
            slots=slots,
            semester_plans=semester_plans,
            weekly_plans=weekly_plans,
            curriculum_map=curriculum_map,
        )

        rules = self._get_rules()
        if rules is None:
            raise ValidationError(
                f"Не найден базовый профиль правил '{self.BASE_RULE_PROFILE_KEY}'."
            )

        locks = self._schedule_repo.list_locks_for_calendar(calendar_id)
        self._emit(
            progress_cb,
            "rules_loaded",
            rules_profile=self.BASE_RULE_PROFILE_KEY,
            locks_count=len(locks),
        )

        teacher_subjects = self._teachers_repo.get_teacher_part_matrix()
        teacher_availability = self._teachers_repo.get_availability_matrix(calendar_id)

        self._emit(
            progress_cb,
            "availability_loaded",
            teacher_subject_links=len(teacher_subjects),
            availability_links=len(teacher_availability),
        )

        self._emit(progress_cb, "building_events")

        try:
            events = self._event_builder.build_events(
                calendar_id=calendar_id,
                hours_per_pair=self._positive_int(
                    getattr(self._config, "hours_per_pair", 2),
                    default=2,
                ),
                locks=locks,
            )
        except ValidationError:
            raise
        except Exception as exc:
            raise SolverError(
                f"Ошибка при построении событий генерации: {exc}"
            ) from exc

        self._emit(
            progress_cb,
            "events_built",
            events_count=len(events),
        )

        if not events:
            raise ValidationError("Не удалось построить события для генерации.")

        # Сохраняем generation events, чтобы downstream-слои
        # работали с тем же набором исходных данных.
        self._schedule_repo.set_generation_events(events)

        random_seed = self._positive_int(getattr(self._config, "random_seed", 1), 1)

        self._emit(
            progress_cb,
            "solver_started",
            k_solutions=variants_count,
            time_limit_seconds=time_limit_seconds,
            random_seed=random_seed,
        )

        try:
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
                time_limit_seconds=time_limit_seconds,
                random_seed=random_seed,
                locks=locks,
            )
        except ValidationError:
            raise
        except SolverError:
            raise
        except Exception as exc:
            raise SolverError(f"Ошибка solver при генерации расписания: {exc}") from exc

        self._emit(
            progress_cb,
            "solver_finished",
            solutions_count=len(solutions),
        )

        if not solutions:
            raise ValidationError("Solver не нашёл ни одного допустимого варианта.")

        variants: list[ScheduleVariantDTO] = []

        for idx, solution in enumerate(solutions, start=1):
            solution_entries = list(getattr(solution, "entries", []) or [])
            objective_value = self._positive_int(
                getattr(solution, "objective_value", 0),
                default=0,
            )

            variant_name = (
                f"{academic_year}_semester_{semester}_variant_{idx}"
                if academic_year
                else f"semester_{semester}_variant_{idx}"
            )

            self._emit(
                progress_cb,
                "saving_variant",
                variant_index=idx,
                entries_count=len(solution_entries),
                objective_value=objective_value,
            )

            try:
                variant_id = self._schedule_repo.create_variant(
                    calendar_id=calendar_id,
                    rule_profile_key=self.BASE_RULE_PROFILE_KEY,
                    name=variant_name,
                    objective_score=objective_value,
                    created_by=self.GENERATED_BY,
                )

                self._schedule_repo.save_solution_entries(
                    variant_id=int(variant_id),
                    solution_entries=solution_entries,
                )

                variant_dto = self._schedule_repo.get_variant_dto(int(variant_id))
            except Exception as exc:
                raise SolverError(
                    f"Ошибка при сохранении варианта расписания #{idx}: {exc}"
                ) from exc

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