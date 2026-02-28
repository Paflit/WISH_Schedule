# app/presentation/viewmodels/dictionaries_vm.py
"""
DictionariesViewModel

ViewModel для справочников:
- Teachers
- Groups
- Subjects
- Rooms

Задачи:
- загрузка данных из репозиториев
- отдача "плоских" списков для таблиц
- централизованная обработка ошибок

Page не должна напрямую обращаться к repo.
"""

from __future__ import annotations

from typing import List, Dict

from app.presentation.viewmodels.base_vm import BaseViewModel


class DictionariesViewModel(BaseViewModel):

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

    def load_rooms(self) -> List[Dict]:
        def _load():
            rooms = self.rooms_repo.list_all()
            return [
                {
                    "id": r.id_room,
                    "number": r.room_number,
                    "type": r.room_type,
                    "capacity": r.capacity,
                    "building": r.building,
                }
                for r in rooms
            ]

        return self.execute(_load) or []