from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.application.use_cases.apply_manual_edit import ApplyManualEditUseCase
from app.application.use_cases.generate_schedule import GenerateScheduleUseCase
from app.config import AppConfig
from app.infrastructure.db.repositories import (
    SqliteCalendarRepository,
    SqliteCurriculumRepository,
    SqliteGroupsRepository,
    SqliteRoomsRepository,
    SqliteScheduleRepository,
    SqliteSubjectsRepository,
    SqliteTeachersRepository,
)
from app.infrastructure.db.sqlite import make_session_factory
from app.infrastructure.optimizer.cp_sat_solver import CPSatScheduleSolver
from app.infrastructure.optimizer.event_builder import EventBuilder


@dataclass(slots=True)
class Container:
    config: AppConfig
    session_factory: object

    teachers_repo: SqliteTeachersRepository
    subjects_repo: SqliteSubjectsRepository
    groups_repo: SqliteGroupsRepository
    rooms_repo: SqliteRoomsRepository
    calendar_repo: SqliteCalendarRepository
    curriculum_repo: SqliteCurriculumRepository
    schedule_repo: SqliteScheduleRepository

    event_builder: EventBuilder
    solver: CPSatScheduleSolver

    apply_manual_edit_uc: ApplyManualEditUseCase
    generate_schedule_uc: GenerateScheduleUseCase

    rule_profiles: dict


def _load_rule_profiles() -> dict:
    return {
        "balanced": {
            "teacher_hard_max_pairs": 6,
            "teacher_soft_max_pairs": 4,
            "allow_lunch_gap": True,
            "lunch_gap_min_pair": 2,
            "lunch_gap_max_pair": 3,
            "allow_student_gaps": False,
            "min_pairs_students_per_day": 2,
            "max_pairs_students_per_day": 5,
            "consider_method_day": True,
            "w_teacher_over_soft": 700,
            "w_teacher_gaps": 150,
            "w_students_gaps": 600,
            "w_students_day_load": 500,
            "w_method_day": 250,
            "w_lecture_late": 70,
            "lecture_preferred_last_pair": 2,
        }
    }


def _rule_profile_to_object(payload: dict):
    class RuleProfile:
        pass

    obj = RuleProfile()
    for key, value in (payload or {}).items():
        setattr(obj, key, value)
    return obj


def _build_rules_map() -> dict:
    raw = _load_rule_profiles()
    return {key: _rule_profile_to_object(value) for key, value in raw.items()}


def _db_path_from_url(db_url: str) -> str:
    if not db_url:
        raise ValueError("config.db_url пуст.")

    if not db_url.startswith("sqlite:///"):
        raise ValueError(f"Поддерживается только sqlite:///..., получено: {db_url}")

    return db_url.replace("sqlite:///", "", 1)


def build_container(config: AppConfig | None = None) -> Container:
    config = config or AppConfig.load()

    db_path = Path(_db_path_from_url(config.db_url))
    if db_path.parent and not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    session_factory = make_session_factory(str(db_path))

    teachers_repo = SqliteTeachersRepository(session_factory)
    subjects_repo = SqliteSubjectsRepository(session_factory)
    groups_repo = SqliteGroupsRepository(session_factory)
    rooms_repo = SqliteRoomsRepository(session_factory)
    calendar_repo = SqliteCalendarRepository(session_factory)
    curriculum_repo = SqliteCurriculumRepository(session_factory)
    schedule_repo = SqliteScheduleRepository(session_factory)

    event_builder = EventBuilder(
        curriculum_repo=curriculum_repo,
        calendar_repo=calendar_repo,
        groups_repo=groups_repo,
        rooms_repo=rooms_repo,
        rules_repo=None,
    )
    solver = CPSatScheduleSolver()

    rule_profiles = _build_rules_map()

    apply_manual_edit_uc = ApplyManualEditUseCase(
        schedule_repo=schedule_repo,
        teachers_repo=teachers_repo,
        groups_repo=groups_repo,
        rooms_repo=rooms_repo,
        calendar_repo=calendar_repo,
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

    return Container(
        config=config,
        session_factory=session_factory,
        teachers_repo=teachers_repo,
        subjects_repo=subjects_repo,
        groups_repo=groups_repo,
        rooms_repo=rooms_repo,
        calendar_repo=calendar_repo,
        curriculum_repo=curriculum_repo,
        schedule_repo=schedule_repo,
        event_builder=event_builder,
        solver=solver,
        apply_manual_edit_uc=apply_manual_edit_uc,
        generate_schedule_uc=generate_schedule_uc,
        rule_profiles=rule_profiles,
    )