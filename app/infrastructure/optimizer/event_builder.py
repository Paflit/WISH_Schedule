from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class LockHint:
    event_id: int
    slot_id: Optional[int] = None
    teacher_id: Optional[int] = None
    room_id: Optional[int] = None


def _parse_room_types(room_type: str | None) -> set[str]:
    if not room_type:
        return set()
    return {x.strip() for x in str(room_type).split(",") if x.strip()}


def _room_matches_required(room, required_room_type: str) -> bool:
    return required_room_type in _parse_room_types(getattr(room, "room_type", ""))


class EventBuilder:
    """
    Построитель событий генерации.

    Основные принципы:
    - строим события из semester plan + weekly plan
    - учитываем реальный week_number_in_semester, если он задан
    - не создаём пустые/нулевые события
    - лекции можно объединять между группами, но только если суммарный размер
      влезает хотя бы в одну подходящую аудиторию
    """

    def __init__(self, curriculum_repo, calendar_repo, groups_repo, rooms_repo, rules_repo=None):
        self._curriculum_repo = curriculum_repo
        self._calendar_repo = calendar_repo
        self._groups_repo = groups_repo
        self._rooms_repo = rooms_repo
        self._rules_repo = rules_repo

    # ---------------------------------------------------------
    # Public
    # ---------------------------------------------------------

    def build_events(
        self,
        calendar_id: int,
        hours_per_pair: int,
        locks: Optional[list] = None,
    ) -> List[object]:
        if int(hours_per_pair) <= 0:
            raise ValueError("hours_per_pair must be > 0")

        # lock hints пока только нормализуем и держим для совместимости
        lock_map: Dict[int, LockHint] = {}
        if locks:
            for lk in locks:
                event_id = getattr(lk, "event_id", None)
                if event_id is None:
                    continue
                lock_map[int(event_id)] = LockHint(
                    event_id=int(event_id),
                    slot_id=getattr(lk, "slot_id", None),
                    teacher_id=getattr(lk, "teacher_id", None),
                    room_id=getattr(lk, "room_id", None),
                )

        # 1) semester plans выбранного полугодия
        plans = self._curriculum_repo.get_semester_plans(calendar_id)
        plans = [p for p in plans if int(getattr(p, "hours_in_semester", 0) or 0) > 0]
        if not plans:
            return []

        # 2) curriculum items
        curriculum_items = self._curriculum_repo.get_curriculum_items_for_plans(plans)
        if not curriculum_items:
            return []

        # 3) weekly plan
        weekly_rows = self._curriculum_repo.get_weekly_plans(calendar_id)
        weekly_rows = [w for w in weekly_rows if self._is_valid_weekly_row(w)]

        weekly_by_plan_id: Dict[int, List[object]] = {}
        for w in weekly_rows:
            weekly_by_plan_id.setdefault(int(w.plan_id), []).append(w)

        # Чтобы weekly rows были стабильны по неделе
        for plan_id, rows in weekly_by_plan_id.items():
            rows.sort(
                key=lambda w: (
                    int(getattr(w, "week_number_in_semester", 0) or 0),
                    int(getattr(w, "week_type", 0) or 0),
                    int(getattr(w, "week_id", 0) or 0),
                )
            )

        # 4) строим атомарные события
        atomic_events: List[SimpleNamespace] = []
        next_event_id = 1

        for plan in plans:
            curriculum_id = int(plan.curriculum_id)
            item = curriculum_items.get(curriculum_id)
            if item is None:
                continue

            plan_id = int(plan.id_plan)
            plan_weekly_rows = weekly_by_plan_id.get(plan_id, [])

            if plan_weekly_rows:
                for w in plan_weekly_rows:
                    hours_this_week = int(getattr(w, "hours_this_week", 0) or 0)

                    # только полные пары
                    event_count = hours_this_week // int(hours_per_pair)
                    if event_count <= 0:
                        continue

                    fixed_week_number = self._normalize_week_number(
                        getattr(w, "week_number_in_semester", None)
                    )
                    fixed_week_type = self._normalize_week_type(
                        getattr(w, "week_type", None)
                    )

                    for _ in range(event_count):
                        atomic_events.append(
                            self._make_atomic_event(
                                event_id=next_event_id,
                                item=item,
                                fixed_week_number=fixed_week_number,
                                fixed_week_type=fixed_week_type,
                            )
                        )
                        next_event_id += 1
            else:
                # fallback: если weekly plan ещё не построен, строим без привязки к неделе
                total_hours = int(getattr(plan, "hours_in_semester", 0) or 0)
                event_count = total_hours // int(hours_per_pair)
                if event_count <= 0:
                    continue

                for _ in range(event_count):
                    atomic_events.append(
                        self._make_atomic_event(
                            event_id=next_event_id,
                            item=item,
                            fixed_week_number=None,
                            fixed_week_type=None,
                        )
                    )
                    next_event_id += 1

        if not atomic_events:
            return []

        # 5) объединяем лекции с учётом вместимости аудиторий
        merged_events = self._merge_lecture_events_with_capacity(atomic_events)

        # 6) перенумерация для компактного финального набора
        final_events: List[SimpleNamespace] = []
        for idx, e in enumerate(merged_events, start=1):
            final_events.append(
                SimpleNamespace(
                    id_event=idx,
                    curriculum_id=int(e.curriculum_id),
                    curriculum_ids=list(e.curriculum_ids),
                    group_id=int(e.group_id),
                    group_ids=list(e.group_ids),
                    subject_id=int(e.subject_id),
                    part_type=str(e.part_type),
                    required_room_type=str(e.required_room_type),
                    fixed_week_number=self._normalize_week_number(
                        getattr(e, "fixed_week_number", None)
                    ),
                    fixed_week_type=self._normalize_week_type(
                        getattr(e, "fixed_week_type", None)
                    ),
                    merged=bool(getattr(e, "merged", False)),
                )
            )

        return final_events

    # ---------------------------------------------------------
    # Internal
    # ---------------------------------------------------------

    def _is_valid_weekly_row(self, row) -> bool:
        if int(getattr(row, "hours_this_week", 0) or 0) <= 0:
            return False

        is_study_week = getattr(row, "is_study_week", 1)
        if is_study_week is not None and int(is_study_week) == 0:
            return False

        return True

    def _normalize_week_number(self, value) -> Optional[int]:
        if value is None:
            return None
        n = int(value or 0)
        return n if n > 0 else None

    def _normalize_week_type(self, value) -> Optional[int]:
        if value is None:
            return None
        n = int(value or 0)
        return n if n in (1, 2) else None

    def _make_atomic_event(
        self,
        event_id: int,
        item,
        fixed_week_number: Optional[int],
        fixed_week_type: Optional[int],
    ) -> SimpleNamespace:
        return SimpleNamespace(
            id_event=int(event_id),
            curriculum_id=int(item.id_curriculum),
            curriculum_ids=[int(item.id_curriculum)],
            group_id=int(item.group_id),
            group_ids=[int(item.group_id)],
            subject_id=int(item.subject_id),
            part_type=str(item.part_type),
            required_room_type=str(item.required_room_type),
            fixed_week_number=fixed_week_number,
            fixed_week_type=fixed_week_type,
            merged=False,
        )

    def _max_capacity_for_required_type(self, required_room_type: str) -> int:
        rooms = self._rooms_repo.list_all()
        caps = [
            int(r.capacity)
            for r in rooms
            if _room_matches_required(r, required_room_type)
        ]
        return max(caps) if caps else 0

    def _group_sizes(self) -> Dict[int, int]:
        groups = self._groups_repo.list_all()
        return {int(g.id_group): int(g.quantity) for g in groups}

    def _merge_lecture_events_with_capacity(self, events: List[SimpleNamespace]) -> List[SimpleNamespace]:
        """
        Объединяем lecture-события по:
        - subject_id
        - part_type
        - required_room_type
        - fixed_week_number
        - fixed_week_type

        Но каждую пачку групп ограничиваем реальной максимальной вместимостью
        подходящей аудитории.
        """
        lecture_groups: Dict[Tuple, List[SimpleNamespace]] = {}
        non_lecture: List[SimpleNamespace] = []

        for e in events:
            if str(e.part_type) != "lecture":
                non_lecture.append(e)
                continue

            key = (
                int(e.subject_id),
                str(e.part_type),
                str(e.required_room_type),
                self._normalize_week_number(getattr(e, "fixed_week_number", None)),
                self._normalize_week_type(getattr(e, "fixed_week_type", None)),
            )
            lecture_groups.setdefault(key, []).append(e)

        group_sizes = self._group_sizes()
        merged: List[SimpleNamespace] = []

        for _key, items in lecture_groups.items():
            if not items:
                continue

            required_room_type = str(items[0].required_room_type)
            max_cap = self._max_capacity_for_required_type(required_room_type)

            # Если вообще нет подходящей аудитории, не объединяем
            if max_cap <= 0:
                merged.extend(items)
                continue

            # Сначала большие группы — это даёт более устойчивую упаковку
            items = sorted(
                items,
                key=lambda x: (-group_sizes.get(int(x.group_id), 0), int(x.group_id))
            )

            batches: List[List[SimpleNamespace]] = []

            for it in items:
                gsize = int(group_sizes.get(int(it.group_id), 0))
                placed = False

                for batch in batches:
                    current_size = sum(group_sizes.get(int(x.group_id), 0) for x in batch)
                    if current_size + gsize <= max_cap:
                        batch.append(it)
                        placed = True
                        break

                if not placed:
                    batches.append([it])

            for batch in batches:
                group_ids: List[int] = []
                curriculum_ids: List[int] = []

                for it in batch:
                    group_ids.extend(int(x) for x in list(it.group_ids))
                    curriculum_ids.extend(int(x) for x in list(it.curriculum_ids))

                group_ids = list(dict.fromkeys(group_ids))
                curriculum_ids = list(dict.fromkeys(curriculum_ids))

                merged.append(
                    SimpleNamespace(
                        id_event=0,
                        curriculum_id=int(curriculum_ids[0]),
                        curriculum_ids=curriculum_ids,
                        group_id=int(group_ids[0]),
                        group_ids=group_ids,
                        subject_id=int(batch[0].subject_id),
                        part_type="lecture",
                        required_room_type=str(batch[0].required_room_type),
                        fixed_week_number=self._normalize_week_number(
                            getattr(batch[0], "fixed_week_number", None)
                        ),
                        fixed_week_type=self._normalize_week_type(
                            getattr(batch[0], "fixed_week_type", None)
                        ),
                        merged=(len(group_ids) > 1),
                    )
                )

        result = merged + non_lecture
        result.sort(
            key=lambda e: (
                str(e.part_type),
                int(e.subject_id),
                tuple(int(x) for x in e.group_ids),
                -1 if getattr(e, "fixed_week_type", None) is None else int(e.fixed_week_type),
                -1 if getattr(e, "fixed_week_number", None) is None else int(e.fixed_week_number),
            )
        )
        return result