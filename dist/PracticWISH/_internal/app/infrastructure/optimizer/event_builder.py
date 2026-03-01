# app/infrastructure/optimizer/event_builder.py
"""
EventBuilder

Задача:
- превратить учебный план на семестр (CurriculumSemesterPlan + WeeklyLoadPlan)
  в список событий Event (одно событие = одна пара)
- учесть неравномерность по неделям, если задан WeeklyLoadPlan
- учесть locks (если запись закреплена, можно вернуть Event с fixed_week/slot и т.п.)

Важно:
- Это инфраструктурный слой, потому что он читает данные из репозиториев/БД
- Но возвращает доменные сущности (Event) и работает с domain-моделями

Ожидаемые методы репозитория curriculum_repo/calendar_repo в MVP:
- curriculum_repo.get_semester_plans(calendar_id) -> list[CurriculumSemesterPlan]
- curriculum_repo.get_curriculum_items_for_plans(plan_ids) -> dict[curriculum_id] -> CurriculumItem
- curriculum_repo.get_weekly_load(plan_id) -> list[WeeklyLoadPlan] (week_id, hours_this_week)
- calendar_repo.get_week_by_id(week_id) -> SemesterWeek (week_number_in_semester, week_type)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional

from app.domain.models import (
    Event,
    CurriculumItem,
    CurriculumSemesterPlan,
    WeeklyLoadPlan,
    SemesterWeek,
)


@dataclass(frozen=True)
class LockHint:
    """
    Минимальная подсказка о локах.
    Если дальше хочешь — расширяй.
    """
    event_id: int
    slot_id: Optional[int] = None
    teacher_id: Optional[int] = None
    room_id: Optional[int] = None


class EventBuilder:
    def __init__(self, curriculum_repo, calendar_repo, rules_repo=None):
        self._curriculum_repo = curriculum_repo
        self._calendar_repo = calendar_repo
        self._rules_repo = rules_repo  # задел на будущие настройки из БД

    # ---------------------------------------------------------

    def build_events(
        self,
        calendar_id: int,
        hours_per_pair: int,
        locks: Optional[list] = None,
    ) -> List[Event]:
        """
        Возвращает список Event для solver.

        Алгоритм:
        1) Берём планы на семестр (CurriculumSemesterPlan)
        2) Для каждого плана:
           - если есть WeeklyLoadPlan -> создаём события по неделям
           - иначе -> создаём events на весь семестр без привязки к неделе
        """

        # locks: список объектов из schedule_repo
        lock_map: Dict[int, LockHint] = {}
        if locks:
            for lk in locks:
                # ожидаем поля event_id/curriculum_id — зависит от твоей реализации
                # здесь используем максимально “терпимый” подход:
                event_id = getattr(lk, "event_id", None)
                if event_id is None:
                    continue
                lock_map[event_id] = LockHint(
                    event_id=event_id,
                    slot_id=getattr(lk, "slot_id", None),
                    teacher_id=getattr(lk, "teacher_id", None),
                    room_id=getattr(lk, "room_id", None),
                )

        plans: List[CurriculumSemesterPlan] = self._curriculum_repo.get_semester_plans(calendar_id)

        if not plans:
            return []

        # подтягиваем CurriculumItem по curriculum_id
        curriculum_items: Dict[int, CurriculumItem] = self._curriculum_repo.get_curriculum_items_for_plans(
            [p.id_plan for p in plans]
        )

        events: List[Event] = []
        next_event_id = 1

        for plan in plans:
            cur = curriculum_items.get(plan.curriculum_id)
            if cur is None:
                continue

            # сколько пар нужно на семестр по этому плану
            total_pairs = plan.hours_in_semester // hours_per_pair

            # есть ли недельное распределение?
            weekly: List[WeeklyLoadPlan] = self._curriculum_repo.get_weekly_load(plan.id_plan)

            if weekly:
                # weekly hours -> weekly pairs
                for w in weekly:
                    week: SemesterWeek = self._calendar_repo.get_week_by_id(w.week_id)

                    week_pairs = w.hours_this_week // hours_per_pair
                    for _ in range(week_pairs):
                        eid = next_event_id
                        next_event_id += 1

                        # если для этого event уже есть lock — можно проставить фиксированную неделю
                        lk = lock_map.get(eid)

                        fixed_week_number = week.week_number_in_semester
                        fixed_week_type = week.week_type

                        # если lock фиксирует слот — фактически он фиксирует неделю тоже
                        # но slot_id мы в Event не храним (solver примет locks отдельно)
                        events.append(Event(
                            id_event=eid,
                            curriculum_id=cur.id_curriculum,
                            group_id=cur.group_id,
                            subject_id=cur.subject_id,
                            part_type=cur.part_type,
                            required_room_type=cur.required_room_type,
                            fixed_week_number=fixed_week_number,
                            fixed_week_type=fixed_week_type,
                        ))

            else:
                # без недельного плана — просто события без привязки к неделе
                for _ in range(total_pairs):
                    eid = next_event_id
                    next_event_id += 1
                    events.append(Event(
                        id_event=eid,
                        curriculum_id=cur.id_curriculum,
                        group_id=cur.group_id,
                        subject_id=cur.subject_id,
                        part_type=cur.part_type,
                        required_room_type=cur.required_room_type,
                        fixed_week_number=None,
                        fixed_week_type=None,
                    ))

        return events