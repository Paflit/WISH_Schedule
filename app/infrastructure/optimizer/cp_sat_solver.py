from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import random
import re
from typing import DefaultDict, Dict, Iterable, List, Optional, Tuple

from ortools.sat.python import cp_model

from app.domain.exceptions import SolverError, ValidationError
from app.domain.models import (
    CurriculumItem,
    Room,
    Solution,
    SolutionEntry,
    StudentGroup,
    Teacher,
    TimeSlot,
)
from app.domain.rules import SchedulingRules

# ============================================================
# Константы и helpers
# ============================================================

MAX_ROOMS_PER_EVENT = 4
MAX_SLOTS_PER_EVENT = 32

# Чем меньше число — тем более специализированная аудитория.
ROOM_SPECIALIZATION_RANK = {
    "lab": 1,
    "computer": 2,
    "lecture": 3,
    "classroom": 4,
}
VALID_ROOM_TYPES = set(ROOM_SPECIALIZATION_RANK.keys())

def _positive_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _optional_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None

def _parse_room_types(room: Room | None) -> set[str]:
    result = Room.parse_room_types(room)
    return {x for x in result if x in VALID_ROOM_TYPES}


def _room_matches_required(room: Room, required_room_type: str) -> bool:
    required = str(required_room_type or "").strip().lower()
    if required not in VALID_ROOM_TYPES:
        return False
    return required in _parse_room_types(room)


def _room_priority_penalty(room: Room, required_room_type: str) -> int:
    """
    Меньше — лучше.

    Логика:
    - если аудитория не поддерживает требуемый тип -> большой штраф;
    - если поддерживает, то штраф зависит от того, насколько аудитория "слишком специализирована" для этой задачи.
    """
    required = str(required_room_type or "").strip().lower()
    if required not in VALID_ROOM_TYPES:
        return 10_000

    room_types = _parse_room_types(room)
    if required not in room_types:
        return 10_000

    required_rank = ROOM_SPECIALIZATION_RANK[required]

    # Самый "сильный" тип аудитории = минимальный rank.
    strongest_room_rank = min(
        (ROOM_SPECIALIZATION_RANK[t] for t in room_types if t in ROOM_SPECIALIZATION_RANK),
        default=999,
    )

    if strongest_room_rank == 999:
        return 10_000

    # Если аудитория более специализирована, чем нужно,
    # даём штраф за перерасход ресурса.
    return max(0, required_rank - strongest_room_rank)

def _day_key(slot: TimeSlot) -> Tuple[int, int]:
    """
    Для генерации шаблонного расписания работаем на уровне двух чередующихся
    недель, поэтому ограничения должны различать именно тип недели.
    """
    return (
        _positive_int(getattr(slot, "week_type", 0)),
        _positive_int(getattr(slot, "day_of_week", 0)),
    )


def _sample_slots_evenly(slots: List[TimeSlot], limit: int) -> List[TimeSlot]:
    """
    Сокращает список слотов, стараясь сохранить равномерное покрытие семестра.
    Простое усечение первых N слотов приводит к перекосу в начало семестра
    и ухудшает качество/реализуемость модели. Здесь берём слоты равномерно
    по отсортированному списку.
    """
    if limit <= 0 or len(slots) <= limit:
        return list(slots)

    if limit == 1:
        return [slots[0]]

    result: List[TimeSlot] = []
    last_index = len(slots) - 1
    for i in range(limit):
        idx = round(i * last_index / (limit - 1))
        result.append(slots[idx])

    # Убираем возможные дубли после round, сохраняя порядок.
    seen: set[int] = set()
    unique_result: List[TimeSlot] = []
    for slot in result:
        slot_id = _positive_int(getattr(slot, "id_slot", 0))
        if slot_id in seen:
            continue
        seen.add(slot_id)
        unique_result.append(slot)

    if len(unique_result) == limit:
        return unique_result

    for slot in slots:
        slot_id = _positive_int(getattr(slot, "id_slot", 0))
        if slot_id in seen:
            continue
        seen.add(slot_id)
        unique_result.append(slot)
        if len(unique_result) >= limit:
            break

    return unique_result[:limit]


def _canonical_template_slots(slots: List[TimeSlot]) -> List[TimeSlot]:
    """
    Оставляет по одному репрезентативному слоту на каждую комбинацию (week_type, day_of_week, pair_number).
    Это переводит solver с уровня всех недель семестра на уровень шаблона
    двух чередующихся недель.
    """
    result: List[TimeSlot] = []
    seen: set[tuple[int, int, int]] = set()

    for slot in sorted(
        slots,
        key=lambda s: (
            _positive_int(getattr(s, "week_number_in_semester", 0)),
            _positive_int(getattr(s, "week_type", 0)),
            _positive_int(getattr(s, "day_of_week", 0)),
            _positive_int(getattr(s, "pair_number", 0)),
            _positive_int(getattr(s, "id_slot", 0)),
        ),
    ):
        key = (
            _positive_int(getattr(slot, "week_type", 0)),
            _positive_int(getattr(slot, "day_of_week", 0)),
            _positive_int(getattr(slot, "pair_number", 0)),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(slot)

    return result


def _detect_subgroup_kind(subject_name: str) -> str:
    name = str(subject_name or "").strip().lower()
    if not name:
        return "none"

    if re.search(r"п\s*/\s*гр\.?\s*1", name):
        return "subgroup_1"
    if re.search(r"п\s*/\s*гр\.?\s*2", name):
        return "subgroup_2"
    return "none"


def _or_bool(
    model: cp_model.CpModel,
    lits: List[cp_model.IntVar],
    name: str,
) -> cp_model.IntVar:
    b = model.NewBoolVar(name)
    if not lits:
        model.Add(b == 0)
    else:
        model.AddMaxEquality(b, lits)
    return b


def _gaps_for_day(
    model: cp_model.CpModel,
    occupied_by_pair: Dict[int, cp_model.IntVar],
    max_pair: int,
    name_prefix: str,
    allow_lunch_gap: bool,
    lunch_min: int,
    lunch_max: int,
) -> cp_model.IntVar:
    y: List[cp_model.IntVar] = []
    for p in range(1, max_pair + 1):
        y.append(occupied_by_pair.get(p, model.NewConstant(0)))

    before_any: Dict[int, cp_model.IntVar] = {}
    after_any: Dict[int, cp_model.IntVar] = {}

    for p in range(1, max_pair + 1):
        before_any[p] = _or_bool(model, y[: p - 1], f"{name_prefix}_before_{p}")
        after_any[p] = _or_bool(model, y[p:], f"{name_prefix}_after_{p}")

    gap_vars: List[cp_model.IntVar] = []
    for p in range(1, max_pair + 1):
        if allow_lunch_gap and lunch_min <= p <= lunch_max:
            continue

        occupied = y[p - 1]
        gp = model.NewBoolVar(f"{name_prefix}_gap_{p}")

        model.Add(gp <= before_any[p])
        model.Add(gp <= after_any[p])
        model.Add(gp <= 1 - occupied)
        model.Add(gp >= before_any[p] + after_any[p] + (1 - occupied) - 2)

        gap_vars.append(gp)

    gaps = model.NewIntVar(0, max_pair, f"{name_prefix}_gaps_total")
    if gap_vars:
        model.Add(gaps == sum(gap_vars))
    else:
        model.Add(gaps == 0)
    return gaps


@dataclass(frozen=True)
class ScheduleLock:
    event_id: int
    slot_id: Optional[int] = None
    teacher_id: Optional[int] = None
    room_id: Optional[int] = None


@dataclass(frozen=True)
class FeasibilityIssue:
    event_id: int
    reason: str
    subject_id: int
    subject_name: str
    part_type: str
    group_ids: Tuple[int, ...]
    group_names: Tuple[str, ...]
    candidate_teachers: int
    candidate_rooms: int
    candidate_slots: int


class _SolutionCollector(cp_model.CpSolverSolutionCallback):
    def __init__(
        self,
        x_vars: Dict[Tuple[int, int], cp_model.IntVar],
        event_options: Dict[int, List[Tuple[int, int, int, int]]],
        k_solutions: int,
    ):
        super().__init__()
        self._x_vars = x_vars
        self._event_options = event_options
        self._k_solutions = max(1, int(k_solutions))
        self.solutions: List[Solution] = []

    def on_solution_callback(self) -> None:
        entries: List[SolutionEntry] = []

        for eid, options in self._event_options.items():
            for idx, (slot_id, teacher_id, room_id, _room_penalty) in enumerate(options):
                var = self._x_vars[(eid, idx)]
                if self.Value(var):
                    entries.append(
                        SolutionEntry(
                            event_id=int(eid),
                            slot_id=int(slot_id),
                            teacher_id=int(teacher_id),
                            room_id=int(room_id),
                        )
                    )
                    break

        self.solutions.append(
            Solution(
                entries=entries,
                objective_value=int(self.ObjectiveValue()),
                meta={"status": "feasible"},
            )
        )

        if len(self.solutions) >= self._k_solutions:
            self.StopSearch()

class CPSatScheduleSolver:
    """
    Solver на OR-Tools CP-SAT.

    Вход:
    - events: generation events, построенные EventBuilder
    - curriculum: dict[curriculum_id] -> CurriculumItem
    - teacher_subjects: {(teacher_id, subject_id, part_type): bool}
    - teacher_availability: {(teacher_id, slot_id): bool}

    Выход:
    - список Solution, где каждый Solution содержит назначения event -> slot/teacher/room
    """

    def solve(
        self,
        teachers: List[Teacher],
        groups: List[StudentGroup],
        rooms: List[Room],
        slots: List[TimeSlot],
        curriculum: Dict[int, CurriculumItem],
        events: List[object],
        teacher_subjects: Dict[Tuple[int, int, str], bool],
        teacher_availability: Dict[Tuple[int, int], bool],
        rules: SchedulingRules,
        k_solutions: int,
        time_limit_seconds: int,
        random_seed: int,
        locks: Optional[List[ScheduleLock]] = None,
        subject_names_by_id: Optional[Dict[int, str]] = None,
    ) -> List[Solution]:
        if not events:
            return []

        if not teachers:
            raise ValidationError("Solver: список преподавателей пуст.")
        if not groups:
            raise ValidationError("Solver: список групп пуст.")
        if not rooms:
            raise ValidationError("Solver: список аудиторий пуст.")
        if not slots:
            raise ValidationError("Solver: список временных слотов пуст.")
        if not curriculum:
            raise ValidationError("Solver: curriculum map пуст.")

        k_solutions = max(1, _positive_int(k_solutions, 1))
        time_limit_seconds = max(1, _positive_int(time_limit_seconds, 30))
        random_seed = max(1, _positive_int(random_seed, 1))

        slots = _canonical_template_slots(slots)

        slot_by_id = {int(s.id_slot): s for s in slots}
        group_by_id = {int(g.id_group): g for g in groups}
        max_pair = max((_positive_int(getattr(s, "pair_number", 0)) for s in slots), default=0)

        study_slots = [s for s in slots if not bool(getattr(s, "is_lunch_break", False))]
        if not study_slots:
            raise ValidationError("Solver: нет учебных слотов (без обеденных перерывов).")

        lock_map: Dict[int, ScheduleLock] = {}
        for lk in locks or []:
            eid = _positive_int(getattr(lk, "event_id", 0))
            if eid > 0:
                lock_map[eid] = ScheduleLock(
                    event_id=eid,
                    slot_id=_optional_int(getattr(lk, "slot_id", None)),
                    teacher_id=_optional_int(getattr(lk, "teacher_id", None)),
                    room_id=_optional_int(getattr(lk, "room_id", None)),
                )

        slots_by_week_type: DefaultDict[int, List[TimeSlot]] = defaultdict(list)
        for s in study_slots:
            wt = _positive_int(getattr(s, "week_type", 0))
            slots_by_week_type[wt].append(s)

        event_options, feasibility_issues = self._build_event_options(
            teachers=teachers,
            groups=groups,
            rooms=rooms,
            slots=study_slots,
            slots_by_week_type=slots_by_week_type,
            curriculum=curriculum,
            events=events,
            teacher_subjects=teacher_subjects,
            teacher_availability=teacher_availability,
            group_by_id=group_by_id,
            lock_map=lock_map,
            subject_names_by_id=subject_names_by_id or {},
            random_seed=random_seed,
        )

        if feasibility_issues:
            raise ValidationError(self._format_feasibility_issues(feasibility_issues))

        if not event_options:
            raise ValidationError("Solver: после подготовки не осталось допустимых событий.")

        model = cp_model.CpModel()

        # x[(eid, idx)] = 1, если для события eid выбрана option idx
        x: Dict[Tuple[int, int], cp_model.IntVar] = {}
        for eid, options in event_options.items():
            for idx, _opt in enumerate(options):
                x[(eid, idx)] = model.NewBoolVar(f"x_e{eid}_o{idx}")

        event_slot_assigned: Dict[Tuple[int, int], cp_model.IntVar] = {}
        for eid, options in event_options.items():
            slot_to_lits: DefaultDict[int, List[cp_model.IntVar]] = defaultdict(list)
            for idx, (slot_id, _teacher_id, _room_id, _room_penalty) in enumerate(options):
                slot_to_lits[int(slot_id)].append(x[(eid, idx)])

            for slot_id, lits in slot_to_lits.items():
                event_slot_assigned[(eid, int(slot_id))] = _or_bool(
                    model,
                    lits,
                    f"event_{eid}_slot_{slot_id}_assigned",
                )

        # Каждое событие должно быть назначено ровно в одну опцию.
        for eid, options in event_options.items():
            model.Add(sum(x[(eid, idx)] for idx in range(len(options))) == 1)

        group_usage: DefaultDict[Tuple[int, int], List[cp_model.IntVar]] = defaultdict(list)
        teacher_usage: DefaultDict[Tuple[int, int], List[cp_model.IntVar]] = defaultdict(list)
        room_usage: DefaultDict[Tuple[int, int], List[cp_model.IntVar]] = defaultdict(list)

        # Для soft-ограничений собираем индексы по дням.
        group_day_pair_usage: DefaultDict[Tuple[int, Tuple[int, int], int], List[cp_model.IntVar]] = defaultdict(list)
        teacher_day_pair_usage: DefaultDict[Tuple[int, Tuple[int, int], int], List[cp_model.IntVar]] = defaultdict(list)
        group_day_usage_any: DefaultDict[Tuple[int, Tuple[int, int]], List[cp_model.IntVar]] = defaultdict(list)
        teacher_day_usage_any: DefaultDict[Tuple[int, Tuple[int, int]], List[cp_model.IntVar]] = defaultdict(list)

        room_penalty_terms: List[cp_model.LinearExpr] = []
        lecture_late_terms: List[cp_model.LinearExpr] = []

        for e in events:
            eid = _positive_int(getattr(e, "id_event", 0))
            if eid <= 0:
                continue

            group_ids = tuple(
                _positive_int(gid)
                for gid in list(getattr(e, "group_ids", []) or [getattr(e, "group_id", 0)])
                if _positive_int(gid) > 0
            )
            if not group_ids:
                group_ids = (_positive_int(getattr(e, "group_id", 0)),)

            part_type = str(getattr(e, "part_type", "") or "").strip()

            options = event_options[eid]
            for idx, (slot_id, teacher_id, room_id, room_penalty) in enumerate(options):
                lit = x[(eid, idx)]
                slot = slot_by_id[slot_id]
                daykey = _day_key(slot)
                pair_number = _positive_int(getattr(slot, "pair_number", 0))

                for gid in group_ids:
                    group_usage[(gid, slot_id)].append(lit)
                    group_day_pair_usage[(gid, daykey, pair_number)].append(lit)
                    group_day_usage_any[(gid, daykey)].append(lit)

                teacher_usage[(teacher_id, slot_id)].append(lit)
                room_usage[(room_id, slot_id)].append(lit)

                teacher_day_pair_usage[(teacher_id, daykey, pair_number)].append(lit)
                teacher_day_usage_any[(teacher_id, daykey)].append(lit)

                if room_penalty > 0:
                    room_penalty_terms.append(room_penalty * lit)

                lecture_preferred_last_pair = _positive_int(
                    getattr(rules, "lecture_preferred_last_pair", 2),
                    2,
                )
                if part_type == "lecture" and pair_number > lecture_preferred_last_pair:
                    lecture_late_terms.append((pair_number - lecture_preferred_last_pair) * lit)

        for _key, lits in group_usage.items():
            if len(lits) > 1:
                model.Add(sum(lits) <= 1)

        for _key, lits in teacher_usage.items():
            if len(lits) > 1:
                model.Add(sum(lits) <= 1)

        for _key, lits in room_usage.items():
            if len(lits) > 1:
                model.Add(sum(lits) <= 1)

        # Подгруппы: дисциплины с пометками п/гр.1 и п/гр.2 не должны идти подряд.
        subgroup_events: List[Tuple[int, Tuple[int, ...], str]] = []
        for e in events:
            eid = _positive_int(getattr(e, "id_event", 0))
            if eid <= 0:
                continue
            subject_id = _positive_int(getattr(e, "subject_id", 0))
            subject_name = str(subject_names_by_id.get(subject_id, "") or "")
            subgroup_kind = _detect_subgroup_kind(subject_name)
            if subgroup_kind == "none":
                continue
            group_ids = tuple(
                _positive_int(gid)
                for gid in list(getattr(e, "group_ids", []) or [getattr(e, "group_id", 0)])
                if _positive_int(gid) > 0
            )
            subgroup_events.append((eid, group_ids, subgroup_kind))

        if subgroup_events:
            event_by_id = {int(getattr(e, "id_event", 0)): e for e in events}
            slot_adjacent_pairs: List[Tuple[int, int]] = []
            for s1 in study_slots:
                for s2 in study_slots:
                    if _positive_int(getattr(s1, "id_slot", 0)) >= _positive_int(getattr(s2, "id_slot", 0)):
                        continue
                    if _positive_int(getattr(s1, "week_type", 0)) != _positive_int(getattr(s2, "week_type", 0)):
                        continue
                    if _positive_int(getattr(s1, "day_of_week", 0)) != _positive_int(getattr(s2, "day_of_week", 0)):
                        continue
                    if abs(
                        _positive_int(getattr(s1, "pair_number", 0))
                        - _positive_int(getattr(s2, "pair_number", 0))
                    ) != 1:
                        continue
                    slot_adjacent_pairs.append(
                        (
                            _positive_int(getattr(s1, "id_slot", 0)),
                            _positive_int(getattr(s2, "id_slot", 0)),
                        )
                    )

            for i in range(len(subgroup_events)):
                eid1, groups1, _kind1 = subgroup_events[i]
                for j in range(i + 1, len(subgroup_events)):
                    eid2, groups2, _kind2 = subgroup_events[j]
                    if not set(groups1).intersection(groups2):
                        continue
                    for slot1, slot2 in slot_adjacent_pairs:
                        lit1 = event_slot_assigned.get((eid1, slot1))
                        lit2 = event_slot_assigned.get((eid2, slot2))
                        if lit1 is not None and lit2 is not None:
                            model.Add(lit1 + lit2 <= 1)

                        lit1_rev = event_slot_assigned.get((eid1, slot2))
                        lit2_rev = event_slot_assigned.get((eid2, slot1))
                        if lit1_rev is not None and lit2_rev is not None:
                            model.Add(lit1_rev + lit2_rev <= 1)

        teacher_hard_max_pairs = max(
            1,
            _positive_int(getattr(rules, "teacher_hard_max_pairs", 6), 6),
        )

        for (teacher_id, daykey), lits in teacher_day_usage_any.items():
            if not lits:
                continue
            day_load = model.NewIntVar(
                0,
                max_pair if max_pair > 0 else len(lits),
                f"teacher_{teacher_id}_day_{daykey[0]}_{daykey[1]}_load",
            )
            model.Add(day_load == sum(lits))
            model.Add(day_load <= teacher_hard_max_pairs)

        objective_terms: List[cp_model.LinearExpr] = []

        # 1) Штраф за перерасход типа аудитории
        if room_penalty_terms:
            objective_terms.append(sum(room_penalty_terms))

        # 2) Лекции не слишком поздно
        if lecture_late_terms:
            objective_terms.append(
                _positive_int(getattr(rules, "w_lecture_late", 70), 70) * sum(lecture_late_terms)
            )

        # 3) Перегруз преподавателя сверх soft max
        teacher_soft_max_pairs = max(
            1,
            _positive_int(getattr(rules, "teacher_soft_max_pairs", 4), 4),
        )
        teacher_over_soft_terms: List[cp_model.LinearExpr] = []
        for (teacher_id, daykey), lits in teacher_day_usage_any.items():
            if not lits:
                continue

            day_load = model.NewIntVar(
                0,
                max_pair if max_pair > 0 else len(lits),
                f"teacher_soft_{teacher_id}_day_{daykey[0]}_{daykey[1]}_load",
            )
            model.Add(day_load == sum(lits))

            over = model.NewIntVar(
                0,
                max(0, max_pair - teacher_soft_max_pairs) if max_pair > 0 else len(lits),
                f"teacher_soft_{teacher_id}_day_{daykey[0]}_{daykey[1]}_over",
            )
            model.Add(over >= day_load - teacher_soft_max_pairs)
            model.Add(over >= 0)
            teacher_over_soft_terms.append(over)

        if teacher_over_soft_terms:
            objective_terms.append(
                _positive_int(getattr(rules, "w_teacher_over_soft", 700), 700)
                * sum(teacher_over_soft_terms)
            )

        # 4) Окна преподавателей
        teacher_gap_terms: List[cp_model.LinearExpr] = []
        for teacher in teachers:
            tid = _positive_int(getattr(teacher, "id_teacher", 0))
            if tid <= 0:
                continue

            for daykey in sorted({key[1] for key in teacher_day_pair_usage.keys() if key[0] == tid}):
                occupied_by_pair: Dict[int, cp_model.IntVar] = {}
                for pair in range(1, max_pair + 1):
                    lits = teacher_day_pair_usage.get((tid, daykey, pair), [])
                    if lits:
                        occupied_by_pair[pair] = _or_bool(
                            model,
                            lits,
                            f"teacher_{tid}_{daykey[0]}_{daykey[1]}_pair_{pair}_occ",
                        )

                if not occupied_by_pair:
                    continue

                gaps = _gaps_for_day(
                    model=model,
                    occupied_by_pair=occupied_by_pair,
                    max_pair=max_pair,
                    name_prefix=f"teacher_{tid}_{daykey[0]}_{daykey[1]}",
                    allow_lunch_gap=bool(getattr(rules, "allow_lunch_gap", True)),
                    lunch_min=_positive_int(getattr(rules, "lunch_gap_min_pair", 2), 2),
                    lunch_max=_positive_int(getattr(rules, "lunch_gap_max_pair", 3), 3),
                )
                teacher_gap_terms.append(gaps)

        if teacher_gap_terms:
            objective_terms.append(
                _positive_int(getattr(rules, "w_teacher_gaps", 150), 150)
                * sum(teacher_gap_terms)
            )

        # 5) Жесткие ограничения для студентов:
        #    - без окон;
        #    - от 2 до 5 пар в активный день;
        #    - не более 5 учебных дней в каждой шаблонной неделе.
        min_pairs_students_per_day = max(
            0,
            _positive_int(getattr(rules, "min_pairs_students_per_day", 2), 2),
        )
        max_pairs_students_per_day = max(
            1,
            _positive_int(getattr(rules, "max_pairs_students_per_day", 5), 5),
        )

        all_group_daykeys = sorted({key[1] for key in group_day_usage_any.keys()})
        all_week_types = sorted({daykey[0] for daykey in all_group_daykeys})
        all_days_of_week = sorted({daykey[1] for daykey in all_group_daykeys})

        student_gap_terms: List[cp_model.LinearExpr] = []
        student_day_load_terms: List[cp_model.LinearExpr] = []

        for group in groups:
            gid = _positive_int(getattr(group, "id_group", 0))
            if gid <= 0:
                continue

            used_day_flags: Dict[Tuple[int, int], cp_model.IntVar] = {}

            for daykey in sorted({key[1] for key in group_day_pair_usage.keys() if key[0] == gid}):
                occupied_by_pair: Dict[int, cp_model.IntVar] = {}
                for pair in range(1, max_pair + 1):
                    lits = group_day_pair_usage.get((gid, daykey, pair), [])
                    occupied_by_pair[pair] = _or_bool(
                        model,
                        lits,
                        f"group_{gid}_{daykey[0]}_{daykey[1]}_pair_{pair}_occ",
                    )

                has_day = _or_bool(
                    model,
                    group_day_usage_any.get((gid, daykey), []),
                    f"group_{gid}_{daykey[0]}_{daykey[1]}_has_day",
                )
                used_day_flags[daykey] = has_day

                day_load = model.NewIntVar(
                    0,
                    max_pair if max_pair > 0 else len(group_day_usage_any.get((gid, daykey), [])),
                    f"group_{gid}_{daykey[0]}_{daykey[1]}_load",
                )
                model.Add(day_load == sum(occupied_by_pair.values()))

                # Жесткое ограничение: если день активен, то 2..5 пар.
                model.Add(day_load >= min_pairs_students_per_day * has_day)
                model.Add(day_load <= max_pairs_students_per_day * has_day)

                # Жесткое отсутствие окон у студентов.
                gaps = _gaps_for_day(
                    model=model,
                    occupied_by_pair=occupied_by_pair,
                    max_pair=max_pair,
                    name_prefix=f"group_{gid}_{daykey[0]}_{daykey[1]}",
                    allow_lunch_gap=False,
                    lunch_min=0,
                    lunch_max=0,
                )
                model.Add(gaps == 0)
                student_gap_terms.append(gaps)

                # Soft-термы можно сохранить как нулевые для совместимости панели метрик.
                low = model.NewIntVar(
                    0,
                    max_pair,
                    f"group_{gid}_{daykey[0]}_{daykey[1]}_underload",
                )
                high = model.NewIntVar(
                    0,
                    max_pair,
                    f"group_{gid}_{daykey[0]}_{daykey[1]}_overload",
                )
                model.Add(low >= min_pairs_students_per_day * has_day - day_load)
                model.Add(low >= 0)
                model.Add(high >= day_load - max_pairs_students_per_day)
                model.Add(high >= 0)
                student_day_load_terms.append(low)
                student_day_load_terms.append(high)

            # Жесткое ограничение: не более 5 учебных дней в каждой шаблонной неделе.
            for wt in all_week_types:
                week_day_flags: List[cp_model.IntVar] = []
                for day in all_days_of_week:
                    daykey = (wt, day)
                    flag = used_day_flags.get(daykey)
                    if flag is None:
                        flag = model.NewBoolVar(f"group_{gid}_{wt}_{day}_has_day_const")
                        model.Add(flag == 0)
                    week_day_flags.append(flag)

                if len(week_day_flags) >= 5:
                    model.Add(sum(week_day_flags) <= 5)

        if student_day_load_terms:
            objective_terms.append(
                _positive_int(getattr(rules, "w_students_day_load", 500), 500)
                * sum(student_day_load_terms)
            )

        # 7) Методдень преподавателя: желательно иметь хотя бы один полностью свободный день
        if bool(getattr(rules, "consider_method_day", True)):
            all_daykeys = sorted({_day_key(s) for s in study_slots})
            method_day_terms: List[cp_model.LinearExpr] = []

            for teacher in teachers:
                tid = _positive_int(getattr(teacher, "id_teacher", 0))
                if tid <= 0:
                    continue
                if not bool(getattr(teacher, "needs_method_day", True)):
                    continue

                used_day_bools: List[cp_model.IntVar] = []
                for daykey in all_daykeys:
                    lits = teacher_day_usage_any.get((tid, daykey), [])
                    used_day_bools.append(
                        _or_bool(
                            model,
                            lits,
                            f"teacher_{tid}_{daykey[0]}_{daykey[1]}_used_day",
                        )
                    )

                if not used_day_bools:
                    continue

                days_used = model.NewIntVar(
                    0,
                    len(used_day_bools),
                    f"teacher_{tid}_days_used",
                )
                model.Add(days_used == sum(used_day_bools))

                no_method_day = model.NewIntVar(
                    0,
                    len(used_day_bools),
                    f"teacher_{tid}_no_method_day",
                )
                model.Add(no_method_day >= days_used - (len(used_day_bools) - 1))
                model.Add(no_method_day >= 0)
                method_day_terms.append(no_method_day)

            if method_day_terms:
                objective_terms.append(
                    _positive_int(getattr(rules, "w_method_day", 250), 250)
                    * sum(method_day_terms)
                )

        if objective_terms:
            model.Minimize(sum(objective_terms))
        else:
            model.Minimize(0)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit_seconds)
        solver.parameters.random_seed = int(random_seed)
        solver.parameters.num_search_workers = 8
        solver.parameters.log_search_progress = False

        collector = _SolutionCollector(
            x_vars=x,
            event_options=event_options,
            k_solutions=k_solutions,
        )

        status = solver.Solve(model, collector)

        if status not in (
            cp_model.OPTIMAL,
            cp_model.FEASIBLE,
        ):
            raise SolverError(self._status_to_message(status))

        if not collector.solutions:
            entries: List[SolutionEntry] = []
            for eid, options in event_options.items():
                found = False
                for idx, (slot_id, teacher_id, room_id, _room_penalty) in enumerate(options):
                    if solver.Value(x[(eid, idx)]):
                        entries.append(
                            SolutionEntry(
                                event_id=int(eid),
                                slot_id=int(slot_id),
                                teacher_id=int(teacher_id),
                                room_id=int(room_id),
                            )
                        )
                        found = True
                        break
                if not found:
                    raise SolverError(
                        f"Solver нашёл решение, но не назначил опцию для event_id={eid}."
                    )

            return [
                Solution(
                    entries=entries,
                    objective_value=int(solver.ObjectiveValue()),
                    meta={"status": self._status_name(status)},
                )
            ]

        for sol in collector.solutions:
            sol.meta["status"] = self._status_name(status)

        return collector.solutions


    def _build_event_options(
        self,
        *,
        teachers: List[Teacher],
        groups: List[StudentGroup],
        rooms: List[Room],
        slots: List[TimeSlot],
        slots_by_week_type: Dict[int, List[TimeSlot]],
        curriculum: Dict[int, CurriculumItem],
        events: List[object],
        teacher_subjects: Dict[Tuple[int, int, str], bool],
        teacher_availability: Dict[Tuple[int, int], bool],
        group_by_id: Dict[int, StudentGroup],
        lock_map: Dict[int, ScheduleLock],
        subject_names_by_id: Dict[int, str],
        random_seed: int,
    ) -> Tuple[Dict[int, List[Tuple[int, int, int, int]]], List[FeasibilityIssue]]:
        event_options: Dict[int, List[Tuple[int, int, int, int]]] = {}
        issues: List[FeasibilityIssue] = []

        for e in events:
            eid = _positive_int(getattr(e, "id_event", 0))
            curriculum_id = _positive_int(getattr(e, "curriculum_id", 0))
            subject_id = _positive_int(getattr(e, "subject_id", 0))
            part_type = str(getattr(e, "part_type", "") or "").strip()

            if eid <= 0:
                issues.append(
                    FeasibilityIssue(
                        event_id=0,
                        reason="Некорректный id_event.",
                        subject_id=subject_id,
                        subject_name=str(getattr(e, "subject_name", "") or ""),
                        part_type=part_type,
                        group_ids=tuple(),
                        group_names=tuple(),
                        candidate_teachers=0,
                        candidate_rooms=0,
                        candidate_slots=0,
                    )
                )
                continue

            cur = curriculum.get(curriculum_id)
            if cur is None:
                issues.append(
                    FeasibilityIssue(
                        event_id=eid,
                        reason=f"Не найден CurriculumItem для curriculum_id={curriculum_id}.",
                        subject_id=subject_id,
                        subject_name=str(getattr(e, "subject_name", "") or ""),
                        part_type=part_type,
                        group_ids=tuple(),
                        group_names=tuple(),
                        candidate_teachers=0,
                        candidate_rooms=0,
                        candidate_slots=0,
                    )
                )
                continue

            group_ids = tuple(
                _positive_int(gid)
                for gid in list(getattr(e, "group_ids", []) or [getattr(e, "group_id", 0)])
                if _positive_int(gid) > 0
            )

            if not group_ids:
                issues.append(
                    FeasibilityIssue(
                        event_id=eid,
                        reason="У события нет group_ids/group_id.",
                        subject_id=subject_id,
                        subject_name=str(getattr(e, "subject_name", "") or ""),
                        part_type=part_type,
                        group_ids=tuple(),
                        group_names=tuple(),
                        candidate_teachers=0,
                        candidate_rooms=0,
                        candidate_slots=0,
                    )
                )
                continue

            total_group_size = 0
            group_missing = False
            group_names: List[str] = []
            for gid in group_ids:
                grp = group_by_id.get(gid)
                if grp is None:
                    group_missing = True
                    break
                total_group_size += _positive_int(getattr(grp, "quantity", 0))
                group_names.append(str(getattr(grp, "group_name", "") or f"id={gid}"))

            subject_name = str(getattr(e, "subject_name", "") or "").strip()
            if not subject_name:
                subject_name = str(subject_names_by_id.get(subject_id, "") or "").strip()
            if not subject_name:
                subject_name = f"ID={subject_id}"

            if group_missing:
                issues.append(
                    FeasibilityIssue(
                        event_id=eid,
                        reason="Для одной из групп события не найдена запись StudentGroup.",
                        subject_id=subject_id,
                        subject_name=subject_name,
                        part_type=part_type,
                        group_ids=group_ids,
                        group_names=tuple(group_names),
                        candidate_teachers=0,
                        candidate_rooms=0,
                        candidate_slots=0,
                    )
                )
                continue

            required_room_type = str(getattr(e, "required_room_type", "") or "").strip().lower()
            if not required_room_type:
                required_room_type = str(getattr(cur, "required_room_type", "") or "").strip().lower()

            candidate_rooms = [
                r
                for r in rooms
                if _room_matches_required(r, required_room_type)
                and _positive_int(getattr(r, "capacity", 0)) >= total_group_size
            ]
            candidate_rooms.sort(
                key=lambda r: (
                    _room_priority_penalty(r, required_room_type),
                    _positive_int(getattr(r, "capacity", 0)) - total_group_size,
                    _positive_int(getattr(r, "id_room", 0)),
                )
            )
            candidate_rooms = candidate_rooms[:MAX_ROOMS_PER_EVENT]

            candidate_teachers = [
                t
                for t in teachers
                if teacher_subjects.get(
                    (
                        _positive_int(getattr(t, "id_teacher", 0)),
                        subject_id,
                        part_type,
                    ),
                    False,
                )
            ]
            candidate_teachers.sort(key=lambda t: _positive_int(getattr(t, "id_teacher", 0)))

            fixed_week_number = _optional_int(getattr(e, "fixed_week_number", None))
            fixed_week_type = _optional_int(getattr(e, "fixed_week_type", None))

            if fixed_week_type is not None:
                candidate_slots = list(slots_by_week_type.get(int(fixed_week_type), []))
            else:
                candidate_slots = list(slots)

            if fixed_week_number is not None:
                candidate_slots = [
                    s
                    for s in candidate_slots
                    if _positive_int(getattr(s, "week_number_in_semester", 0), 0) == fixed_week_number
                ]

            candidate_slots.sort(
                key=lambda s: (
                    _positive_int(getattr(s, "week_type", 0)),
                    _positive_int(getattr(s, "day_of_week", 0)),
                    _positive_int(getattr(s, "pair_number", 0)),
                    _positive_int(getattr(s, "id_slot", 0)),
                )
            )

            lk = lock_map.get(eid)
            if lk is not None and lk.slot_id is not None:
                candidate_slots = [
                    s for s in candidate_slots if _positive_int(getattr(s, "id_slot", 0)) == lk.slot_id
                ]
            if lk is not None and lk.teacher_id is not None:
                candidate_teachers = [
                    t
                    for t in candidate_teachers
                    if _positive_int(getattr(t, "id_teacher", 0)) == lk.teacher_id
                ]
            if lk is not None and lk.room_id is not None:
                candidate_rooms = [
                    r
                    for r in candidate_rooms
                    if _positive_int(getattr(r, "id_room", 0)) == lk.room_id
                ]

            if candidate_teachers and candidate_slots:
                candidate_slots = [
                    s
                    for s in candidate_slots
                    if any(
                        teacher_availability.get(
                            (
                                _positive_int(getattr(t, "id_teacher", 0)),
                                _positive_int(getattr(s, "id_slot", 0)),
                            ),
                            True,
                        )
                        for t in candidate_teachers
                    )
                ]

            candidate_slots = _sample_slots_evenly(candidate_slots, MAX_SLOTS_PER_EVENT)

            event_rng = random.Random(int(random_seed) * 1000003 + int(eid))
            event_rng.shuffle(candidate_teachers)
            event_rng.shuffle(candidate_rooms)
            event_rng.shuffle(candidate_slots)

            opts: List[Tuple[int, int, int, int]] = []
            for s in candidate_slots:
                sid = _positive_int(getattr(s, "id_slot", 0))
                if sid <= 0:
                    continue

                for t in candidate_teachers:
                    tid = _positive_int(getattr(t, "id_teacher", 0))
                    if tid <= 0:
                        continue

                    if not teacher_availability.get((tid, sid), True):
                        continue

                    for r in candidate_rooms:
                        rid = _positive_int(getattr(r, "id_room", 0))
                        if rid <= 0:
                            continue

                        penalty = _room_priority_penalty(r, required_room_type)
                        opts.append((sid, tid, rid, _positive_int(penalty, 0)))

            if opts:
                event_rng.shuffle(opts)

            if not opts:
                reason_parts: List[str] = []
                if not candidate_teachers:
                    reason_parts.append("нет преподавателей для subject/part_type")
                if not candidate_rooms:
                    reason_parts.append("нет подходящих аудиторий по типу/вместимости")
                if not candidate_slots:
                    reason_parts.append("нет допустимых слотов")
                if candidate_teachers and candidate_slots and candidate_rooms:
                    reason_parts.append("после фильтра availability не осталось допустимых комбинаций")

                issues.append(
                    FeasibilityIssue(
                        event_id=eid,
                        reason="; ".join(reason_parts) if reason_parts else "не найдено допустимых комбинаций",
                        subject_id=subject_id,
                        subject_name=subject_name,
                        part_type=part_type,
                        group_ids=group_ids,
                        group_names=tuple(group_names),
                        candidate_teachers=len(candidate_teachers),
                        candidate_rooms=len(candidate_rooms),
                        candidate_slots=len(candidate_slots),
                    )
                )
                continue

            event_options[eid] = opts

        return event_options, issues

    def _format_feasibility_issues(self, issues: List[FeasibilityIssue]) -> str:
        head = "Невозможно запустить solver: найдены события без допустимых назначений."
        lines = [head]

        for issue in issues[:10]:
            group_text = ", ".join(issue.group_names) if issue.group_names else ", ".join(
                f"id={gid}" for gid in issue.group_ids
            )
            lines.append(
                (
                    f"- event_id={issue.event_id}, группы=[{group_text}], "
                    f"дисциплина='{issue.subject_name}', part_type={issue.part_type}: {issue.reason} "
                    f"(teachers={issue.candidate_teachers}, rooms={issue.candidate_rooms}, slots={issue.candidate_slots})"
                )
            )

        if len(issues) > 10:
            lines.append(f"- ... ещё проблемных событий: {len(issues) - 10}")

        return "\n".join(lines)

    @staticmethod
    def _status_name(status: int) -> str:
        mapping = {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.MODEL_INVALID: "MODEL_INVALID",
            cp_model.UNKNOWN: "UNKNOWN",
        }
        return mapping.get(status, f"STATUS_{status}")

    def _status_to_message(self, status: int) -> str:
        status_name = self._status_name(status)
        if status == cp_model.INFEASIBLE:
            return "Solver не нашёл допустимого решения: модель оказалась несовместимой."
        if status == cp_model.MODEL_INVALID:
            return "Solver не смог обработать модель: модель некорректна."
        if status == cp_model.UNKNOWN:
            return "Solver завершился без найденного решения в отведённое время."
        return f"Solver завершился со статусом {status_name}."
