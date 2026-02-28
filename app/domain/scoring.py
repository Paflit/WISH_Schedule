# app/domain/scoring.py
"""
Расчёт метрик и "штрафов" для уже построенного расписания.

Зачем нужен scoring:
- Solver (OR-Tools) оптимизирует по своей objective, но GUI нужно:
  * показать понятные метрики (окна, перегрузы, методдни, лекции не в начале)
  * сравнивать варианты
  * пересчитывать score после ручных правок (без перезапуска solver)

Важно:
- Здесь нет OR-Tools
- Здесь нет БД/Qt
- На вход подаём "плоские" записи (SolutionEntry или DTO) + справочники слотов
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple, Optional, Set, Any
from collections import defaultdict

from app.domain.models import TimeSlot, ScheduleMetrics
from app.domain.rules import SchedulingRules


# -----------------------------
# Helpers
# -----------------------------

def day_key(slot: TimeSlot) -> Tuple[int, int, int]:
    """(week_number_in_semester, week_type, day_of_week)"""
    return (slot.week_number_in_semester, slot.week_type, slot.day_of_week)


def _count_gaps(
    occupied_pairs: Set[int],
    max_pair: int,
    allow_lunch_gap: bool,
    lunch_min: int,
    lunch_max: int,
) -> int:
    """
    occupied_pairs: {pair_number,...} в рамках одного дня.
    Окна = количество пустых пар между первой и последней занятой парой.
    Обеденный разрыв (если разрешён) не считаем как окно.
    """
    if not occupied_pairs:
        return 0

    first_p = min(occupied_pairs)
    last_p = max(occupied_pairs)
    gaps = 0
    for p in range(first_p, last_p + 1):
        if p in occupied_pairs:
            continue
        if allow_lunch_gap and lunch_min <= p <= lunch_max:
            # считаем, что "обеденный слот" может быть пустым без штрафа
            continue
        gaps += 1
    return gaps


def _student_day_load_penalty(load: int, rules: SchedulingRules) -> int:
    """
    Возвращает "units" штрафа (без веса): насколько вышли за границы 2..5.
    """
    under = max(0, rules.min_pairs_students_per_day - load)
    over = max(0, load - rules.max_pairs_students_per_day)
    return under + over


def _teacher_over_soft_units(load: int, soft_max: int) -> int:
    """
    Возвращает "units" штрафа (без веса) за нагрузку преподавателя.
    Рекомендуемая схема:
      <= soft_max: 0
      soft_max+1 (обычно 5): 1
      soft_max+2 (обычно 6): 3  (сильнее, крайний случай)
    """
    if load <= soft_max:
        return 0
    if load == soft_max + 1:
        return 1
    # 6 пар при soft=4 -> хотим 3 units, а не 2
    if load >= soft_max + 2:
        return 3 + (load - (soft_max + 2)) * 2  # на всякий случай, если появятся >6
    return load - soft_max


def _lecture_late_units(pair_number: int, rules: SchedulingRules) -> int:
    """
    Units штрафа за лекцию не в начале дня (без веса).
    """
    return max(0, pair_number - rules.lecture_preferred_last_pair)


# -----------------------------
# Scoring API
# -----------------------------

@dataclass(frozen=True)
class ScoreBreakdown:
    """
    Детальная расшифровка для UI (если нужно).
    total_penalty = сумма всех (weight * units).
    """
    total_penalty: int

    # units
    student_gaps_units: int
    teacher_gaps_units: int
    student_day_load_units: int
    teacher_over_soft_units: int
    method_day_violations_units: int
    lecture_late_units: int

    # weighted parts
    student_gaps_penalty: int
    teacher_gaps_penalty: int
    student_day_load_penalty: int
    teacher_over_soft_penalty: int
    method_day_penalty: int
    lecture_late_penalty: int


def compute_metrics(
    *,
    entries: Iterable[Any],
    slots_by_id: Dict[int, TimeSlot],
    rules: SchedulingRules,
    teacher_soft_max_by_id: Optional[Dict[int, int]] = None,
    consider_method_day_by_teacher: Optional[Dict[int, bool]] = None,
    event_part_type_by_event_id: Optional[Dict[int, str]] = None,
) -> Tuple[ScheduleMetrics, ScoreBreakdown]:
    """
    Универсальный расчёт.

    entries: элементы должны иметь поля/атрибуты:
        - slot_id
        - group_id
        - teacher_id
        - event_id (опционально, но нужен для лекций)
    slots_by_id: dict[slot_id] -> TimeSlot
    teacher_soft_max_by_id: если нет — используем rules.teacher_soft_max_pairs
    consider_method_day_by_teacher: если нет — считаем всем, если rules.consider_method_day=True
    event_part_type_by_event_id: если нет — лекции не считаем (или можно передать)

    Возвращает:
      (ScheduleMetrics, ScoreBreakdown)
    """

    # --- Собираем занятость по дням и парам ---
    # group_occ[(group_id, daykey)] -> set(pair_number)
    group_occ: Dict[Tuple[int, Tuple[int, int, int]], Set[int]] = defaultdict(set)
    teacher_occ: Dict[Tuple[int, Tuple[int, int, int]], Set[int]] = defaultdict(set)

    # для лекций
    lecture_late_units = 0

    # деньки по неделям для методдня: teacher_days[(teacher_id, (week_number, week_type))] -> set(day_of_week with any class)
    teacher_days_with_classes: Dict[Tuple[int, Tuple[int, int]], Set[int]] = defaultdict(set)

    max_pair = 0
    for e in entries:
        slot = slots_by_id[getattr(e, "slot_id")]
        dk = day_key(slot)
        max_pair = max(max_pair, slot.pair_number)

        group_id = getattr(e, "group_id")
        teacher_id = getattr(e, "teacher_id")

        group_occ[(group_id, dk)].add(slot.pair_number)
        teacher_occ[(teacher_id, dk)].add(slot.pair_number)

        teacher_days_with_classes[(teacher_id, (slot.week_number_in_semester, slot.week_type))].add(slot.day_of_week)

        # лекции
        if event_part_type_by_event_id is not None:
            event_id = getattr(e, "event_id", None)
            if event_id is not None:
                part_type = (event_part_type_by_event_id.get(event_id) or "").lower()
                if part_type == "lecture":
                    lecture_late_units += _lecture_late_units(slot.pair_number, rules)

    # список всех daykey, чтобы корректно считать методдень (знать, какие дни недели вообще есть)
    all_daykeys: Set[Tuple[int, int, int]] = set()
    all_weeks: Set[Tuple[int, int]] = set()
    all_days_of_week: Set[int] = set()
    for slot in slots_by_id.values():
        dk = day_key(slot)
        all_daykeys.add(dk)
        all_weeks.add((slot.week_number_in_semester, slot.week_type))
        all_days_of_week.add(slot.day_of_week)

    # --- Студенты: окна + нагрузка в день + баланс (L1) ---
    student_gaps_units = 0
    student_day_load_units = 0

    # Нам нужны все группы, присутствующие в расписании
    groups_in_schedule = {gid for (gid, _dk) in group_occ.keys()}

    # Баланс считаем как сумма |load - avg|
    student_balance_units_total = 0

    for gid in groups_in_schedule:
        loads: List[int] = []
        for dk in all_daykeys:
            occ = group_occ.get((gid, dk), set())
            load = len(occ)
            loads.append(load)

            # нагрузка 2..5 (units)
            student_day_load_units += _student_day_load_penalty(load, rules)

            # окна (если запрещены)
            if not rules.allow_student_gaps:
                student_gaps_units += _count_gaps(
                    occupied_pairs=occ,
                    max_pair=max_pair,
                    allow_lunch_gap=rules.allow_lunch_gap,
                    lunch_min=rules.lunch_gap_min_pair,
                    lunch_max=rules.lunch_gap_max_pair,
                )

        if loads:
            avg = round(sum(loads) / len(loads))
            student_balance_units_total += sum(abs(l - avg) for l in loads)

    # --- Преподаватели: окна + перегруз > soft_max ---
    teacher_gaps_units = 0
    teacher_over_soft_units = 0

    teachers_in_schedule = {tid for (tid, _dk) in teacher_occ.keys()}

    for tid in teachers_in_schedule:
        soft_max = (teacher_soft_max_by_id or {}).get(tid, rules.teacher_soft_max_pairs)

        for dk in all_daykeys:
            occ = teacher_occ.get((tid, dk), set())
            load = len(occ)

            teacher_over_soft_units += _teacher_over_soft_units(load, soft_max)
            teacher_gaps_units += _count_gaps(
                occupied_pairs=occ,
                max_pair=max_pair,
                allow_lunch_gap=rules.allow_lunch_gap,
                lunch_min=rules.lunch_gap_min_pair,
                lunch_max=rules.lunch_gap_max_pair,
            )

    # --- Методдень: 1 раз в неделю день без занятий (если включено) ---
    method_day_violations_units = 0
    if rules.consider_method_day:
        # Для каждого преподавателя и каждой недели проверим: есть ли хотя бы 1 день без занятий
        for tid in teachers_in_schedule:
            consider = True
            if consider_method_day_by_teacher is not None:
                consider = bool(consider_method_day_by_teacher.get(tid, True))
            if not consider:
                continue

            for wk in all_weeks:
                busy_days = teacher_days_with_classes.get((tid, wk), set())
                # если расписание этой недели реально использует не все дни, всё равно по регламенту
                # методдень можно считать по списку days_of_week в сетке слотов
                has_free = len(busy_days) < len(all_days_of_week)
                if not has_free:
                    method_day_violations_units += 1

    # --- Взвешивание ---
    student_gaps_penalty = rules.w_students_gaps * student_gaps_units
    teacher_gaps_penalty = rules.w_teacher_gaps * teacher_gaps_units
    student_day_load_penalty = rules.w_students_day_load * student_day_load_units
    teacher_over_soft_penalty = rules.w_teacher_over_soft * teacher_over_soft_units
    method_day_penalty = rules.w_method_day * method_day_violations_units
    lecture_late_penalty = rules.w_lecture_late * lecture_late_units
    student_balance_penalty = rules.w_students_balance * student_balance_units_total

    total_penalty = (
        student_gaps_penalty
        + teacher_gaps_penalty
        + student_day_load_penalty
        + teacher_over_soft_penalty
        + method_day_penalty
        + lecture_late_penalty
        + student_balance_penalty
    )

    metrics = ScheduleMetrics(
        total_penalty=total_penalty,
        student_gaps=student_gaps_units,
        teacher_gaps=teacher_gaps_units,
        student_overloads=student_day_load_units,
        teacher_overloads=teacher_over_soft_units,
        method_day_violations=method_day_violations_units,
        lecture_late_penalty=lecture_late_penalty,
    )

    breakdown = ScoreBreakdown(
        total_penalty=total_penalty,

        student_gaps_units=student_gaps_units,
        teacher_gaps_units=teacher_gaps_units,
        student_day_load_units=student_day_load_units,
        teacher_over_soft_units=teacher_over_soft_units,
        method_day_violations_units=method_day_violations_units,
        lecture_late_units=lecture_late_units,

        student_gaps_penalty=student_gaps_penalty,
        teacher_gaps_penalty=teacher_gaps_penalty,
        student_day_load_penalty=student_day_load_penalty,
        teacher_over_soft_penalty=teacher_over_soft_penalty,
        method_day_penalty=method_day_penalty,
        lecture_late_penalty=lecture_late_penalty,
    )

    return metrics, breakdown


def compute_metrics_from_dto(
    *,
    entries: Iterable[Any],
    slots_by_id: Dict[int, TimeSlot],
    rules: SchedulingRules,
) -> ScheduleMetrics:
    """
    Упрощённый помощник: если у тебя в GUI уже ScheduleEntryDTO и тебе нужны только метрики.
    """
    metrics, _ = compute_metrics(
        entries=entries,
        slots_by_id=slots_by_id,
        rules=rules,
        # part_type у DTO есть напрямую — но lecture-проверка через event_id map.
        # Можно расширить, если захочешь учитывать лекции и из DTO.
    )
    return metrics