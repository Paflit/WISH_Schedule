# app/domain/rules.py
"""
Правила (constraints) и профили оптимизации.

Содержит:
- SchedulingRules: параметры регламента и веса штрафов (soft)
- DefaultRuleProfiles: наборы готовых профилей для UI:
    - students (комфорт студентов)
    - teachers (комфорт преподавателей)
    - balanced (баланс)
    - rooms (акцент на аудитории) — задел

ВАЖНО:
- Это доменные настройки, не зависят от БД/Qt.
- В идеале их можно хранить в БД (SchedulingRules table),
  но для MVP держим дефолты здесь.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class SchedulingRules:
    # --------- Students (hard/soft policy) ----------
    min_pairs_students_per_day: int = 2
    max_pairs_students_per_day: int = 5
    allow_student_gaps: bool = False
    allow_lunch_gap: bool = True
    lunch_gap_min_pair: int = 2
    lunch_gap_max_pair: int = 3

    # --------- Teachers ----------
    teacher_hard_max_pairs: int = 6
    teacher_soft_max_pairs: int = 4
    consider_method_day: bool = True

    # --------- Lectures ----------
    lecture_preferred_last_pair: int = 2  # лекции желательно не позже этой пары

    # --------- Weights (soft penalties) ----------
    w_students_day_load: int = 500
    w_students_gaps: int = 600
    w_students_balance: int = 40
    w_teacher_over_soft: int = 700
    w_teacher_gaps: int = 150
    w_method_day: int = 250
    w_lecture_late: int = 70


class DefaultRuleProfiles:
    """
    Готовые профили оптимизации.
    GUI показывает их в выпадающем списке.
    """

    def __init__(self) -> None:
        self._profiles: Dict[str, SchedulingRules] = {
            # Акцент на отсутствие окон и адекватную нагрузку студентов
            "students": SchedulingRules(
                w_students_day_load=700,
                w_students_gaps=900,
                w_students_balance=60,
                w_teacher_over_soft=500,
                w_teacher_gaps=120,
                w_method_day=200,
                w_lecture_late=100,
            ),
            # Акцент на нагрузку преподавателей и методдень
            "teachers": SchedulingRules(
                w_students_day_load=400,
                w_students_gaps=500,
                w_students_balance=20,
                w_teacher_over_soft=900,
                w_teacher_gaps=250,
                w_method_day=450,
                w_lecture_late=50,
            ),
            # Сбалансированный профиль (по умолчанию)
            "balanced": SchedulingRules(
                w_students_day_load=500,
                w_students_gaps=600,
                w_students_balance=40,
                w_teacher_over_soft=700,
                w_teacher_gaps=150,
                w_method_day=250,
                w_lecture_late=70,
            ),
            # Задел: если позже добавим штрафы по загрузке аудиторий/корпусов
            "rooms": SchedulingRules(
                w_students_day_load=450,
                w_students_gaps=550,
                w_students_balance=35,
                w_teacher_over_soft=650,
                w_teacher_gaps=120,
                w_method_day=220,
                w_lecture_late=60,
            ),
        }

    def list_keys(self) -> list[str]:
        return list(self._profiles.keys())

    def get(self, key: str) -> Optional[SchedulingRules]:
        return self._profiles.get(key)