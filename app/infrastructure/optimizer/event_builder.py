from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, Iterable, List, Optional, Tuple

from app.domain.exceptions import ValidationError


@dataclass(frozen=True)
class LockHint:
    event_id: int
    slot_id: Optional[int] = None
    teacher_id: Optional[int] = None
    room_id: Optional[int] = None


def _parse_room_types(room) -> set[str]:
    """
    Поддержка новой модели:
    - если у Room есть room_types -> используем их;
    - иначе откатываемся на старый room_type.

    Важно:
    - room_types может быть list[str]
    - room_type может быть одной строкой или legacy-строкой через запятую
    """
    if room is None:
        return set()

    raw_room_types = getattr(room, "room_types", None)
    if raw_room_types:
        result = {
            str(x).strip().lower()
            for x in list(raw_room_types)
            if str(x).strip()
        }
        if result:
            return result

    raw_room_type = getattr(room, "room_type", None)
    if not raw_room_type:
        return set()

    return {
        x.strip().lower()
        for x in str(raw_room_type).split(",")
        if x.strip()
    }


def _room_matches_required(room, required_room_type: str) -> bool:
    required = str(required_room_type or "").strip().lower()
    if not required:
        return False
    return required in _parse_room_types(room)


class EventBuilder:
    """
    Построитель событий генерации.

    Единица генерации = одна учебная пара, которую solver должен поставить в сетку.

    Основные принципы:
    - строим события из semester plan + weekly plan;
    - используем week_number_in_semester / week_type, если они реально есть;
    - не создаём пустые события;
    - лекции можно объединять между группами, но только:
        * если это одна и та же дисциплина;
        * если совпадает тип занятия и тип аудитории;
        * если совпадает неделя / тип недели;
        * если суммарный размер групп влезает в хотя бы одну подходящую аудиторию;
        * если события не затронуты lock-ами.
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
        calendar_id = int(calendar_id)
        hours_per_pair = int(hours_per_pair)

        if calendar_id <= 0:
            raise ValidationError("calendar_id должен быть положительным числом.")
        if hours_per_pair <= 0:
            raise ValidationError("hours_per_pair должен быть больше 0.")

        lock_map = self._normalize_locks(locks)

        plans = self._load_semester_plans(calendar_id)
        if not plans:
            return []

        curriculum_items = self._curriculum_repo.get_curriculum_items_for_plans(plans)
        if not curriculum_items:
            return []

        weekly_rows = self._load_weekly_rows(calendar_id)
        weekly_by_plan_id = self._group_weekly_rows_by_plan(weekly_rows)

        atomic_events = self._build_atomic_events(
            plans=plans,
            curriculum_items=curriculum_items,
            weekly_by_plan_id=weekly_by_plan_id,
            hours_per_pair=hours_per_pair,
        )
        if not atomic_events:
            return []

        final_events = self._merge_lecture_events_with_capacity(
            events=atomic_events,
            lock_map=lock_map,
        )
        if not final_events:
            return []

        return self._finalize_events(final_events)

    # ---------------------------------------------------------
    # Loaders / validators
    # ---------------------------------------------------------
    def _normalize_locks(self, locks: Optional[list]) -> Dict[int, LockHint]:
        result: Dict[int, LockHint] = {}
        if not locks:
            return result

        for lk in locks:
            event_id = getattr(lk, "event_id", None)
            if event_id is None:
                continue

            try:
                event_id = int(event_id)
            except (TypeError, ValueError):
                continue

            if event_id <= 0:
                continue

            result[event_id] = LockHint(
                event_id=event_id,
                slot_id=self._optional_int(getattr(lk, "slot_id", None)),
                teacher_id=self._optional_int(getattr(lk, "teacher_id", None)),
                room_id=self._optional_int(getattr(lk, "room_id", None)),
            )
        return result

    def _load_semester_plans(self, calendar_id: int) -> List[object]:
        plans = self._curriculum_repo.get_semester_plans(calendar_id)
        plans = [
            p
            for p in plans
            if self._positive_int(getattr(p, "hours_in_semester", 0)) > 0
        ]
        return sorted(
            plans,
            key=lambda p: (
                self._positive_int(getattr(p, "id_plan", 0)),
                self._positive_int(getattr(p, "curriculum_id", 0)),
            ),
        )

    def _load_weekly_rows(self, calendar_id: int) -> List[object]:
        weekly_rows = self._curriculum_repo.get_weekly_plans(calendar_id)
        weekly_rows = [w for w in weekly_rows if self._is_valid_weekly_row(w)]
        return sorted(
            weekly_rows,
            key=lambda w: (
                self._positive_int(getattr(w, "plan_id", 0)),
                self._normalize_week_number(getattr(w, "week_number_in_semester", None)) or 0,
                self._normalize_week_type(getattr(w, "week_type", None)) or 0,
                self._positive_int(getattr(w, "week_id", 0)),
                self._positive_int(getattr(w, "id_week_plan", 0)),
            ),
        )

    def _group_weekly_rows_by_plan(self, weekly_rows: Iterable[object]) -> Dict[int, List[object]]:
        weekly_by_plan_id: Dict[int, List[object]] = {}
        for row in weekly_rows:
            plan_id = self._positive_int(getattr(row, "plan_id", 0))
            if plan_id <= 0:
                continue
            weekly_by_plan_id.setdefault(plan_id, []).append(row)
        return weekly_by_plan_id

    def _is_valid_weekly_row(self, row) -> bool:
        if self._positive_int(getattr(row, "hours_this_week", 0)) <= 0:
            return False

        is_study_week = getattr(row, "is_study_week", 1)
        if is_study_week is not None:
            try:
                if int(is_study_week) == 0:
                    return False
            except (TypeError, ValueError):
                pass

        return True

    # ---------------------------------------------------------
    # Atomic events
    # ---------------------------------------------------------
    def _build_atomic_events(
        self,
        *,
        plans: List[object],
        curriculum_items: Dict[int, object],
        weekly_by_plan_id: Dict[int, List[object]],
        hours_per_pair: int,
    ) -> List[SimpleNamespace]:
        events: List[SimpleNamespace] = []
        next_event_id = 1

        missing_curriculum_ids: List[int] = []

        for plan in plans:
            plan_id = self._positive_int(getattr(plan, "id_plan", 0))
            curriculum_id = self._positive_int(getattr(plan, "curriculum_id", 0))

            item = curriculum_items.get(curriculum_id)
            if item is None:
                missing_curriculum_ids.append(curriculum_id)
                continue

            weekly_rows = weekly_by_plan_id.get(plan_id, [])
            if weekly_rows:
                for weekly_row in weekly_rows:
                    hours_this_week = self._positive_int(
                        getattr(weekly_row, "hours_this_week", 0)
                    )
                    pairs_count = hours_this_week // hours_per_pair
                    if pairs_count <= 0:
                        continue

                    fixed_week_number = self._normalize_week_number(
                        getattr(weekly_row, "week_number_in_semester", None)
                    )
                    fixed_week_type = self._normalize_week_type(
                        getattr(weekly_row, "week_type", None)
                    )

                    for _ in range(pairs_count):
                        events.append(
                            self._make_atomic_event(
                                event_id=next_event_id,
                                item=item,
                                fixed_week_number=fixed_week_number,
                                fixed_week_type=fixed_week_type,
                            )
                        )
                        next_event_id += 1
            else:
                total_hours = self._positive_int(getattr(plan, "hours_in_semester", 0))
                pairs_count = total_hours // hours_per_pair
                if pairs_count <= 0:
                    continue

                for _ in range(pairs_count):
                    events.append(
                        self._make_atomic_event(
                            event_id=next_event_id,
                            item=item,
                            fixed_week_number=None,
                            fixed_week_type=None,
                        )
                    )
                    next_event_id += 1

        if missing_curriculum_ids and not events:
            missing_str = ", ".join(str(x) for x in sorted(set(missing_curriculum_ids))[:10])
            raise ValidationError(
                f"Не удалось построить события: отсутствуют CurriculumItems для curriculum_id: {missing_str}."
            )

        return events

    def _make_atomic_event(
        self,
        *,
        event_id: int,
        item,
        fixed_week_number: Optional[int],
        fixed_week_type: Optional[int],
    ) -> SimpleNamespace:
        curriculum_id = self._positive_int(getattr(item, "id_curriculum", 0))
        group_id = self._positive_int(getattr(item, "group_id", 0))
        subject_id = self._positive_int(getattr(item, "subject_id", 0))
        part_type = str(getattr(item, "part_type", "") or "").strip()
        required_room_type = str(getattr(item, "required_room_type", "") or "").strip().lower()

        if curriculum_id <= 0:
            raise ValidationError("CurriculumItem содержит некорректный id_curriculum.")
        if group_id <= 0:
            raise ValidationError(f"CurriculumItem id={curriculum_id} содержит некорректный group_id.")
        if subject_id <= 0:
            raise ValidationError(f"CurriculumItem id={curriculum_id} содержит некорректный subject_id.")
        if not part_type:
            raise ValidationError(f"CurriculumItem id={curriculum_id} не содержит part_type.")
        if not required_room_type:
            raise ValidationError(
                f"CurriculumItem id={curriculum_id} не содержит required_room_type."
            )

        return SimpleNamespace(
            id_event=int(event_id),
            curriculum_id=curriculum_id,
            curriculum_ids=[curriculum_id],
            group_id=group_id,
            group_ids=[group_id],
            subject_id=subject_id,
            part_type=part_type,
            required_room_type=required_room_type,
            fixed_week_number=fixed_week_number,
            fixed_week_type=fixed_week_type,
            merged=False,
            source_event_ids=[int(event_id)],
        )

    # ---------------------------------------------------------
    # Merge lectures
    # ---------------------------------------------------------
    def _group_sizes(self) -> Dict[int, int]:
        groups = self._groups_repo.list_all()
        result: Dict[int, int] = {}
        for g in groups:
            gid = self._positive_int(getattr(g, "id_group", 0))
            qty = self._positive_int(getattr(g, "quantity", 0))
            if gid > 0:
                result[gid] = max(0, qty)
        return result

    def _max_capacity_for_required_type(self, required_room_type: str) -> int:
        required = str(required_room_type or "").strip().lower()
        rooms = self._rooms_repo.list_all()
        capacities = [
            self._positive_int(getattr(r, "capacity", 0))
            for r in rooms
            if _room_matches_required(r, required)
        ]
        capacities = [c for c in capacities if c > 0]
        return max(capacities) if capacities else 0

    def _is_locked_event(self, event_id: int, lock_map: Dict[int, LockHint]) -> bool:
        return int(event_id) in lock_map

    def _merge_lecture_events_with_capacity(
        self,
        *,
        events: List[SimpleNamespace],
        lock_map: Dict[int, LockHint],
    ) -> List[SimpleNamespace]:
        """
        Объединяем только lecture-события и только если это безопасно.

        Не объединяем:
        - не lecture;
        - события с lock;
        - события без подходящей аудитории;
        - события, которые не влезают суммарно по capacity.
        """
        lecture_groups: Dict[Tuple, List[SimpleNamespace]] = {}
        passthrough: List[SimpleNamespace] = []

        for event in events:
            if str(getattr(event, "part_type", "")) != "lecture":
                passthrough.append(event)
                continue

            if self._is_locked_event(getattr(event, "id_event", 0), lock_map):
                passthrough.append(event)
                continue

            key = (
                self._positive_int(getattr(event, "subject_id", 0)),
                str(getattr(event, "part_type", "")).strip(),
                str(getattr(event, "required_room_type", "")).strip().lower(),
                self._normalize_week_number(getattr(event, "fixed_week_number", None)),
                self._normalize_week_type(getattr(event, "fixed_week_type", None)),
            )
            lecture_groups.setdefault(key, []).append(event)

        group_sizes = self._group_sizes()
        merged_events: List[SimpleNamespace] = []

        for _key, items in lecture_groups.items():
            if not items:
                continue

            required_room_type = str(getattr(items[0], "required_room_type", "")).strip().lower()
            max_capacity = self._max_capacity_for_required_type(required_room_type)

            if max_capacity <= 0:
                passthrough.extend(items)
                continue

            items = sorted(
                items,
                key=lambda x: (
                    -group_sizes.get(self._positive_int(getattr(x, "group_id", 0)), 0),
                    self._positive_int(getattr(x, "group_id", 0)),
                    self._positive_int(getattr(x, "id_event", 0)),
                ),
            )

            batches: List[List[SimpleNamespace]] = []

            for item in items:
                item_group_id = self._positive_int(getattr(item, "group_id", 0))
                item_group_size = group_sizes.get(item_group_id, 0)

                placed = False
                for batch in batches:
                    current_size = sum(
                        group_sizes.get(
                            self._positive_int(getattr(batch_item, "group_id", 0)),
                            0,
                        )
                        for batch_item in batch
                    )
                    if current_size + item_group_size <= max_capacity:
                        batch.append(item)
                        placed = True
                        break

                if not placed:
                    batches.append([item])

            for batch in batches:
                if len(batch) == 1:
                    merged_events.append(batch[0])
                    continue

                group_ids: List[int] = []
                curriculum_ids: List[int] = []
                source_event_ids: List[int] = []

                for item in batch:
                    group_ids.extend(
                        self._positive_int(x)
                        for x in list(getattr(item, "group_ids", []) or [])
                        if self._positive_int(x) > 0
                    )
                    curriculum_ids.extend(
                        self._positive_int(x)
                        for x in list(getattr(item, "curriculum_ids", []) or [])
                        if self._positive_int(x) > 0
                    )
                    source_event_ids.extend(
                        self._positive_int(x)
                        for x in list(getattr(item, "source_event_ids", []) or [])
                        if self._positive_int(x) > 0
                    )

                group_ids = list(dict.fromkeys(group_ids))
                curriculum_ids = list(dict.fromkeys(curriculum_ids))
                source_event_ids = list(dict.fromkeys(source_event_ids))

                anchor_event_id = min(source_event_ids) if source_event_ids else 0
                anchor_curriculum_id = curriculum_ids[0] if curriculum_ids else 0
                anchor_group_id = group_ids[0] if group_ids else 0

                merged_events.append(
                    SimpleNamespace(
                        id_event=anchor_event_id,
                        curriculum_id=anchor_curriculum_id,
                        curriculum_ids=curriculum_ids,
                        group_id=anchor_group_id,
                        group_ids=group_ids,
                        subject_id=self._positive_int(getattr(batch[0], "subject_id", 0)),
                        part_type="lecture",
                        required_room_type=str(
                            getattr(batch[0], "required_room_type", "") or ""
                        ).strip().lower(),
                        fixed_week_number=self._normalize_week_number(
                            getattr(batch[0], "fixed_week_number", None)
                        ),
                        fixed_week_type=self._normalize_week_type(
                            getattr(batch[0], "fixed_week_type", None)
                        ),
                        merged=True,
                        source_event_ids=source_event_ids,
                    )
                )

        result = merged_events + passthrough
        result.sort(
            key=lambda e: (
                self._positive_int(getattr(e, "id_event", 0)),
                str(getattr(e, "part_type", "")),
                self._positive_int(getattr(e, "subject_id", 0)),
                tuple(
                    self._positive_int(x)
                    for x in list(getattr(e, "group_ids", []) or [])
                    if self._positive_int(x) > 0
                ),
                self._normalize_week_type(getattr(e, "fixed_week_type", None)) or 0,
                self._normalize_week_number(getattr(e, "fixed_week_number", None)) or 0,
            )
        )
        return result

    # ---------------------------------------------------------
    # Final shape
    # ---------------------------------------------------------
    def _finalize_events(self, events: List[SimpleNamespace]) -> List[SimpleNamespace]:
        """
        Возвращаем компактный, но стабильный набор событий.

        Важно:
        - сохраняем id_event детерминированным;
        - не перенумеровываем после merge подряд 1..N,
          чтобы не ломать возможную привязку lock-ов к исходным событиям.
        """
        final_events: List[SimpleNamespace] = []

        seen_ids: set[int] = set()
        next_fallback_id = 1

        for event in events:
            event_id = self._positive_int(getattr(event, "id_event", 0))
            if event_id <= 0 or event_id in seen_ids:
                while next_fallback_id in seen_ids:
                    next_fallback_id += 1
                event_id = next_fallback_id
                next_fallback_id += 1

            seen_ids.add(event_id)

            final_events.append(
                SimpleNamespace(
                    id_event=event_id,
                    curriculum_id=self._positive_int(getattr(event, "curriculum_id", 0)),
                    curriculum_ids=list(
                        dict.fromkeys(
                            self._positive_int(x)
                            for x in list(getattr(event, "curriculum_ids", []) or [])
                            if self._positive_int(x) > 0
                        )
                    ),
                    group_id=self._positive_int(getattr(event, "group_id", 0)),
                    group_ids=list(
                        dict.fromkeys(
                            self._positive_int(x)
                            for x in list(getattr(event, "group_ids", []) or [])
                            if self._positive_int(x) > 0
                        )
                    ),
                    subject_id=self._positive_int(getattr(event, "subject_id", 0)),
                    part_type=str(getattr(event, "part_type", "") or "").strip(),
                    required_room_type=str(
                        getattr(event, "required_room_type", "") or ""
                    ).strip().lower(),
                    fixed_week_number=self._normalize_week_number(
                        getattr(event, "fixed_week_number", None)
                    ),
                    fixed_week_type=self._normalize_week_type(
                        getattr(event, "fixed_week_type", None)
                    ),
                    merged=bool(getattr(event, "merged", False)),
                    source_event_ids=list(
                        dict.fromkeys(
                            self._positive_int(x)
                            for x in list(getattr(event, "source_event_ids", []) or [])
                            if self._positive_int(x) > 0
                        )
                    ),
                )
            )

        return final_events

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    @staticmethod
    def _positive_int(value, default: int = 0) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError):
            return int(default)
        return result

    @staticmethod
    def _optional_int(value) -> Optional[int]:
        if value is None:
            return None
        try:
            result = int(value)
        except (TypeError, ValueError):
            return None
        return result if result > 0 else None

    @staticmethod
    def _normalize_week_number(value) -> Optional[int]:
        if value is None:
            return None
        try:
            n = int(value)
        except (TypeError, ValueError):
            return None
        return n if n > 0 else None

    @staticmethod
    def _normalize_week_type(value) -> Optional[int]:
        if value is None:
            return None
        try:
            n = int(value)
        except (TypeError, ValueError):
            return None
        return n if n in (1, 2) else None