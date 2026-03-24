from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, DefaultDict
from collections import defaultdict

from ortools.sat.python import cp_model

from app.domain.models import (
    Teacher,
    StudentGroup,
    Room,
    TimeSlot,
    CurriculumItem,
    Solution,
    SolutionEntry,
)
from app.domain.rules import SchedulingRules


# ============================================================
# Helpers
# ============================================================

MAX_ROOMS_PER_EVENT = 8
MAX_SLOTS_PER_EVENT = 32


def _day_key(slot: TimeSlot) -> Tuple[int, int]:
    """
    Для ежедневных штрафов опираемся прежде всего на week_type + day_of_week.

    week_number_in_semester в текущем проекте используется непоследовательно:
    в части репозиториев/слотов он фактически всегда 0, а weekly model живёт
    в основном через week_type. Поэтому для устойчивости solver не делает
    day-key зависимым от week_number_in_semester.
    """
    return (int(slot.week_type), int(slot.day_of_week))


def _or_bool(model: cp_model.CpModel, lits: List[cp_model.IntVar], name: str) -> cp_model.IntVar:
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
        if p in occupied_by_pair:
            y.append(occupied_by_pair[p])
        else:
            y.append(model.NewConstant(0))

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


def _parse_room_types(room_type: str | None) -> set[str]:
    if not room_type:
        return set()
    return {x.strip() for x in str(room_type).split(",") if x.strip()}


def _room_matches_required(room: Room, required_room_type: str) -> bool:
    room_types = _parse_room_types(room.room_type)
    return required_room_type in room_types


def _room_priority_penalty(room: Room, required_room_type: str) -> int:
    """
    Меньше — лучше.

    Приоритет ресурса аудитории:
      computer > lecture > lab > classroom

    Если событию требуется менее "ценный" тип, но аудитория содержит
    более ценный тип, начисляем штраф за перерасход ресурса.
    """
    room_types = _parse_room_types(room.room_type)

    if required_room_type not in room_types:
        return 10_000

    resource_rank = {
        "computer": 4,
        "lecture": 3,
        "lab": 2,
        "classroom": 1,
    }

    highest_room_rank = max((resource_rank.get(t, 0) for t in room_types), default=0)
    required_rank = resource_rank.get(required_room_type, 0)

    return max(0, highest_room_rank - required_rank)


@dataclass(frozen=True)
class ScheduleLock:
    event_id: int
    slot_id: Optional[int] = None
    teacher_id: Optional[int] = None
    room_id: Optional[int] = None


# ============================================================
# Solver
# ============================================================

class CPSatScheduleSolver:
    """
    Solver на OR-Tools CP-SAT.

    Улучшения по сравнению с прежней версией:
    - меньше служебных переменных
    - меньше повторных проходов по всем options
    - ограничение числа комнат/слотов на событие
    - более устойчивая работа с weekly model
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
    ) -> List[Solution]:
        if not events:
            return []

        slot_by_id = {int(s.id_slot): s for s in slots}
        group_by_id = {int(g.id_group): g for g in groups}
        max_pair = max((int(s.pair_number) for s in slots), default=0)
        all_daykeys = sorted({_day_key(s) for s in slots})

        lock_map: Dict[int, ScheduleLock] = {}
        if locks:
            for lk in locks:
                lock_map[int(lk.event_id)] = lk

        # ----------------------------------------------------
        # Прединдексация доступных слотов по week_type
        # ----------------------------------------------------
        study_slots = [s for s in slots if not bool(getattr(s, "is_lunch_break", False))]

        slots_by_week_type: DefaultDict[int, List[TimeSlot]] = defaultdict(list)
        for s in study_slots:
            slots_by_week_type[int(s.week_type)].append(s)

        # ----------------------------------------------------
        # Подготовка допустимых опций для каждого события
        # event_options[event_id] = [(slot_id, teacher_id, room_id, room_penalty)]
        # ----------------------------------------------------
        event_options: Dict[int, List[Tuple[int, int, int, int]]] = {}

        for e in events:
            eid = int(e.id_event)
            cur = curriculum[int(e.curriculum_id)]

            group_ids = list(getattr(e, "group_ids", [int(e.group_id)]))
            group_sizes = []
            for gid in group_ids:
                grp = group_by_id.get(int(gid))
                if grp is None:
                    raise ValueError(f"Group not found for event={eid}, group_id={gid}")
                group_sizes.append(int(grp.quantity))

            total_group_size = sum(group_sizes)

            # -----------------------------
            # Rooms: сразу сортируем и режем хвост
            # -----------------------------
            candidate_rooms = [
                r for r in rooms
                if _room_matches_required(r, cur.required_room_type) and int(r.capacity) >= total_group_size
            ]
            candidate_rooms.sort(
                key=lambda r: (
                    _room_priority_penalty(r, cur.required_room_type),
                    int(r.capacity) - total_group_size,
                    int(r.id_room),
                )
            )
            candidate_rooms = candidate_rooms[:MAX_ROOMS_PER_EVENT]

            # -----------------------------
            # Teachers
            # -----------------------------
            candidate_teachers = [
                t for t in teachers
                if teacher_subjects.get((int(t.id_teacher), int(e.subject_id), str(e.part_type)), False)
            ]
            candidate_teachers.sort(key=lambda t: int(t.id_teacher))

            # -----------------------------
            # Slots
            # fixed_week_number <= 0 считаем "не зафиксировано"
            # -----------------------------
            fixed_week_number = getattr(e, "fixed_week_number", None)
            if fixed_week_number is not None and int(fixed_week_number) <= 0:
                fixed_week_number = None

            fixed_week_type = getattr(e, "fixed_week_type", None)

            if fixed_week_type is not None:
                candidate_slots = list(slots_by_week_type.get(int(fixed_week_type), []))
            else:
                candidate_slots = list(study_slots)

            if fixed_week_number is not None:
                candidate_slots = [
                    s for s in candidate_slots
                    if int(getattr(s, "week_number_in_semester", 0) or 0) == int(fixed_week_number)
                ]

            candidate_slots.sort(
                key=lambda s: (
                    int(getattr(s, "week_type", 0) or 0),
                    int(getattr(s, "day_of_week", 0) or 0),
                    int(getattr(s, "pair_number", 0) or 0),
                    int(s.id_slot),
                )
            )
            candidate_slots = candidate_slots[:MAX_SLOTS_PER_EVENT]

            # -----------------------------
            # Locks
            # -----------------------------
            lk = lock_map.get(eid)
            if lk is not None and lk.slot_id is not None:
                candidate_slots = [s for s in candidate_slots if int(s.id_slot) == int(lk.slot_id)]
            if lk is not None and lk.teacher_id is not None:
                candidate_teachers = [t for t in candidate_teachers if int(t.id_teacher) == int(lk.teacher_id)]
            if lk is not None and lk.room_id is not None:
                candidate_rooms = [r for r in candidate_rooms if int(r.id_room) == int(lk.room_id)]

            # -----------------------------
            # Итоговые опции
            # -----------------------------
            opts: List[Tuple[int, int, int, int]] = []
            for s in candidate_slots:
                sid = int(s.id_slot)
                for t in candidate_teachers:
                    tid = int(t.id_teacher)
                    if not teacher_availability.get((tid, sid), True):
                        continue
                    for r in candidate_rooms:
                        penalty = _room_priority_penalty(r, cur.required_room_type)
                        opts.append((sid, tid, int(r.id_room), int(penalty)))

            if not opts:
                raise ValueError(
                    f"No feasible options for event={eid} "
                    f"(groups={group_ids}, subject={e.subject_id}, part={e.part_type}). "
                    f"teachers={len(candidate_teachers)}, rooms={len(candidate_rooms)}, slots={len(candidate_slots)}. "
                    f"Check teacher qualification by part_type, room type/capacity, availability, locks."
                )

            event_options[eid] = opts

        # ====================================================
        # Поиск k решений через no-good cuts
        # ====================================================
        solutions: List[Solution] = []
        nogoods: List[Dict[int, Tuple[int, int, int, int]]] = []

        for _variant_idx in range(max(1, int(k_solutions))):
            model = cp_model.CpModel()

            x: Dict[Tuple[int, int], cp_model.IntVar] = {}

            # Индексы для быстрого построения ограничений и штрафов
            used_group_slot: DefaultDict[Tuple[int, int], List[cp_model.IntVar]] = defaultdict(list)
            used_teacher_slot: DefaultDict[Tuple[int, int], List[cp_model.IntVar]] = defaultdict(list)
            used_room_slot: DefaultDict[Tuple[int, int], List[cp_model.IntVar]] = defaultdict(list)

            occ_group_day_pair: DefaultDict[Tuple[int, Tuple[int, int], int], List[cp_model.IntVar]] = defaultdict(list)
            occ_teacher_day_pair: DefaultDict[Tuple[int, Tuple[int, int], int], List[cp_model.IntVar]] = defaultdict(list)
            teacher_day_load_lits: DefaultDict[Tuple[int, Tuple[int, int]], List[cp_model.IntVar]] = defaultdict(list)

            # ------------------------------------------------
            # Exactly one option per event
            # ------------------------------------------------
            for e in events:
                eid = int(e.id_event)
                opts = event_options[eid]

                bools: List[cp_model.IntVar] = []
                group_ids = list(getattr(e, "group_ids", [int(e.group_id)]))

                for i, (slot_id, teacher_id, room_id, _room_penalty) in enumerate(opts):
                    b = model.NewBoolVar(f"x_e{eid}_o{i}")
                    x[(eid, i)] = b
                    bools.append(b)

                    slot = slot_by_id[int(slot_id)]
                    daykey = _day_key(slot)
                    pair_no = int(slot.pair_number)

                    for gid in group_ids:
                        gid = int(gid)
                        used_group_slot[(gid, int(slot_id))].append(b)
                        occ_group_day_pair[(gid, daykey, pair_no)].append(b)

                    tid = int(teacher_id)
                    rid = int(room_id)

                    used_teacher_slot[(tid, int(slot_id))].append(b)
                    used_room_slot[(rid, int(slot_id))].append(b)

                    occ_teacher_day_pair[(tid, daykey, pair_no)].append(b)
                    teacher_day_load_lits[(tid, daykey)].append(b)

                model.AddExactlyOne(bools)

            # ------------------------------------------------
            # Жёсткие конфликты
            # ------------------------------------------------
            for lits in used_group_slot.values():
                if len(lits) > 1:
                    model.Add(sum(lits) <= 1)

            for lits in used_teacher_slot.values():
                if len(lits) > 1:
                    model.Add(sum(lits) <= 1)

            for lits in used_room_slot.values():
                if len(lits) > 1:
                    model.Add(sum(lits) <= 1)

            objective_terms = []

            # ------------------------------------------------
            # Штрафы за окна у групп
            # ------------------------------------------------
            w_group_gaps = int(getattr(rules, "w_group_gaps", 10))
            if w_group_gaps > 0:
                for g in groups:
                    gid = int(g.id_group)
                    for daykey in all_daykeys:
                        occ_by_pair: Dict[int, cp_model.IntVar] = {}
                        for p in range(1, max_pair + 1):
                            lits = occ_group_day_pair.get((gid, daykey, p), [])
                            occ_by_pair[p] = _or_bool(model, lits, f"occ_g{gid}_{daykey}_{p}")

                        gaps = _gaps_for_day(
                            model=model,
                            occupied_by_pair=occ_by_pair,
                            max_pair=max_pair,
                            name_prefix=f"g{gid}_{daykey}",
                            allow_lunch_gap=bool(getattr(rules, "allow_lunch_gap", True)),
                            lunch_min=int(getattr(rules, "lunch_gap_min_pair", 2)),
                            lunch_max=int(getattr(rules, "lunch_gap_max_pair", 3)),
                        )
                        objective_terms.append(w_group_gaps * gaps)

            # ------------------------------------------------
            # Штрафы за окна у преподавателей
            # ------------------------------------------------
            w_teacher_gaps = int(getattr(rules, "w_teacher_gaps", 6))
            if w_teacher_gaps > 0:
                for t in teachers:
                    tid = int(t.id_teacher)
                    for daykey in all_daykeys:
                        occ_by_pair: Dict[int, cp_model.IntVar] = {}
                        for p in range(1, max_pair + 1):
                            lits = occ_teacher_day_pair.get((tid, daykey, p), [])
                            occ_by_pair[p] = _or_bool(model, lits, f"occ_t{tid}_{daykey}_{p}")

                        gaps = _gaps_for_day(
                            model=model,
                            occupied_by_pair=occ_by_pair,
                            max_pair=max_pair,
                            name_prefix=f"t{tid}_{daykey}",
                            allow_lunch_gap=bool(getattr(rules, "allow_lunch_gap", True)),
                            lunch_min=int(getattr(rules, "lunch_gap_min_pair", 2)),
                            lunch_max=int(getattr(rules, "lunch_gap_max_pair", 3)),
                        )
                        objective_terms.append(w_teacher_gaps * gaps)

            # ------------------------------------------------
            # Штраф за перегруз преподавателя
            # ------------------------------------------------
            w_teacher_overload = int(getattr(rules, "w_teacher_overload", 8))
            if w_teacher_overload > 0:
                for t in teachers:
                    tid = int(t.id_teacher)
                    soft_max = int(getattr(t, "soft_max_pairs_per_day", 4))

                    for daykey in all_daykeys:
                        lits = teacher_day_load_lits.get((tid, daykey), [])
                        if not lits:
                            continue

                        load = model.NewIntVar(0, len(lits), f"load_t{tid}_{daykey}")
                        model.Add(load == sum(lits))

                        overload = model.NewIntVar(0, len(lits), f"over_t{tid}_{daykey}")
                        model.Add(overload >= load - soft_max)
                        model.Add(overload >= 0)

                        objective_terms.append(w_teacher_overload * overload)

            # ------------------------------------------------
            # Лекции не на последней паре
            # ------------------------------------------------
            w_last_pair_lecture = int(getattr(rules, "w_last_pair_lecture", 4))
            if w_last_pair_lecture > 0:
                for e in events:
                    if str(e.part_type) != "lecture":
                        continue
                    eid = int(e.id_event)
                    opts = event_options[eid]
                    for i, (slot_id, _tid, _rid, _rp) in enumerate(opts):
                        slot = slot_by_id[int(slot_id)]
                        if int(slot.pair_number) == max_pair:
                            objective_terms.append(w_last_pair_lecture * x[(eid, i)])

            # ------------------------------------------------
            # Штраф за субботу
            # ------------------------------------------------
            w_saturday_penalty = int(getattr(rules, "w_saturday_penalty", 50))
            if w_saturday_penalty > 0:
                for e in events:
                    eid = int(e.id_event)
                    opts = event_options[eid]
                    for i, (slot_id, _tid, _rid, _rp) in enumerate(opts):
                        slot = slot_by_id[int(slot_id)]
                        if int(slot.day_of_week) == 6:
                            objective_terms.append(w_saturday_penalty * x[(eid, i)])

            # ------------------------------------------------
            # Штраф за использование "слишком ценной" аудитории
            # ------------------------------------------------
            w_room_priority = int(getattr(rules, "w_room_priority", 5))
            if w_room_priority > 0:
                for e in events:
                    eid = int(e.id_event)
                    opts = event_options[eid]
                    for i, (_slot_id, _tid, _rid, room_penalty) in enumerate(opts):
                        if int(room_penalty) > 0:
                            objective_terms.append(w_room_priority * int(room_penalty) * x[(eid, i)])

            # ------------------------------------------------
            # No-good cuts для поиска нескольких решений
            # ------------------------------------------------
            for prev in nogoods:
                lits = []
                for event_id, prev_opt in prev.items():
                    opts = event_options[int(event_id)]
                    for i, opt in enumerate(opts):
                        if opt == prev_opt:
                            lits.append(x[(int(event_id), i)])
                            break
                if lits:
                    model.Add(sum(lits) <= len(lits) - 1)

            model.Minimize(sum(objective_terms) if objective_terms else 0)

            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = float(time_limit_seconds)
            solver.parameters.random_seed = int(random_seed)
            solver.parameters.num_search_workers = 8

            status = solver.Solve(model)
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                break

            entries: List[SolutionEntry] = []
            chosen_for_nogood: Dict[int, Tuple[int, int, int, int]] = {}

            for e in events:
                eid = int(e.id_event)
                opts = event_options[eid]

                chosen_i = None
                for i in range(len(opts)):
                    if solver.Value(x[(eid, i)]) == 1:
                        chosen_i = i
                        break

                if chosen_i is None:
                    raise ValueError(f"Chosen option not found for event={eid}")

                slot_id, teacher_id, room_id, room_penalty = opts[chosen_i]
                chosen_for_nogood[eid] = (slot_id, teacher_id, room_id, room_penalty)

                entries.append(
                    SolutionEntry(
                        event_id=eid,
                        slot_id=int(slot_id),
                        teacher_id=int(teacher_id),
                        room_id=int(room_id),
                    )
                )

            total_options = sum(len(v) for v in event_options.values())

            solutions.append(
                Solution(
                    entries=entries,
                    objective_value=int(solver.ObjectiveValue()),
                    meta={
                        "status": int(status),
                        "events_count": len(events),
                        "total_options": int(total_options),
                        "avg_options_per_event": float(total_options / max(1, len(events))),
                    },
                )
            )
            nogoods.append(chosen_for_nogood)

        return solutions