"""
MVP ядра оптимизации расписания (вариант 2: CP-SAT / OR-Tools)

Что умеет:
- строит расписание на семестр по слотовой сетке (2-недельное чередование уже заложено через TimeSlot.week_type)
- учитывает: конфликты группы/препода/аудитории, доступность препода, тип/вместимость аудитории
- soft-штрафы: окна у студентов/преподов, 2–5 пар у студентов, >4 пары у препода (5/6 сильно штрафуем),
  методдень (по возможности), лекции желательно не позже N пары
- генерирует K вариантов (no-good cut)

ВАЖНО:
1) Это MVP-реализация. Она опирается на "опции размещения" (slot, teacher, room) для каждого события.
2) Для больших данных оптимизируй генерацию опций (фильтры, ограничение списка преподавателей/аудиторий).

pip install ortools
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Iterable, Optional
from collections import defaultdict
from ortools.sat.python import cp_model


# -----------------------------
# Data models
# -----------------------------

@dataclass(frozen=True)
class Teacher:
    id_teacher: int
    full_name: str
    hard_max_pairs_per_day: int = 6   # hard
    soft_max_pairs_per_day: int = 4   # soft (штрафуем >4)
    needs_method_day: bool = True


@dataclass(frozen=True)
class StudentGroup:
    id_group: int
    group_name: str
    quantity: int
    education_form: str = "full-time"  # full-time/part-time/etc


@dataclass(frozen=True)
class Subject:
    id_subject: int
    subject_name: str


@dataclass(frozen=True)
class Room:
    id_class: int
    room_number: str
    room_type: str
    capacity: int


@dataclass(frozen=True)
class TimeSlot:
    id_slot: int
    week_number_in_semester: int  # 1..N
    week_type: int               # 1/2 (если чередование), иначе 1
    day_of_week: int             # 1..7
    pair_number: int             # 1..P
    is_lunch_break: bool = False


@dataclass(frozen=True)
class CurriculumItem:
    id_curriculum: int
    group_id: int
    subject_id: int
    part_type: str              # lecture/practice/lab
    required_room_type: str


@dataclass(frozen=True)
class Event:
    """
    Одно занятие (одна пара) которое нужно поставить в расписание.
    """
    id_event: int
    curriculum_id: int
    group_id: int
    subject_id: int
    part_type: str
    required_room_type: str
    # Если задано — событие должно быть в конкретной учебной неделе (например из WeeklyLoadPlan)
    fixed_week_number: Optional[int] = None   # week_number_in_semester
    fixed_week_type: Optional[int] = None     # 1/2


@dataclass(frozen=True)
class Rules:
    # Студенты
    min_pairs_students_per_day: int = 2
    max_pairs_students_per_day: int = 5
    allow_student_gaps: bool = False
    allow_lunch_gap: bool = True
    lunch_gap_min_pair: int = 2
    lunch_gap_max_pair: int = 3

    # Преподы
    teacher_hard_max_pairs: int = 6
    teacher_soft_max_pairs: int = 4
    consider_method_day: bool = True

    # Лекции
    lecture_preferred_last_pair: int = 2  # лекции желательно не позже 2 пары

    # Веса штрафов (профили можно менять)
    w_students_day_load: int = 500
    w_students_gaps: int = 600
    w_students_balance: int = 40
    w_teacher_over_soft: int = 700
    w_teacher_gaps: int = 150
    w_method_day: int = 250
    w_lecture_late: int = 70


# -----------------------------
# Helpers
# -----------------------------

def _key_day(slot: TimeSlot) -> Tuple[int, int, int]:
    """(week_number, week_type, day_of_week)"""
    return (slot.week_number_in_semester, slot.week_type, slot.day_of_week)


def _or_bool(model: cp_model.CpModel, lits: List[cp_model.IntVar], name: str) -> cp_model.IntVar:
    """
    b == OR(lits). lits must be BoolVars (0/1).
    Реализуем через MaxEquality.
    """
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
    """
    occupied_by_pair[p] = 1 если на паре p есть занятие.
    Возвращает IntVar gaps = количество "окон" между первой и последней занятой парой.
    Для CP-SAT: gap_p = 1 если:
      - пара p пустая
      - есть занятие раньше
      - есть занятие позже
    """
    y = [occupied_by_pair.get(p, None) for p in range(1, max_pair + 1)]
    # заполним отсутствующие пары нулями
    for p in range(1, max_pair + 1):
        if y[p - 1] is None:
            y[p - 1] = model.NewBoolVar(f"{name_prefix}_occ_{p}")
            model.Add(y[p - 1] == 0)

    before = {}  # before[p] = OR(y[1..p-1])
    after = {}   # after[p]  = OR(y[p+1..P])

    for p in range(1, max_pair + 1):
        before[p] = _or_bool(model, y[: p - 1], f"{name_prefix}_before_{p}")
        after[p] = _or_bool(model, y[p:], f"{name_prefix}_after_{p}")  # y[p] is index p+1 actually; but y[p:] is p+1..P

    gap_vars = []
    for p in range(1, max_pair + 1):
        # обеденный разрыв (если разрешён) — не штрафуем
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


# -----------------------------
# Core solver
# -----------------------------

@dataclass
class SolutionEntry:
    event_id: int
    slot_id: int
    teacher_id: int
    room_id: int


@dataclass
class Solution:
    entries: List[SolutionEntry]
    objective_value: int


def solve_schedule(
    *,
    teachers: List[Teacher],
    groups: List[StudentGroup],
    rooms: List[Room],
    slots: List[TimeSlot],
    curriculum: Dict[int, CurriculumItem],
    events: List[Event],
    teacher_subjects: Dict[Tuple[int, int], bool],  # (teacher_id, subject_id) -> True
    teacher_availability: Dict[Tuple[int, int], bool],  # (teacher_id, slot_id) -> is_available
    rules: Rules,
    k_solutions: int = 5,
    time_limit_seconds: int = 15,
    random_seed: int = 1,
) -> List[Solution]:
    """
    Возвращает до k_solutions вариантов. Каждый следующий отличается от предыдущих (no-good cut).

    Важно: для скорости и простоты мы создаём для каждого event список допустимых "опций":
      option = (slot_id, teacher_id, room_id)
    и выбираем ровно одну option per event.
    """

    # Индексы
    teacher_by_id = {t.id_teacher: t for t in teachers}
    group_by_id = {g.id_group: g for g in groups}
    room_by_id = {r.id_class: r for r in rooms}
    slot_by_id = {s.id_slot: s for s in slots}

    # Параметры сетки
    max_pair = max(s.pair_number for s in slots) if slots else 0

    # Предварительные фильтры опций для событий
    # -------------------------------------------------------
    # Для каждого event соберём возможные варианты (slot, teacher, room)
    event_options: Dict[int, List[Tuple[int, int, int]]] = {}

    # Кеши: комнаты по типу и вместимости
    rooms_by_type = defaultdict(list)
    for r in rooms:
        rooms_by_type[r.room_type].append(r)

    for e in events:
        cur = curriculum[e.curriculum_id]
        grp = group_by_id[e.group_id]
        candidate_rooms = [
            r for r in rooms_by_type[cur.required_room_type]
            if r.capacity >= grp.quantity
        ]

        # преподаватели, которые могут вести предмет
        candidate_teachers = [
            t for t in teachers
            if teacher_subjects.get((t.id_teacher, e.subject_id), False)
        ]

        # слоты с учетом фиксированной недели (если задано)
        candidate_slots = []
        for s in slots:
            if e.fixed_week_number is not None and s.week_number_in_semester != e.fixed_week_number:
                continue
            if e.fixed_week_type is not None and s.week_type != e.fixed_week_type:
                continue
            # если слот помечен как обеденный перерыв — занятия туда не ставим
            if s.is_lunch_break:
                continue
            candidate_slots.append(s)

        opts = []
        for s in candidate_slots:
            for t in candidate_teachers:
                if not teacher_availability.get((t.id_teacher, s.id_slot), True):
                    continue
                for r in candidate_rooms:
                    opts.append((s.id_slot, t.id_teacher, r.id_class))

        if not opts:
            raise ValueError(
                f"No feasible options for event {e.id_event} "
                f"(group={e.group_id}, subject={e.subject_id}, part={e.part_type}). "
                f"Check availability/rooms/teacher_subjects."
            )
        event_options[e.id_event] = opts

    # -------------------------------------------------------
    # Решаем K раз с no-good cuts
    # -------------------------------------------------------
    solutions: List[Solution] = []
    nogood_assignments: List[Dict[int, Tuple[int, int, int]]] = []  # event_id -> (slot, teacher, room)

    for sol_index in range(k_solutions):
        model = cp_model.CpModel()

        # Переменные выбора опции для каждого event
        x: Dict[Tuple[int, int], cp_model.IntVar] = {}  # (event_id, option_idx) -> BoolVar
        chosen_option_idx: Dict[int, cp_model.IntVar] = {}

        for e in events:
            opts = event_options[e.id_event]
            bools = []
            for i in range(len(opts)):
                b = model.NewBoolVar(f"x_e{e.id_event}_o{i}")
                x[(e.id_event, i)] = b
                bools.append(b)

            # ровно одна опция
            model.AddExactlyOne(bools)

            # индекс выбранной опции (для удобства вывода)
            idx = model.NewIntVar(0, len(opts) - 1, f"chosen_idx_e{e.id_event}")
            chosen_option_idx[e.id_event] = idx
            # idx == sum(i * x_i)
            model.Add(idx == sum(i * x[(e.id_event, i)] for i in range(len(opts))))

        # Hard constraints: конфликтность по slot для группы/препода/аудитории
        # -------------------------------------------------------
        # Соберём для каждого slot набор булевых литералов "в этом slot занято"
        used_group_slot = defaultdict(list)   # (group_id, slot_id) -> [BoolVars]
        used_teacher_slot = defaultdict(list) # (teacher_id, slot_id) -> [BoolVars]
        used_room_slot = defaultdict(list)    # (room_id, slot_id) -> [BoolVars]

        for e in events:
            opts = event_options[e.id_event]
            for i, (slot_id, teacher_id, room_id) in enumerate(opts):
                b = x[(e.id_event, i)]
                used_group_slot[(e.group_id, slot_id)].append(b)
                used_teacher_slot[(teacher_id, slot_id)].append(b)
                used_room_slot[(room_id, slot_id)].append(b)

        # В одном слоте:
        # - у группы максимум 1 занятие
        # - у преподавателя максимум 1
        # - в аудитории максимум 1
        for (g_id, slot_id), lits in used_group_slot.items():
            if len(lits) > 1:
                model.Add(sum(lits) <= 1)
        for (t_id, slot_id), lits in used_teacher_slot.items():
            if len(lits) > 1:
                model.Add(sum(lits) <= 1)
        for (r_id, slot_id), lits in used_room_slot.items():
            if len(lits) > 1:
                model.Add(sum(lits) <= 1)

        # Hard: максимальная нагрузка преподавателя (6 пар в день)
        # -------------------------------------------------------
        # pairs(t, daykey) <= hard_max
        # daykey = (week_number, week_type, day_of_week)
        teacher_day_pairs = defaultdict(list)  # (teacher_id, daykey, pair_number) -> bool occ
        # будем строить "занятость" по парам для штрафов окон и подсчёта нагрузки
        for t in teachers:
            for s in slots:
                daykey = _key_day(s)
                # occ[t, daykey, pair] = OR всех занятий, где (teacher=t, slot=s)
                lits = used_teacher_slot.get((t.id_teacher, s.id_slot), [])
                occ = _or_bool(model, lits, f"occ_T{t.id_teacher}_S{s.id_slot}")
                teacher_day_pairs[(t.id_teacher, daykey, s.pair_number)].append(occ)

        # Сведём к одному bool на (teacher, daykey, pair)
        teacher_occ_pair = {}
        for key, occ_list in teacher_day_pairs.items():
            teacher_occ_pair[key] = _or_bool(model, occ_list, f"occpair_T{key[0]}_{key[1]}_P{key[2]}")

        # Нагрузка по дням
        for t in teachers:
            hard_max = min(rules.teacher_hard_max_pairs, t.hard_max_pairs_per_day)
            for daykey in {( _key_day(s) ) for s in slots}:
                load = model.NewIntVar(0, max_pair, f"load_T{t.id_teacher}_{daykey}")
                day_occ = [
                    teacher_occ_pair[(t.id_teacher, daykey, p)]
                    for p in range(1, max_pair + 1)
                    if (t.id_teacher, daykey, p) in teacher_occ_pair
                ]
                model.Add(load == sum(day_occ) if day_occ else 0)
                model.Add(load <= hard_max)

        # -------------------------------------------------------
        # Soft penalties
        # -------------------------------------------------------
        penalties: List[cp_model.LinearExpr] = []

        # 1) Студенты: занятость по парам, окна, нагрузка 2..5, баланс
        group_occ_pair = {}  # (group_id, daykey, pair) -> bool
        group_load_day = {}  # (group_id, daykey) -> int load

        all_daykeys = sorted({_key_day(s) for s in slots})

        for g in groups:
            for daykey in all_daykeys:
                # Build occupied_by_pair for this group/day
                occupied_by_pair: Dict[int, cp_model.IntVar] = {}
                for s in slots:
                    if _key_day(s) != daykey:
                        continue
                    lits = used_group_slot.get((g.id_group, s.id_slot), [])
                    occupied_by_pair[s.pair_number] = _or_bool(model, lits, f"occ_G{g.id_group}_S{s.id_slot}")

                # load = sum occupied pairs
                load = model.NewIntVar(0, max_pair, f"load_G{g.id_group}_{daykey}")
                model.Add(load == sum(
                    occupied_by_pair[p] if occupied_by_pair.get(p) is not None else 0
                    for p in range(1, max_pair + 1)
                    ))
                group_load_day[(g.id_group, daykey)] = load

                # 1a) штраф за выход за 2..5 (если хочешь сделать Hard — перенеси в hard constraints)
                under = model.NewIntVar(0, rules.min_pairs_students_per_day, f"under_G{g.id_group}_{daykey}")
                over = model.NewIntVar(0, max_pair, f"over_G{g.id_group}_{daykey}")
                model.AddMaxEquality(under, [0, rules.min_pairs_students_per_day - load])
                model.AddMaxEquality(over, [0, load - rules.max_pairs_students_per_day])
                penalties.append(rules.w_students_day_load * (under + over))

                # 1b) окна у студентов
                if not rules.allow_student_gaps:
                    gaps = _gaps_for_day(
                        model=model,
                        occupied_by_pair=occupied_by_pair,
                        max_pair=max_pair,
                        name_prefix=f"G{g.id_group}_{daykey}",
                        allow_lunch_gap=rules.allow_lunch_gap,
                        lunch_min=rules.lunch_gap_min_pair,
                        lunch_max=rules.lunch_gap_max_pair,
                    )
                    penalties.append(rules.w_students_gaps * gaps)

            # 1c) баланс нагрузки студентов по дням недели
            loads = [group_load_day[(g.id_group, dk)] for dk in all_daykeys]
            if loads:
                # avg приблизим целым: avg = round(sum / n) (через int division)
                total = model.NewIntVar(0, max_pair * len(loads), f"totload_G{g.id_group}")
                model.Add(total == sum(loads))
                avg = model.NewIntVar(0, max_pair, f"avgload_G{g.id_group}")
                # avg * n <= total < (avg+1) * n
                n = len(loads)
                model.Add(avg * n <= total)
                model.Add(total < (avg + 1) * n)

                # sum (load-avg)^2 — квадраты напрямую не линейны; MVP: L1-отклонение
                devs = []
                for j, ld in enumerate(loads):
                    dev = model.NewIntVar(0, max_pair, f"dev_G{g.id_group}_{j}")
                    model.AddAbsEquality(dev, ld - avg)
                    devs.append(dev)
                penalties.append(rules.w_students_balance * sum(devs))

        # 2) Преподаватели: окна, >4 пары/день, методдень
        for t in teachers:
            soft_max = min(rules.teacher_soft_max_pairs, t.soft_max_pairs_per_day)

            for daykey in all_daykeys:
                # occupied_by_pair for teacher/day
                occupied_by_pair = {}
                for s in slots:
                    if _key_day(s) != daykey:
                        continue
                    occupied_by_pair[s.pair_number] = teacher_occ_pair.get((t.id_teacher, daykey, s.pair_number), None)

                # load
                load = model.NewIntVar(0, max_pair, f"loadT_T{t.id_teacher}_{daykey}")
                model.Add(load == sum((occupied_by_pair.get(p) or 0) for p in range(1, max_pair + 1)))

                # 2a) штраф за нагрузку сверх soft_max: 5 -> 1, 6 -> 3 (настраиваемо)
                over_soft = model.NewIntVar(0, max_pair, f"overSoft_T{t.id_teacher}_{daykey}")
                model.AddMaxEquality(over_soft, [0, load - soft_max])

                # усилим штраф: over_soft=1 (5 пар), over_soft=2 (6 пар при soft=4) — хотим 3
                # Сделаем piecewise: penalty_units = over_soft + is_six * 1 (добавка)
                is_six = model.NewBoolVar(f"isSix_T{t.id_teacher}_{daykey}")
                model.Add(load == 6).OnlyEnforceIf(is_six)
                model.Add(load != 6).OnlyEnforceIf(is_six.Not())
                penalty_units = model.NewIntVar(0, 10, f"penUnits_T{t.id_teacher}_{daykey}")
                model.Add(penalty_units == over_soft + is_six)  # при 6 добавит +1 (пример)
                penalties.append(rules.w_teacher_over_soft * penalty_units)

                # 2b) окна у преподавателя (допустимы, но лучше меньше)
                gaps = _gaps_for_day(
                    model=model,
                    occupied_by_pair={
                    p: (occupied_by_pair.get(p) if occupied_by_pair.get(p) is not None else model.NewConstant(0))
                    for p in range(1, max_pair + 1)
                        },
                    max_pair=max_pair,
                    name_prefix=f"T{t.id_teacher}_{daykey}",
                    allow_lunch_gap=rules.allow_lunch_gap,
                    lunch_min=rules.lunch_gap_min_pair,
                    lunch_max=rules.lunch_gap_max_pair,
                )
                penalties.append(rules.w_teacher_gaps * gaps)

            # 2c) методдень (по возможности 1 раз в неделю)
            if rules.consider_method_day and t.needs_method_day:
                # группируем daykeys по (week_number, week_type)
                by_week = defaultdict(list)
                for dk in all_daykeys:
                    by_week[(dk[0], dk[1])].append(dk)

                for week_key, dks in by_week.items():
                    day_has_class = []
                    for dk in dks:
                        # has_class = OR(occ pairs)
                        occs = [
                            teacher_occ_pair[(t.id_teacher, dk, p)]
                            for p in range(1, max_pair + 1)
                            if (t.id_teacher, dk, p) in teacher_occ_pair
                        ]
                        has_class = _or_bool(model, occs, f"hasClass_T{t.id_teacher}_{dk}")
                        day_has_class.append(has_class)

                    free_days = []
                    for i, hc in enumerate(day_has_class):
                        fd = model.NewBoolVar(f"freeDay_T{t.id_teacher}_{week_key}_{i}")
                        # fd = NOT has_class
                        model.Add(fd + hc == 1)
                        free_days.append(fd)

                    has_free = _or_bool(model, free_days, f"hasFree_T{t.id_teacher}_{week_key}")
                    method_pen = model.NewIntVar(0, 1, f"methodPen_T{t.id_teacher}_{week_key}")
                    # method_pen = 1 - has_free
                    model.Add(method_pen + has_free == 1)
                    penalties.append(rules.w_method_day * method_pen)

        # 3) Лекции “в начале дня”
        for e in events:
            if e.part_type.lower() != "lecture":
                continue
            opts = event_options[e.id_event]
            # lecture_late_units = sum x_i * max(0, pair-L)
            late_terms = []
            for i, (slot_id, _teacher_id, _room_id) in enumerate(opts):
                pair = slot_by_id[slot_id].pair_number
                units = max(0, pair - rules.lecture_preferred_last_pair)
                if units == 0:
                    continue
                late_terms.append(units * x[(e.id_event, i)])
            if late_terms:
                penalties.append(rules.w_lecture_late * sum(late_terms))

        # no-good cuts (чтобы получить другой вариант)
        # -------------------------------------------------------
        for prev in nogood_assignments:
            # Запрещаем повторить для всех событий те же выбранные (slot,teacher,room)
            # Реализация: сумма "совпало" <= len(events)-1
            same_lits = []
            for e in events:
                slot_id, teacher_id, room_id = prev[e.id_event]
                # найдём индекс опции, которая соответствует этому триплету
                opts = event_options[e.id_event]
                try:
                    idx = opts.index((slot_id, teacher_id, room_id))
                except ValueError:
                    continue
                same_lits.append(x[(e.id_event, idx)])
            if same_lits:
                model.Add(sum(same_lits) <= len(same_lits) - 1)

        # Objective
        model.Minimize(sum(penalties))

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit_seconds)
        solver.parameters.random_seed = int(random_seed + sol_index)
        solver.parameters.num_search_workers = 8  # можно 1, если нужно детерминированнее

        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break

        # Extract solution
        entries: List[SolutionEntry] = []
        assignment_map: Dict[int, Tuple[int, int, int]] = {}

        for e in events:
            idx = solver.Value(chosen_option_idx[e.id_event])
            slot_id, teacher_id, room_id = event_options[e.id_event][idx]
            assignment_map[e.id_event] = (slot_id, teacher_id, room_id)
            entries.append(SolutionEntry(e.id_event, slot_id, teacher_id, room_id))

        solutions.append(Solution(entries=entries, objective_value=int(solver.ObjectiveValue())))
        nogood_assignments.append(assignment_map)

    return solutions


# -----------------------------
# Example: how to build Events from semester hours
# -----------------------------

def build_events_from_semester_hours(
    *,
    curriculum_items: List[CurriculumItem],
    semester_hours_by_curriculum: Dict[int, int],  # curriculum_id -> hours_in_semester
    hours_per_pair: int = 2,
    weekly_plan: Optional[Dict[Tuple[int, int], int]] = None,
    # weekly_plan: (curriculum_id, week_number_in_semester) -> hours_this_week
    week_type_mode: bool = True,
) -> List[Event]:
    """
    Превращает семестровые часы в список Event (по одной паре).
    Если weekly_plan задан, то события получают fixed_week_number (и week_type можно определить по вашей таблице недель).

    В MVP: если weekly_plan задан — создаём события с фиксацией только week_number.
    week_type (1/2) можно проставить отдельно, когда у вас есть SemesterWeeks.
    """
    events: List[Event] = []
    eid = 1

    cur_by_id = {c.id_curriculum: c for c in curriculum_items}

    for cur_id, sem_hours in semester_hours_by_curriculum.items():
        cur = cur_by_id[cur_id]
        total_pairs = sem_hours // hours_per_pair

        if weekly_plan:
            # распределение по неделям
            # суммарные пары по неделям
            week_pairs = {}
            for (cid, w), hrs in weekly_plan.items():
                if cid != cur_id:
                    continue
                week_pairs[w] = hrs // hours_per_pair

            for w, cnt in sorted(week_pairs.items()):
                for _ in range(cnt):
                    events.append(Event(
                        id_event=eid,
                        curriculum_id=cur.id_curriculum,
                        group_id=cur.group_id,
                        subject_id=cur.subject_id,
                        part_type=cur.part_type,
                        required_room_type=cur.required_room_type,
                        fixed_week_number=w,
                        fixed_week_type=None,
                    ))
                    eid += 1
        else:
            # без недельного плана: просто создаём N событий, неделю/слот выберет решатель
            for _ in range(total_pairs):
                events.append(Event(
                    id_event=eid,
                    curriculum_id=cur.id_curriculum,
                    group_id=cur.group_id,
                    subject_id=cur.subject_id,
                    part_type=cur.part_type,
                    required_room_type=cur.required_room_type,
                ))
                eid += 1

    return events


# -----------------------------
# Minimal smoke test template (fill your data)
# -----------------------------
if __name__ == "__main__":
    # Заглушки — подставь реальные данные из БД/импорта
    teachers = [
        Teacher(1, "Иванов И.И."),
        Teacher(2, "Петров П.П.", needs_method_day=False),
    ]
    groups = [
        StudentGroup(1, "ИВТ-21", quantity=25),
    ]
    rooms = [
        Room(1, "101", "lecture", 80),
        Room(2, "202", "computer", 30),
    ]
    slots = []
    slot_id = 1
    # пример: 2 недели (week_type 1/2), 5 дней, 5 пар
    for week_number in range(1, 3):  # week_number_in_semester
        for week_type in (1, 2):
            for day in range(1, 6):
                for pair in range(1, 6):
                    slots.append(TimeSlot(
                        id_slot=slot_id,
                        week_number_in_semester=week_number,
                        week_type=week_type,
                        day_of_week=day,
                        pair_number=pair,
                        is_lunch_break=False
                    ))
                    slot_id += 1

    curriculum_items = [
        CurriculumItem(1, group_id=1, subject_id=1, part_type="lecture", required_room_type="lecture"),
        CurriculumItem(2, group_id=1, subject_id=2, part_type="lab", required_room_type="computer"),
    ]
    curriculum = {c.id_curriculum: c for c in curriculum_items}

    teacher_subjects = {
        (1, 1): True,
        (1, 2): True,
        (2, 1): True,
        (2, 2): False,
    }

    # Все доступны по умолчанию, но можно запретить отдельные слоты:
    teacher_availability = defaultdict(lambda: True)
    # teacher_availability[(1, some_slot_id)] = False

    # Семестр: математика 24 часа => 12 пар, лабораторные 8 часов => 4 пары
    semester_hours = {1: 24, 2: 8}
    events = build_events_from_semester_hours(
        curriculum_items=curriculum_items,
        semester_hours_by_curriculum=semester_hours,
        hours_per_pair=2,
    )

    rules = Rules()

    sols = solve_schedule(
        teachers=teachers,
        groups=groups,
        rooms=rooms,
        slots=slots,
        curriculum=curriculum,
        events=events,
        teacher_subjects=teacher_subjects,
        teacher_availability=teacher_availability,
        rules=rules,
        k_solutions=3,
        time_limit_seconds=5,
    )

    print(f"Found {len(sols)} solution(s)")
    for i, sol in enumerate(sols, 1):
        print(f"\nVariant #{i}, objective={sol.objective_value}")
        # покажем первые 10 назначений
        for e in sol.entries[:10]:
            s = next(ss for ss in slots if ss.id_slot == e.slot_id)
            print(f"  event={e.event_id} slot={e.slot_id} "
                  f"(w{ s.week_number_in_semester } wt{ s.week_type } d{ s.day_of_week } p{ s.pair_number }) "
                  f"teacher={e.teacher_id} room={e.room_id}")