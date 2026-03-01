# app/infrastructure/optimizer/cp_sat_solver.py
"""
CP-SAT solver (OR-Tools) — реализация ScheduleSolverPort.

Особенности:
- строит расписание на основе списка Event
- выбирает для каждого Event одну "опцию" (slot, teacher, room)
- hard constraints:
  * конфликт группы/препода/аудитории в одном слоте
  * тип аудитории + вместимость
  * доступность преподавателя
  * (опционально) учитывает locks как hard constraints
- soft penalties (как в domain.rules):
  * окна у студентов (если запрещены)
  * 2..5 пар у студентов в день (штраф за выход)
  * нагрузка препода > soft_max (5/6 сильно штрафуем)
  * окна у преподавателя (штрафуем мягко)
  * методдень (1 свободный день в неделю)
  * лекции желательно не позже N пары

Важно:
- НЕ используйте Python `or/and` с BoolVar/IntVar (это вызывает NotImplementedError).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Iterable, DefaultDict
from collections import defaultdict

from ortools.sat.python import cp_model

from app.domain.models import (
    Teacher,
    StudentGroup,
    Room,
    TimeSlot,
    CurriculumItem,
    Event,
    Solution,
    SolutionEntry,
)
from app.domain.rules import SchedulingRules


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _day_key(slot: TimeSlot) -> Tuple[int, int, int]:
    return (slot.week_number_in_semester, slot.week_type, slot.day_of_week)


def _or_bool(model: cp_model.CpModel, lits: List[cp_model.IntVar], name: str) -> cp_model.IntVar:
    """b == OR(lits) for BoolVars. Реализуем через MaxEquality."""
    b = model.NewBoolVar(name)
    if not lits:
        model.Add(b == 0)
    else:
        model.AddMaxEquality(b, lits)
    return b


def _gaps_for_day(
    model: cp_model.CpModel,
    occupied_by_pair: Dict[int, cp_model.IntVar],  # pair -> BoolVar(0/1)
    max_pair: int,
    name_prefix: str,
    allow_lunch_gap: bool,
    lunch_min: int,
    lunch_max: int,
) -> cp_model.IntVar:
    """
    Возвращает IntVar gaps = количество "окон" между первой и последней занятой парой.
    gap_p = 1 если:
      - пара p пустая
      - есть занятие раньше
      - есть занятие позже
    Обеденный диапазон (если разрешен) не штрафуем.
    """
    # Заполним отсутствующие пары 0-константой (без Python `or`)
    y: List[cp_model.IntVar] = []
    for p in range(1, max_pair + 1):
        v = occupied_by_pair.get(p)
        if v is None:
            v = model.NewConstant(0)
        y.append(v)

    # before[p] = OR(y[1..p-1]), after[p] = OR(y[p+1..P])
    before: Dict[int, cp_model.IntVar] = {}
    after: Dict[int, cp_model.IntVar] = {}

    for p in range(1, max_pair + 1):
        before[p] = _or_bool(model, y[: p - 1], f"{name_prefix}_before_{p}")
        after[p] = _or_bool(model, y[p:], f"{name_prefix}_after_{p}")  # y[p:] = p+1..P

    gap_vars: List[cp_model.IntVar] = []
    for p in range(1, max_pair + 1):
        if allow_lunch_gap and lunch_min <= p <= lunch_max:
            continue

        gp = model.NewBoolVar(f"{name_prefix}_gap_{p}")

        # gp <= (1 - y[p])
        model.Add(gp <= 1 - y[p - 1])
        model.Add(gp <= before[p])
        model.Add(gp <= after[p])

        # gp >= before + after + (1-y) - 2
        model.Add(gp >= before[p] + after[p] + (1 - y[p - 1]) - 2)

        gap_vars.append(gp)

    gaps = model.NewIntVar(0, max_pair, f"{name_prefix}_gaps_total")
    if gap_vars:
        model.Add(gaps == sum(gap_vars))
    else:
        model.Add(gaps == 0)
    return gaps


# ------------------------------------------------------------
# Locks model (минимально)
# ------------------------------------------------------------

@dataclass(frozen=True)
class ScheduleLock:
    """
    Минимальная структура для hard-фиксаций.
    Если у тебя репозиторий возвращает другой формат — адаптируй в use-case/event_builder.
    """
    event_id: int
    slot_id: Optional[int] = None
    teacher_id: Optional[int] = None
    room_id: Optional[int] = None


# ------------------------------------------------------------
# Solver class
# ------------------------------------------------------------

class CPSatScheduleSolver:
    def solve(
        self,
        teachers: List[Teacher],
        groups: List[StudentGroup],
        rooms: List[Room],
        slots: List[TimeSlot],
        curriculum: Dict[int, CurriculumItem],
        events: List[Event],
        teacher_subjects: Dict[Tuple[int, int], bool],
        teacher_availability: Dict[Tuple[int, int], bool],
        rules: SchedulingRules,
        k_solutions: int,
        time_limit_seconds: int,
        random_seed: int,
        locks: Optional[List[ScheduleLock]] = None,
    ) -> List[Solution]:
        """
        Возвращает до k_solutions решений.
        """
        if not events:
            return []

        slot_by_id = {s.id_slot: s for s in slots}
        group_by_id = {g.id_group: g for g in groups}
        teacher_by_id = {t.id_teacher: t for t in teachers}

        max_pair = max(s.pair_number for s in slots) if slots else 0
        all_daykeys = sorted({_day_key(s) for s in slots})

        # ---- room candidates cache by type and capacity ----
        rooms_by_type: DefaultDict[str, List[Room]] = defaultdict(list)
        for r in rooms:
            rooms_by_type[r.room_type].append(r)

        # ---- locks by event_id ----
        lock_map: Dict[int, ScheduleLock] = {}
        if locks:
            for lk in locks:
                lock_map[lk.event_id] = lk

        # ---- build options for each event ----
        event_options: Dict[int, List[Tuple[int, int, int]]] = {}

        for e in events:
            cur = curriculum[e.curriculum_id]
            grp = group_by_id[e.group_id]

            # rooms that fit
            candidate_rooms = [
                r for r in rooms_by_type[cur.required_room_type]
                if r.capacity >= grp.quantity
            ]

            # teachers that can teach subject
            candidate_teachers = [
                t for t in teachers
                if teacher_subjects.get((t.id_teacher, e.subject_id), False)
            ]

            # slots filter: fixed week constraints + exclude lunch slots
            candidate_slots = []
            for s in slots:
                if s.is_lunch_break:
                    continue
                if e.fixed_week_number is not None and s.week_number_in_semester != e.fixed_week_number:
                    continue
                if e.fixed_week_type is not None and s.week_type != e.fixed_week_type:
                    continue
                candidate_slots.append(s)

            # apply lock filters
            lk = lock_map.get(e.id_event)
            if lk is not None and lk.slot_id is not None:
                candidate_slots = [s for s in candidate_slots if s.id_slot == lk.slot_id]
            if lk is not None and lk.teacher_id is not None:
                candidate_teachers = [t for t in candidate_teachers if t.id_teacher == lk.teacher_id]
            if lk is not None and lk.room_id is not None:
                candidate_rooms = [r for r in candidate_rooms if r.id_room == lk.room_id]

            opts: List[Tuple[int, int, int]] = []
            for s in candidate_slots:
                for t in candidate_teachers:
                    # availability: if missing -> True
                    if not teacher_availability.get((t.id_teacher, s.id_slot), True):
                        continue
                    for r in candidate_rooms:
                        opts.append((s.id_slot, t.id_teacher, r.id_room))

            if not opts:
                raise ValueError(
                    f"No feasible options for event={e.id_event} "
                    f"(group={e.group_id}, subject={e.subject_id}, part={e.part_type}). "
                    f"Check rooms/teachers/availability/locks."
                )
            event_options[e.id_event] = opts

        # ---- solve multiple variants via no-good cuts ----
        solutions: List[Solution] = []
        nogoods: List[Dict[int, Tuple[int, int, int]]] = []

        for variant_idx in range(k_solutions):
            model = cp_model.CpModel()

            # decision vars: x[(event_id, option_idx)] = 1 if chosen
            x: Dict[Tuple[int, int], cp_model.IntVar] = {}
            chosen_idx: Dict[int, cp_model.IntVar] = {}

            for e in events:
                opts = event_options[e.id_event]
                bools = []
                for i in range(len(opts)):
                    b = model.NewBoolVar(f"x_e{e.id_event}_o{i}")
                    x[(e.id_event, i)] = b
                    bools.append(b)
                model.AddExactlyOne(bools)

                idx = model.NewIntVar(0, len(opts) - 1, f"chosen_idx_e{e.id_event}")
                chosen_idx[e.id_event] = idx
                model.Add(idx == sum(i * x[(e.id_event, i)] for i in range(len(opts))))

            # ---- hard: conflicts in same slot ----
            used_group_slot: DefaultDict[Tuple[int, int], List[cp_model.IntVar]] = defaultdict(list)
            used_teacher_slot: DefaultDict[Tuple[int, int], List[cp_model.IntVar]] = defaultdict(list)
            used_room_slot: DefaultDict[Tuple[int, int], List[cp_model.IntVar]] = defaultdict(list)

            for e in events:
                opts = event_options[e.id_event]
                for i, (slot_id, teacher_id, room_id) in enumerate(opts):
                    b = x[(e.id_event, i)]
                    used_group_slot[(e.group_id, slot_id)].append(b)
                    used_teacher_slot[(teacher_id, slot_id)].append(b)
                    used_room_slot[(room_id, slot_id)].append(b)

            for (_, _), lits in used_group_slot.items():
                if len(lits) > 1:
                    model.Add(sum(lits) <= 1)
            for (_, _), lits in used_teacher_slot.items():
                if len(lits) > 1:
                    model.Add(sum(lits) <= 1)
            for (_, _), lits in used_room_slot.items():
                if len(lits) > 1:
                    model.Add(sum(lits) <= 1)

            # ---- build occupancy maps for penalties and teacher hard max ----
            teacher_occ_pair: Dict[Tuple[int, Tuple[int, int, int], int], cp_model.IntVar] = {}
            group_occ_pair: Dict[Tuple[int, Tuple[int, int, int], int], cp_model.IntVar] = {}

            # for each slot create occ vars as OR over matching assignments
            for s in slots:
                dk = _day_key(s)

                for t in teachers:
                    lits = used_teacher_slot.get((t.id_teacher, s.id_slot), [])
                    occ = _or_bool(model, lits, f"occT_T{t.id_teacher}_S{s.id_slot}")
                    teacher_occ_pair[(t.id_teacher, dk, s.pair_number)] = occ

                for g in groups:
                    lits = used_group_slot.get((g.id_group, s.id_slot), [])
                    occ = _or_bool(model, lits, f"occG_G{g.id_group}_S{s.id_slot}")
                    group_occ_pair[(g.id_group, dk, s.pair_number)] = occ

            # ---- hard: teacher daily load <= hard_max ----
            for t in teachers:
                hard_max = min(rules.teacher_hard_max_pairs, t.hard_max_pairs_per_day)
                for dk in all_daykeys:
                    day_occ = [
                        teacher_occ_pair[(t.id_teacher, dk, p)]
                        for p in range(1, max_pair + 1)
                        if (t.id_teacher, dk, p) in teacher_occ_pair
                    ]
                    load = model.NewIntVar(0, max_pair, f"loadT_T{t.id_teacher}_{dk}")
                    model.Add(load == (sum(day_occ) if day_occ else 0))
                    model.Add(load <= hard_max)

            # ---- soft penalties ----
            penalties: List[cp_model.LinearExpr] = []

            # students: day load + gaps + weekly balance (L1)
            for g in groups:
                loads: List[cp_model.IntVar] = []
                for dk in all_daykeys:
                    occ_map = {p: group_occ_pair.get((g.id_group, dk, p)) for p in range(1, max_pair + 1)}
                    load = model.NewIntVar(0, max_pair, f"loadG_G{g.id_group}_{dk}")

                    # !!! no Python `or` with BoolVar here
                    terms = []
                    for p in range(1, max_pair + 1):
                        v = occ_map.get(p)
                        terms.append(v if v is not None else 0)
                    model.Add(load == sum(terms))

                    loads.append(load)

                    # day load penalty units
                    under = model.NewIntVar(0, rules.min_pairs_students_per_day, f"under_G{g.id_group}_{dk}")
                    over = model.NewIntVar(0, max_pair, f"over_G{g.id_group}_{dk}")
                    model.AddMaxEquality(under, [0, rules.min_pairs_students_per_day - load])
                    model.AddMaxEquality(over, [0, load - rules.max_pairs_students_per_day])
                    penalties.append(rules.w_students_day_load * (under + over))

                    # gaps penalty
                    if not rules.allow_student_gaps:
                        gaps = _gaps_for_day(
                            model=model,
                            occupied_by_pair=occ_map,
                            max_pair=max_pair,
                            name_prefix=f"G{g.id_group}_{dk}",
                            allow_lunch_gap=rules.allow_lunch_gap,
                            lunch_min=rules.lunch_gap_min_pair,
                            lunch_max=rules.lunch_gap_max_pair,
                        )
                        penalties.append(rules.w_students_gaps * gaps)

                # weekly balance (L1 deviation from avg)
                if loads:
                    n = len(loads)
                    total = model.NewIntVar(0, max_pair * n, f"totLoad_G{g.id_group}")
                    model.Add(total == sum(loads))
                    avg = model.NewIntVar(0, max_pair, f"avgLoad_G{g.id_group}")
                    model.Add(avg * n <= total)
                    model.Add(total < (avg + 1) * n)
                    devs: List[cp_model.IntVar] = []
                    for j, ld in enumerate(loads):
                        dev = model.NewIntVar(0, max_pair, f"dev_G{g.id_group}_{j}")
                        model.AddAbsEquality(dev, ld - avg)
                        devs.append(dev)
                    penalties.append(rules.w_students_balance * sum(devs))

            # teachers: over soft + gaps + method day
            for t in teachers:
                soft_max = min(rules.teacher_soft_max_pairs, t.soft_max_pairs_per_day)

                # for method day (per week)
                if rules.consider_method_day and t.needs_method_day:
                    by_week: DefaultDict[Tuple[int, int], List[Tuple[int, int, int]]] = defaultdict(list)
                    for dk in all_daykeys:
                        by_week[(dk[0], dk[1])].append(dk)

                for dk in all_daykeys:
                    occ_map = {p: teacher_occ_pair.get((t.id_teacher, dk, p)) for p in range(1, max_pair + 1)}
                    load = model.NewIntVar(0, max_pair, f"loadTsoft_T{t.id_teacher}_{dk}")
                    terms = []
                    for p in range(1, max_pair + 1):
                        v = occ_map.get(p)
                        terms.append(v if v is not None else 0)
                    model.Add(load == sum(terms))

                    # over-soft units
                    over_soft = model.NewIntVar(0, max_pair, f"overSoft_T{t.id_teacher}_{dk}")
                    model.AddMaxEquality(over_soft, [0, load - soft_max])

                    is_six = model.NewBoolVar(f"isSix_T{t.id_teacher}_{dk}")
                    model.Add(load == 6).OnlyEnforceIf(is_six)
                    model.Add(load != 6).OnlyEnforceIf(is_six.Not())

                    # penalty_units = over_soft + is_six  (чтобы 6 штрафовалось сильнее)
                    penalty_units = model.NewIntVar(0, 10, f"penUnits_T{t.id_teacher}_{dk}")
                    model.Add(penalty_units == over_soft + is_six)

                    penalties.append(rules.w_teacher_over_soft * penalty_units)

                    # gaps (allowed but penalized)
                    gaps = _gaps_for_day(
                        model=model,
                        occupied_by_pair=occ_map,
                        max_pair=max_pair,
                        name_prefix=f"T{t.id_teacher}_{dk}",
                        allow_lunch_gap=rules.allow_lunch_gap,
                        lunch_min=rules.lunch_gap_min_pair,
                        lunch_max=rules.lunch_gap_max_pair,
                    )
                    penalties.append(rules.w_teacher_gaps * gaps)

                # method day (per week)
                if rules.consider_method_day and t.needs_method_day:
                    by_week = defaultdict(list)
                    for dk in all_daykeys:
                        by_week[(dk[0], dk[1])].append(dk)

                    for week_key, dks in by_week.items():
                        day_has_class: List[cp_model.IntVar] = []
                        for dk in dks:
                            occs = [
                                teacher_occ_pair[(t.id_teacher, dk, p)]
                                for p in range(1, max_pair + 1)
                                if (t.id_teacher, dk, p) in teacher_occ_pair
                            ]
                            has_class = _or_bool(model, occs, f"hasClass_T{t.id_teacher}_{dk}")
                            day_has_class.append(has_class)

                        free_days: List[cp_model.IntVar] = []
                        for i, hc in enumerate(day_has_class):
                            fd = model.NewBoolVar(f"freeDay_T{t.id_teacher}_{week_key}_{i}")
                            model.Add(fd + hc == 1)  # fd = NOT hc
                            free_days.append(fd)

                        has_free = _or_bool(model, free_days, f"hasFree_T{t.id_teacher}_{week_key}")
                        method_pen = model.NewIntVar(0, 1, f"methodPen_T{t.id_teacher}_{week_key}")
                        model.Add(method_pen + has_free == 1)
                        penalties.append(rules.w_method_day * method_pen)

            # lectures late penalty
            for e in events:
                if e.part_type.lower() != "lecture":
                    continue
                opts = event_options[e.id_event]
                late_terms = []
                for i, (slot_id, _tid, _rid) in enumerate(opts):
                    pair = slot_by_id[slot_id].pair_number
                    units = max(0, pair - rules.lecture_preferred_last_pair)
                    if units > 0:
                        late_terms.append(units * x[(e.id_event, i)])
                if late_terms:
                    penalties.append(rules.w_lecture_late * sum(late_terms))

            # no-good cuts for different variants
            for prev in nogoods:
                same_lits = []
                for e in events:
                    prev_triplet = prev.get(e.id_event)
                    if prev_triplet is None:
                        continue
                    try:
                        idx = event_options[e.id_event].index(prev_triplet)
                    except ValueError:
                        continue
                    same_lits.append(x[(e.id_event, idx)])
                if same_lits:
                    model.Add(sum(same_lits) <= len(same_lits) - 1)

            model.Minimize(sum(penalties))

            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = float(time_limit_seconds)
            solver.parameters.random_seed = int(random_seed + variant_idx)
            solver.parameters.num_search_workers = 8

            status = solver.Solve(model)
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                break

            assignment: Dict[int, Tuple[int, int, int]] = {}
            sol_entries: List[SolutionEntry] = []
            for e in events:
                idx = solver.Value(chosen_idx[e.id_event])
                slot_id, teacher_id, room_id = event_options[e.id_event][idx]
                assignment[e.id_event] = (slot_id, teacher_id, room_id)
                sol_entries.append(SolutionEntry(
                    event_id=e.id_event,
                    slot_id=slot_id,
                    teacher_id=teacher_id,
                    room_id=room_id,
                ))

            solutions.append(Solution(entries=sol_entries, objective_value=int(solver.ObjectiveValue())))
            nogoods.append(assignment)

        return solutions