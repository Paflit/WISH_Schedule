from __future__ import annotations

from collections import Counter, defaultdict
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional

from app.application.dto.schedule_dto import GenerationResultDTO, ScheduleVariantDTO
from app.domain.exceptions import SolverError, SolverInfeasibleError, ValidationError
from app.domain.group_rules import min_pairs_per_active_day_for_group
from app.domain.models import Room

ProgressCallback = Optional[Callable[[str, dict], None]]


def setup_generation_logger(variant_id: int) -> logging.Logger:
    
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    log_file = logs_dir / f"generation_{variant_id}.log"
    
    logger = logging.getLogger(f"generation_{variant_id}")
    logger.setLevel(logging.INFO)
    
    # Удаляем существующие handlers
    logger.handlers.clear()
    
    # File handler
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    
    return logger


@dataclass(frozen=True)
class GenerateScheduleCommand:

    calendar_id: int
    variants_count: int
    time_limit_seconds: int
    draft_id: Optional[int] = None
    use_draft_as_locks: bool = False
    base_variant_id: Optional[int] = None
    use_base_variant_as_locks: bool = False
    random_seed: Optional[int] = None

    def __post_init__(self) -> None:
        if int(self.calendar_id) <= 0:
            raise ValidationError("calendar_id должен быть положительным числом.")
        if int(self.variants_count) <= 0:
            raise ValidationError("Количество вариантов должно быть больше 0.")
        if int(self.time_limit_seconds) <= 0:
            raise ValidationError("Лимит времени должен быть больше 0.")
        if self.draft_id is not None and int(self.draft_id) <= 0:
            raise ValidationError("draft_id должен быть положительным числом.")
        if self.base_variant_id is not None and int(self.base_variant_id) <= 0:
            raise ValidationError("base_variant_id должен быть положительным числом.")
        if self.random_seed is not None and int(self.random_seed) <= 0:
            raise ValidationError("random_seed должен быть положительным числом.")


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
    AUTO_PLACEHOLDER_RETRY_LIMIT = 1

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

    def _resolve_random_seed(self, command: GenerateScheduleCommand) -> int:
        explicit_seed = getattr(command, "random_seed", None)
        if explicit_seed is not None:
            return self._positive_int(explicit_seed, 1)

        return self._positive_int(getattr(self._config, "solver_random_seed", 1), 1)

    def _load_existing_solution_entries(self, calendar_id: int) -> list[list[object]]:
        excluded_solutions: list[list[object]] = []
        variants = list(self._schedule_repo.list_variants(calendar_id=int(calendar_id)) or [])
        for variant in variants:
            variant_id = self._positive_int(getattr(variant, "id_variant", 0), 0)
            if variant_id <= 0:
                continue
            entries = list(self._schedule_repo.list_entries(int(variant_id)) or [])
            if entries:
                excluded_solutions.append(entries)
        return excluded_solutions

    def _next_variant_number(self, calendar_id: int) -> int:
        max_number = 0
        variants = list(self._schedule_repo.list_variants(calendar_id=int(calendar_id)) or [])
        for variant in variants:
            name = str(getattr(variant, "name", "") or "")
            match = re.search(r"(?:^|_)variant_(\d+)(?:\D.*)?$", name)
            if match:
                max_number = max(max_number, self._positive_int(match.group(1), 0))
        return max_number + 1 if max_number > 0 else len(variants) + 1

    def _draft_name_suffix(self, calendar_id: int, command: GenerateScheduleCommand) -> str:
        if not bool(getattr(command, "use_draft_as_locks", False)) or not getattr(command, "draft_id", None):
            return ""

        draft_id = self._positive_int(getattr(command, "draft_id", 0), 0)
        if draft_id <= 0:
            return ""

        for draft in list(self._schedule_repo.list_generation_drafts(calendar_id=int(calendar_id)) or []):
            if self._positive_int(getattr(draft, "id_draft", 0), 0) != draft_id:
                continue
            draft_name = str(getattr(draft, "name", "") or "").strip()
            if not draft_name:
                return ""
            safe_name = re.sub(r"\s+", "_", draft_name)
            safe_name = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_-]+", "", safe_name)
            return f"_{safe_name}" if safe_name else ""

        return ""

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

    def _build_base_variant_locks(self, base_variant_id: int) -> list[object]:
        entries = list(self._schedule_repo.list_entries(int(base_variant_id)) or [])
        locks: list[object] = []
        for entry in entries:
            event_id = self._positive_int(getattr(entry, "event_id", 0), 0)
            if event_id <= 0:
                continue
            locks.append(
                SimpleNamespace(
                    event_id=int(event_id),
                    slot_id=self._positive_int(getattr(entry, "slot_id", 0), 0),
                    teacher_id=self._positive_int(getattr(entry, "teacher_id", 0), 0),
                    room_id=self._positive_int(getattr(entry, "room_id", 0), 0),
                )
            )
        return locks

    def _build_draft_locks(self, draft_id: int) -> list[object]:
        entries = list(self._schedule_repo.list_generation_draft_entries(int(draft_id)) or [])
        locks: list[object] = []
        for entry in entries:
            event_id = self._positive_int(getattr(entry, "event_id", 0), 0)
            if event_id <= 0:
                continue
            locks.append(
                SimpleNamespace(
                    event_id=int(event_id),
                    slot_id=self._positive_int(getattr(entry, "slot_id", 0), 0),
                    teacher_id=self._positive_int(getattr(entry, "teacher_id", 0), 0)
                    if getattr(entry, "teacher_id", None) is not None
                    else None,
                    room_id=self._positive_int(getattr(entry, "room_id", 0), 0)
                    if getattr(entry, "room_id", None) is not None
                    else None,
                )
            )
        return locks

    def _unique_teacher_name(self, subject_name: str) -> str:
        base_name = f"Преподаватель {str(subject_name or '').strip()}"
        idx = 1
        while True:
            candidate = f"{base_name}{idx}"
            if self._teachers_repo.get_by_full_name(candidate) is None:
                return candidate
            idx += 1

    def _unique_room_name(self, room_type: str) -> str:
        existing = {str(getattr(room, "room_number", "") or "") for room in self._rooms_repo.list_all()}
        idx = 1
        while True:
            candidate = f"Аудитория для {room_type} {idx}"
            if candidate not in existing:
                return candidate
            idx += 1

    def _create_event_placeholders_from_diagnostics(self, diagnostics: dict, calendar_id: int) -> tuple[int, int]:
        created_teachers = 0
        created_rooms = 0
        created_teacher_keys: set[tuple[int, str]] = set()
        created_room_types: set[str] = set()

        for item in list(diagnostics.get("event_option_summary", []) or []):
            subject_id = self._positive_int(item.get("subject_id", 0), 0)
            subject_name = str(item.get("subject_name", "") or f"ID={subject_id}")
            part_type = str(item.get("part_type", "") or "practice")
            has_missing_teacher = bool(item.get("has_missing_teacher_option", False))
            has_missing_room = bool(item.get("has_missing_room_option", False))

            if has_missing_teacher and subject_id > 0:
                key = (subject_id, part_type)
                if key not in created_teacher_keys:
                    teacher_id = self._teachers_repo.create(
                        full_name=self._unique_teacher_name(subject_name),
                        hard_max=6,
                        soft_max=4,
                        needs_method_day=False,
                        commentary="Автоматически добавлен при повторной генерации по проблемному событию.",
                    )
                    self._teachers_repo.replace_teacher_subject_rules(
                        int(teacher_id),
                        [
                            {
                                "subject_id": int(subject_id),
                                "can_lecture": part_type == "lecture",
                                "can_practice": part_type == "practice",
                                "can_computer_practice": part_type == "computer_practice",
                                "can_lab": part_type == "lab",
                            }
                        ],
                    )
                    self._teachers_repo.replace_teacher_availability_grid(
                        teacher_id=int(teacher_id),
                        calendar_id=int(calendar_id),
                        unavailable_cells=set(),
                    )
                    created_teacher_keys.add(key)
                    created_teachers += 1

            if has_missing_room:
                required_room_type = "classroom"
                if part_type == "lecture":
                    required_room_type = "lecture"
                elif part_type == "computer_practice":
                    required_room_type = "computer"
                elif part_type == "lab":
                    required_room_type = "lab"
                if required_room_type not in created_room_types:
                    self._rooms_repo.create(
                        room_number=self._unique_room_name(required_room_type),
                        room_type=required_room_type,
                        room_types=[required_room_type],
                        capacity=35,
                        building="Автозаглушка",
                    )
                    created_room_types.add(required_room_type)
                    created_rooms += 1

        return created_teachers, created_rooms

    def _create_capacity_teacher_placeholders_from_diagnostics(
        self,
        diagnostics: dict,
        calendar_id: int,
    ) -> int:
        created_teachers = 0
        created_teacher_keys: set[tuple[int, str]] = set()

        candidates: dict[tuple[int, str], dict] = {}
        for item in list(diagnostics.get("teacher_pool_bottlenecks", []) or []):
            subject_id = self._positive_int(item.get("subject_id", 0), 0)
            part_type = str(item.get("part_type", "") or "practice")
            events_count = self._positive_int(item.get("events_count", 0), 0)
            teacher_count = self._positive_int(item.get("candidate_teachers", 0), 0)
            if subject_id <= 0 or teacher_count > 1 or events_count < 2:
                continue
            candidates.setdefault((subject_id, part_type), item)

        for item in list(diagnostics.get("teacher_slot_bottlenecks", []) or []):
            subject_id = self._positive_int(item.get("subject_id", 0), 0)
            part_type = str(item.get("part_type", "") or "practice")
            load_ratio = float(item.get("load_ratio", 0) or 0)
            teacher_count = self._positive_int(item.get("candidate_teachers", 0), 0)
            if subject_id <= 0 or teacher_count > 1 or load_ratio < 0.03:
                continue
            candidates.setdefault((subject_id, part_type), item)

        for (subject_id, part_type), item in sorted(candidates.items())[:40]:
            key = (int(subject_id), str(part_type))
            if key in created_teacher_keys:
                continue

            subject_name = str(item.get("subject_name", "") or f"ID={subject_id}")
            teacher_id = self._teachers_repo.create(
                full_name=self._unique_teacher_name(subject_name),
                hard_max=6,
                soft_max=4,
                needs_method_day=False,
                commentary="Автоматически добавлен при повторной генерации из-за дефицита преподавательского ресурса.",
            )
            self._teachers_repo.replace_teacher_subject_rules(
                int(teacher_id),
                [
                    {
                        "subject_id": int(subject_id),
                        "can_lecture": part_type == "lecture",
                        "can_practice": part_type == "practice",
                        "can_computer_practice": part_type == "computer_practice",
                        "can_lab": part_type == "lab",
                    }
                ],
            )
            self._teachers_repo.replace_teacher_availability_grid(
                teacher_id=int(teacher_id),
                calendar_id=int(calendar_id),
                unavailable_cells=set(),
            )
            created_teacher_keys.add(key)
            created_teachers += 1

        return created_teachers

    def _repair_auto_placeholder_availability(self, calendar_id: int) -> int:
        slots = list(self._calendar_repo.list_time_slots(int(calendar_id)) or [])
        if not slots:
            return 0

        teacher_availability = self._teachers_repo.get_availability_matrix(int(calendar_id))
        slot_count = len(slots)
        repaired = 0

        for teacher in self._teachers_repo.list_all():
            teacher_id = self._positive_int(getattr(teacher, "id_teacher", 0), 0)
            if teacher_id <= 0:
                continue
            commentary = str(getattr(teacher, "commentary", "") or "").lower()
            full_name = str(getattr(teacher, "full_name", "") or "")
            is_auto_placeholder = (
                "автоматически добавлен" in commentary
                or full_name.startswith("Преподаватель ")
            )
            if not is_auto_placeholder:
                continue

            rows_count = sum(1 for tid, _sid in teacher_availability.keys() if int(tid) == teacher_id)
            if rows_count >= slot_count:
                continue

            self._teachers_repo.replace_teacher_availability_grid(
                teacher_id=teacher_id,
                calendar_id=int(calendar_id),
                unavailable_cells=set(),
            )
            repaired += 1

        return repaired

    @staticmethod
    def _detect_subgroup_kind(subject_name: str) -> str:
        name = str(subject_name or "").strip().lower()
        if re.search(r"п\s*/\s*гр\.?\s*1", name):
            return "subgroup_1"
        if re.search(r"п\s*/\s*гр\.?\s*2", name):
            return "subgroup_2"
        if re.search(r"(?:^|[\s(\[\{])1\s*п\s*г\b", name):
            return "subgroup_1"
        if re.search(r"(?:^|[\s(\[\{])2\s*п\s*г\b", name):
            return "subgroup_2"
        if re.search(r"подгрупп\w*\s*1", name):
            return "subgroup_1"
        if re.search(r"подгрупп\w*\s*2", name):
            return "subgroup_2"
        return "none"

    def _build_generation_diagnostics(
        self,
        *,
        calendar_id: int,
        events: list,
        teachers: list,
        groups: list,
        rooms: list,
        slots: list,
        subject_names_by_id: dict[int, str],
        teacher_subjects: dict,
        teacher_availability: dict,
        teacher_group_assignments: dict,
        room_subject_assignments: dict,
    ) -> dict:
        group_by_id = {
            self._positive_int(getattr(group, "id_group", 0), 0): group
            for group in groups
        }
        slots_by_week_type: dict[int, list] = defaultdict(list)
        for slot in slots:
            if bool(getattr(slot, "is_lunch_break", False)):
                continue
            week_type = self._positive_int(getattr(slot, "week_type", 0), 0)
            if week_type > 0:
                slots_by_week_type[week_type].append(slot)

        teacher_availability_rows = Counter(int(tid) for tid, _sid in teacher_availability.keys())
        slot_count = len(slots)
        missing_availability_teachers = []
        for teacher in teachers:
            teacher_id = self._positive_int(getattr(teacher, "id_teacher", 0), 0)
            rows_count = int(teacher_availability_rows.get(teacher_id, 0))
            if slot_count and rows_count != slot_count:
                missing_availability_teachers.append(
                    {
                        "teacher_id": teacher_id,
                        "full_name": str(getattr(teacher, "full_name", "") or ""),
                        "availability_rows": rows_count,
                        "expected_rows": slot_count,
                    }
                )

        local_resource_issues = []
        group_week_common_load = Counter()
        group_week_subgroup_load = Counter()
        subject_part_week_events = Counter()
        subject_part_candidate_teachers: dict[tuple[int, str], set[int]] = defaultdict(set)
        subject_part_week_teacher_slots: dict[tuple[int, str, int], set[tuple[int, int]]] = defaultdict(set)
        room_type_week_events = Counter()

        for event in events:
            event_id = self._positive_int(getattr(event, "id_event", 0), 0)
            subject_id = self._positive_int(getattr(event, "subject_id", 0), 0)
            subject_name = str(subject_names_by_id.get(subject_id, "") or f"ID={subject_id}")
            part_type = str(getattr(event, "part_type", "") or "")
            week_type = self._positive_int(getattr(event, "fixed_week_type", 0), 0)
            group_ids = [
                self._positive_int(gid, 0)
                for gid in list(getattr(event, "group_ids", []) or [getattr(event, "group_id", 0)])
                if self._positive_int(gid, 0) > 0
            ]
            subgroup_kind = self._detect_subgroup_kind(subject_name)
            for group_id in group_ids:
                if subgroup_kind == "none":
                    group_week_common_load[(group_id, week_type)] += 1
                else:
                    group_week_subgroup_load[(group_id, week_type, subgroup_kind)] += 1

            subject_part_week_events[(subject_id, part_type, week_type)] += 1
            required_room_type = str(getattr(event, "required_room_type", "") or "").strip().lower()
            room_type_week_events[(required_room_type, week_type)] += 1

            total_group_size = sum(
                self._positive_int(getattr(group_by_id.get(group_id), "quantity", 0), 0)
                for group_id in group_ids
            )
            candidate_teachers = []
            for teacher in teachers:
                teacher_id = self._positive_int(getattr(teacher, "id_teacher", 0), 0)
                if not teacher_subjects.get((teacher_id, subject_id, part_type), False):
                    continue
                assigned_groups = teacher_group_assignments.get(teacher_id, set())
                if assigned_groups and not all(int(gid) in assigned_groups for gid in group_ids):
                    continue
                candidate_teachers.append(teacher)
                subject_part_candidate_teachers[(subject_id, part_type)].add(teacher_id)

            candidate_rooms = []
            for room in rooms:
                room_id = self._positive_int(getattr(room, "id_room", 0), 0)
                room_types = Room.parse_room_types(room)
                if required_room_type not in room_types:
                    continue
                if self._positive_int(getattr(room, "capacity", 0), 0) < total_group_size:
                    continue
                assigned_subjects = room_subject_assignments.get(room_id, set())
                if assigned_subjects and subject_id not in assigned_subjects:
                    continue
                candidate_rooms.append(room)

            candidate_slots = slots_by_week_type.get(week_type, [])
            availability_slots = 0
            if candidate_teachers:
                for slot in candidate_slots:
                    slot_id = self._positive_int(getattr(slot, "id_slot", 0), 0)
                    available_teacher_ids = [
                        self._positive_int(getattr(teacher, "id_teacher", 0), 0)
                        for teacher in candidate_teachers
                        if teacher_availability.get(
                            (self._positive_int(getattr(teacher, "id_teacher", 0), 0), slot_id),
                            True,
                        )
                    ]
                    if available_teacher_ids:
                        availability_slots += 1
                    for teacher_id in available_teacher_ids:
                        subject_part_week_teacher_slots[(subject_id, part_type, week_type)].add(
                            (teacher_id, slot_id)
                        )

            if not candidate_teachers or not candidate_rooms or not candidate_slots or (candidate_teachers and availability_slots == 0):
                local_resource_issues.append(
                    {
                        "event_id": event_id,
                        "subject_id": subject_id,
                        "subject_name": subject_name,
                        "part_type": part_type,
                        "week_type": week_type,
                        "group_ids": group_ids,
                        "candidate_teachers": len(candidate_teachers),
                        "candidate_rooms": len(candidate_rooms),
                        "candidate_slots": len(candidate_slots),
                        "availability_slots": availability_slots,
                    }
                )

        teacher_slot_bottlenecks = []
        for (subject_id, part_type, week_type), events_count in sorted(subject_part_week_events.items()):
            teacher_slots = subject_part_week_teacher_slots.get((subject_id, part_type, week_type), set())
            teacher_count = len(subject_part_candidate_teachers.get((subject_id, part_type), set()))
            if not teacher_slots:
                continue
            slot_capacity = len(teacher_slots)
            tight_ratio = events_count / max(1, slot_capacity)
            if tight_ratio >= 0.5 or teacher_count <= 1:
                teacher_slot_bottlenecks.append(
                    {
                        "subject_id": subject_id,
                        "subject_name": str(subject_names_by_id.get(subject_id, "") or f"ID={subject_id}"),
                        "part_type": part_type,
                        "week_type": week_type,
                        "events_count": int(events_count),
                        "candidate_teachers": int(teacher_count),
                        "teacher_slot_capacity": int(slot_capacity),
                        "load_ratio": round(float(tight_ratio), 3),
                    }
                )

        teacher_slot_bottlenecks.sort(
            key=lambda item: (
                -float(item.get("load_ratio", 0)),
                int(item.get("candidate_teachers", 0)),
                -int(item.get("events_count", 0)),
            )
        )

        teacher_pool_bottlenecks = []
        for (subject_id, part_type, week_type), events_count in sorted(subject_part_week_events.items()):
            teacher_count = len(subject_part_candidate_teachers.get((subject_id, part_type), set()))
            if teacher_count <= 2 or events_count > teacher_count * 12:
                teacher_pool_bottlenecks.append(
                    {
                        "subject_id": subject_id,
                        "subject_name": str(subject_names_by_id.get(subject_id, "") or f"ID={subject_id}"),
                        "part_type": part_type,
                        "week_type": week_type,
                        "events_count": int(events_count),
                        "candidate_teachers": int(teacher_count),
                    }
                )

        group_load_summary = []
        for (group_id, week_type), common_count in sorted(group_week_common_load.items()):
            group = group_by_id.get(group_id)
            subgroup_count = sum(
                count
                for (gid, wt, _kind), count in group_week_subgroup_load.items()
                if int(gid) == int(group_id) and int(wt) == int(week_type)
            )
            group_load_summary.append(
                {
                    "group_id": group_id,
                    "group_name": str(getattr(group, "group_name", "") or f"id={group_id}"),
                    "week_type": week_type,
                    "common_events": int(common_count),
                    "subgroup_events": int(subgroup_count),
                    "min_pairs_per_active_day": min_pairs_per_active_day_for_group(group, default=2),
                    "hard_common_capacity": 25,
                    "over_common_capacity": int(common_count) > 25,
                }
            )

        return {
            "missing_availability_teachers": missing_availability_teachers[:20],
            "missing_availability_teachers_count": len(missing_availability_teachers),
            "local_resource_issues": local_resource_issues[:20],
            "local_resource_issues_count": len(local_resource_issues),
            "teacher_pool_bottlenecks": teacher_pool_bottlenecks[:30],
            "teacher_slot_bottlenecks": teacher_slot_bottlenecks[:30],
            "group_load_summary": group_load_summary,
        }

    def execute(
        self,
        command: GenerateScheduleCommand,
        progress_cb: ProgressCallback = None,
    ) -> GenerationResultDTO:
        return self._execute_internal(command, progress_cb, auto_retry_left=self.AUTO_PLACEHOLDER_RETRY_LIMIT)

    def _execute_internal(
        self,
        command: GenerateScheduleCommand,
        progress_cb: ProgressCallback,
        *,
        auto_retry_left: int,
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
            random_seed=getattr(command, "random_seed", None),
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

        if not weekly_plans:
            self._emit(
                progress_cb,
                "weekly_plans_missing",
                fallback="semester_plan",
            )

        teachers = self._teachers_repo.list_all()
        subjects = self._subjects_repo.list_all()
        groups = self._groups_repo.list_all()
        rooms = self._rooms_repo.list_all()
        slots = self._calendar_repo.list_time_slots(calendar_id)

        subject_names_by_id = {
            int(getattr(subject, "id_subject", 0) or 0): str(
                getattr(subject, "subject_name", "") or ""
            )
            for subject in subjects
        }

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

        locks = list(self._schedule_repo.list_locks_for_calendar(calendar_id) or [])
        if bool(getattr(command, "use_draft_as_locks", False)) and getattr(command, "draft_id", None):
            locks.extend(self._build_draft_locks(int(command.draft_id)))
        if bool(getattr(command, "use_base_variant_as_locks", False)) and getattr(command, "base_variant_id", None):
            locks.extend(self._build_base_variant_locks(int(command.base_variant_id)))

        self._emit(
            progress_cb,
            "rules_loaded",
            rules_profile=self.BASE_RULE_PROFILE_KEY,
            locks_count=len(locks),
        )

        teacher_subjects = self._teachers_repo.get_teacher_part_matrix()
        teacher_group_assignments = self._teachers_repo.get_teacher_group_assignments()
        room_subject_assignments = self._rooms_repo.get_room_subject_assignments()
        teacher_availability = self._teachers_repo.get_availability_matrix(calendar_id)

        self._emit(
            progress_cb,
            "availability_loaded",
            teacher_subject_links=len(teacher_subjects),
            availability_links=len(teacher_availability),
        )

        repaired_placeholder_teachers = self._repair_auto_placeholder_availability(calendar_id)
        if repaired_placeholder_teachers:
            teacher_availability = self._teachers_repo.get_availability_matrix(calendar_id)
            self._emit(
                progress_cb,
                "auto_placeholder_availability_repaired",
                teachers_count=repaired_placeholder_teachers,
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

        generation_diagnostics = self._build_generation_diagnostics(
            calendar_id=calendar_id,
            events=events,
            teachers=teachers,
            groups=groups,
            rooms=rooms,
            slots=slots,
            subject_names_by_id=subject_names_by_id,
            teacher_subjects=teacher_subjects,
            teacher_availability=teacher_availability,
            teacher_group_assignments=teacher_group_assignments,
            room_subject_assignments=room_subject_assignments,
        )
        self._emit(
            progress_cb,
            "pre_solver_diagnostics",
            **generation_diagnostics,
        )

        if auto_retry_left > 0:
            created_capacity_teachers = self._create_capacity_teacher_placeholders_from_diagnostics(
                generation_diagnostics,
                calendar_id=calendar_id,
            )
            if created_capacity_teachers:
                self._emit(
                    progress_cb,
                    "auto_capacity_placeholders_added",
                    created_teachers=created_capacity_teachers,
                )
                return self._execute_internal(
                    command,
                    progress_cb,
                    auto_retry_left=auto_retry_left - 1,
                )

        # Сохраняем generation events, чтобы downstream-слои
        # работали с тем же набором исходных данных.
        self._schedule_repo.set_generation_events(events)

        excluded_solutions = self._load_existing_solution_entries(calendar_id)
        random_seed = self._resolve_random_seed(command)

        self._emit(
            progress_cb,
            "solver_started",
            k_solutions=variants_count,
            time_limit_seconds=time_limit_seconds,
            random_seed=random_seed,
            excluded_existing_variants=len(excluded_solutions),
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
                subject_names_by_id=subject_names_by_id,
                teacher_group_assignments=teacher_group_assignments,
                room_subject_assignments=room_subject_assignments,
                excluded_solutions=excluded_solutions,
            )
        except ValidationError:
            raise
        except SolverInfeasibleError as exc:
            diagnostics = getattr(exc, "diagnostics", {}) or {}
            if diagnostics:
                self._emit(
                    progress_cb,
                    "solver_infeasible_diagnostics",
                    **diagnostics,
                )
            if auto_retry_left > 0:
                created_teachers, created_rooms = self._create_event_placeholders_from_diagnostics(
                    diagnostics,
                    calendar_id=calendar_id,
                )
                if created_teachers or created_rooms:
                    self._emit(
                        progress_cb,
                        "auto_placeholders_added",
                        created_teachers=created_teachers,
                        created_rooms=created_rooms,
                    )
                    return self._execute_internal(
                        command,
                        progress_cb,
                        auto_retry_left=auto_retry_left - 1,
                    )
            solver_error = SolverError(str(exc))
            solver_error.diagnostics = diagnostics
            raise solver_error from exc
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
        next_variant_number = self._next_variant_number(calendar_id)
        draft_suffix = self._draft_name_suffix(calendar_id, command)

        for idx, solution in enumerate(solutions, start=1):
            solution_entries = list(getattr(solution, "entries", []) or [])
            objective_value = self._positive_int(
                getattr(solution, "objective_value", 0),
                default=0,
            )

            variant_number = next_variant_number + idx - 1
            variant_name = (
                f"{academic_year}_semester_{semester}_variant_{variant_number}{draft_suffix}"
                if academic_year
                else f"semester_{semester}_variant_{variant_number}{draft_suffix}"
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

                # Настраиваем логгер для этого варианта
                logger = setup_generation_logger(int(variant_id))
                logger.info(f"Начало сохранения варианта #{idx}")
                logger.info(f"Variant ID: {variant_id}")
                logger.info(f"Variant name: {variant_name}")
                logger.info(f"Calendar ID: {calendar_id}")
                logger.info(f"Objective score: {objective_value}")
                logger.info(f"Solution entries count: {len(solution_entries)}")

                self._schedule_repo.save_solution_entries(
                    variant_id=int(variant_id),
                    solution_entries=solution_entries,
                )

                logger.info("Solution entries сохранены")

                variant_dto = self._schedule_repo.get_variant_dto(int(variant_id))
                
                logger.info(f"Variant DTO получен, entries: {len(getattr(variant_dto, 'entries', []) or [])}")
                logger.info("Генерация варианта завершена успешно")
                
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
