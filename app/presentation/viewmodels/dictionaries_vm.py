from __future__ import annotations

from typing import List, Dict

from app.presentation.viewmodels.base_vm import BaseViewModel


class DictionariesViewModel(BaseViewModel):
    ROOM_TYPE_LABELS = {
        "lecture": "Лекционная",
        "classroom": "Обычная аудитория",
        "computer": "Компьютерный класс",
        "lab": "Лаборатория",
    }

    ROOM_TYPE_PRIORITY = ["lab", "computer", "lecture", "classroom"]

    def __init__(self, container):
        super().__init__(container)

        self.teachers_repo = container.teachers_repo
        self.groups_repo = container.groups_repo
        self.subjects_repo = container.subjects_repo
        self.rooms_repo = container.rooms_repo

    # ---------------------------------------------------------
    # Teachers
    # ---------------------------------------------------------

    def load_teachers(self) -> List[Dict]:
        def _load():
            teachers = self.teachers_repo.list_all()
            return [
                {
                    "id": t.id_teacher,
                    "name": t.full_name,
                    "hard_max": t.hard_max_pairs_per_day,
                    "soft_max": t.soft_max_pairs_per_day,
                    "method_day": t.needs_method_day,
                }
                for t in teachers
            ]

        return self.execute(_load) or []

    # ---------------------------------------------------------
    # Groups
    # ---------------------------------------------------------

    def load_groups(self) -> List[Dict]:
        def _load():
            groups = self.groups_repo.list_all()
            return [
                {
                    "id": g.id_group,
                    "name": g.group_name,
                    "year": getattr(g, "year", None),
                    "quantity": g.quantity,
                }
                for g in groups
            ]

        return self.execute(_load) or []

    # ---------------------------------------------------------
    # Subjects
    # ---------------------------------------------------------

    def load_subjects(self) -> List[Dict]:
        def _load():
            subjects = self.subjects_repo.list_all()
            return [
                {
                    "id": s.id_subject,
                    "name": s.subject_name,
                }
                for s in subjects
            ]

        return self.execute(_load) or []

    # ---------------------------------------------------------
    # Rooms
    # ---------------------------------------------------------

    def _normalize_room_types(self, room) -> list[str]:
        room_types = getattr(room, "room_types", None)

        if room_types:
            raw = [str(x).strip().lower() for x in room_types if str(x).strip()]
        else:
            single_type = str(getattr(room, "room_type", "") or "").strip().lower()
            raw = [single_type] if single_type else []

        seen = set()
        normalized: list[str] = []

        for value in raw:
            if value in seen:
                continue
            seen.add(value)
            normalized.append(value)

        normalized.sort(
            key=lambda x: self.ROOM_TYPE_PRIORITY.index(x)
            if x in self.ROOM_TYPE_PRIORITY
            else 999
        )
        return normalized

    def _room_type_label(self, value: str) -> str:
        return self.ROOM_TYPE_LABELS.get(value, value or "—")

    def _room_types_display(self, room_types: list[str]) -> str:
        if not room_types:
            return "—"
        return ", ".join(self._room_type_label(x) for x in room_types)

    def load_rooms(self) -> List[Dict]:
        def _load():
            rooms = self.rooms_repo.list_all()
            result = []

            for r in rooms:
                room_types = self._normalize_room_types(r)
                primary_type = (
                    str(getattr(r, "room_type", "") or "").strip().lower()
                    or (room_types[0] if room_types else "")
                )

                result.append(
                    {
                        "id": r.id_room,
                        "number": r.room_number,
                        "type": primary_type,
                        "room_types": room_types,
                        "room_types_display": self._room_types_display(room_types),
                        "capacity": r.capacity,
                        "building": r.building,
                    }
                )

            return result

        return self.execute(_load) or []