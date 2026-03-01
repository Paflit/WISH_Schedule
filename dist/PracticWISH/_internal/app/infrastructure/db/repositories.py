# app/infrastructure/db/repositories.py
"""
SQLite-реализация репозиториев.

MVP-реализация:
- используется sqlite3 (без ORM для простоты)
- session_factory — это callable, возвращающий sqlite3.Connection
- таблицы должны соответствовать ранее описанной схеме

ВАЖНО:
Это базовая рабочая версия.
Можно позже заменить на SQLAlchemy без изменения application слоя.
"""

from __future__ import annotations

import sqlite3
from typing import List, Dict, Tuple, Optional

from app.domain.models import (
    Teacher,
    StudentGroup,
    Subject,
    Room,
    TimeSlot,
    CurriculumItem,
    SolutionEntry,
)
from app.application.dto.schedule_dto import (
    ScheduleVariantDTO,
    ScheduleEntryDTO,
)
from types import SimpleNamespace

# ============================================================
# Helpers
# ============================================================

def _row_to_dict(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


# ============================================================
# Teachers Repository
# ============================================================

class SqliteTeachersRepository:

    def __init__(self, session_factory):
        self._session_factory = session_factory

        def upsert(
        self,
        id_teacher: int,
        full_name: str,
        hard_max: int = 6,
        soft_max: int = 4,
        needs_method_day: bool = True,
        commentary: str | None = None,
    ) -> None:
            with self._session_factory() as conn:
                conn.execute(
                    """
                    INSERT INTO Teachers(id_teacher, full_name, commentary, max_pairs_per_day_hard, max_pairs_per_day_soft, needs_method_day)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id_teacher) DO UPDATE SET
                        full_name=excluded.full_name,
                        commentary=excluded.commentary,
                        max_pairs_per_day_hard=excluded.max_pairs_per_day_hard,
                        max_pairs_per_day_soft=excluded.max_pairs_per_day_soft,
                        needs_method_day=excluded.needs_method_day
                    """,
                    (
                        id_teacher,
                        full_name,
                        commentary,
                        int(hard_max),
                        int(soft_max),
                        1 if needs_method_day else 0,
                    ),
                )
                conn.commit()

    def delete(self, id_teacher: int) -> None:
        with self._session_factory() as conn:
            conn.execute("DELETE FROM Teachers WHERE id_teacher = ?", (id_teacher,))
            conn.commit()

    def list_all(self) -> List[Teacher]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute("SELECT * FROM Teachers")
            rows = cur.fetchall()
            return [
                Teacher(
                    id_teacher=r["id_teacher"],
                    full_name=r["full_name"],
                    hard_max_pairs_per_day=r.get("max_pairs_per_day_hard", 6),
                    soft_max_pairs_per_day=r.get("max_pairs_per_day_soft", 4),
                    needs_method_day=bool(r.get("needs_method_day", 1)),
                )
                for r in rows
            ]

    def get_teacher_subject_matrix(self) -> Dict[Tuple[int, int], bool]:
        with self._session_factory() as conn:
            cur = conn.execute("SELECT teacher_id, subject_id FROM TeacherSubjects")
            return {(t, s): True for t, s in cur.fetchall()}

    def get_availability_matrix(self, calendar_id: int) -> Dict[Tuple[int, int], bool]:
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                SELECT teacher_id, slot_id, is_available
                FROM TeacherAvailability
                WHERE calendar_id = ?
                """,
                (calendar_id,),
            )
            return {(t, s): bool(a) for t, s, a in cur.fetchall()}


# ============================================================
# Groups Repository
# ============================================================

class SqliteGroupsRepository:

    def __init__(self, session_factory):
        self._session_factory = session_factory

        def upsert(
        self,
        id_group: int,
        group_name: str,
        year: int | None,
        quantity: int,
        education_form: str = "full-time",
    ) -> None:
            with self._session_factory() as conn:
                conn.execute(
                    """
                    INSERT INTO StudentGroups(id_group, group_name, year, quantity, education_form)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id_group) DO UPDATE SET
                        group_name=excluded.group_name,
                        year=excluded.year,
                        quantity=excluded.quantity,
                        education_form=excluded.education_form
                    """,
                    (int(id_group), group_name, year, int(quantity), education_form),
                )
                conn.commit()

    def delete(self, id_group: int) -> None:
        with self._session_factory() as conn:
            conn.execute("DELETE FROM StudentGroups WHERE id_group = ?", (int(id_group),))
            conn.commit()

    def list_all(self) -> List[StudentGroup]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute("SELECT * FROM StudentGroups")
            rows = cur.fetchall()
            return [
                StudentGroup(
                    id_group=r["id_group"],
                    group_name=r["group_name"],
                    quantity=r["quantity"],
                    education_form=r.get("education_form", "full-time"),
                )
                for r in rows
            ]


# ============================================================
# Subjects Repository
# ============================================================

class SqliteSubjectsRepository:

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def list_all(self) -> List[Subject]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute("SELECT * FROM Subjects")
            rows = cur.fetchall()
            return [
                Subject(
                    id_subject=r["id_subject"],
                    subject_name=r["subject_name"],
                )
                for r in rows
            ]
    
    def upsert(self, id_subject: int, subject_name: str) -> None:
        with self._session_factory() as conn:
            conn.execute(
                """
                INSERT INTO Subjects(id_subject, subject_name)
                VALUES (?, ?)
                ON CONFLICT(id_subject) DO UPDATE SET subject_name=excluded.subject_name
                """,
                (id_subject, subject_name),
            )
            conn.commit()

    def delete(self, id_subject: int) -> None:
        with self._session_factory() as conn:
            conn.execute("DELETE FROM Subjects WHERE id_subject = ?", (id_subject,))
            conn.commit()


# ============================================================
# Rooms Repository
# ============================================================

class SqliteRoomsRepository:

    def __init__(self, session_factory):
        self._session_factory = session_factory

        def upsert(
        self,
        id_room: int,
        room_number: str,
        room_type: str,
        capacity: int,
        building: str | None = None,
    ) -> None:
            with self._session_factory() as conn:
                conn.execute(
                    """
                    INSERT INTO Classes(id_class, room_number, room_type, capacity, building)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id_class) DO UPDATE SET
                        room_number=excluded.room_number,
                        room_type=excluded.room_type,
                        capacity=excluded.capacity,
                        building=excluded.building
                    """,
                    (int(id_room), room_number, room_type, int(capacity), building),
                )
                conn.commit()

    def delete(self, id_room: int) -> None:
        with self._session_factory() as conn:
            conn.execute("DELETE FROM Classes WHERE id_class = ?", (int(id_room),))
            conn.commit()

    def list_all(self) -> List[Room]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute("SELECT * FROM Classes")
            rows = cur.fetchall()
            return [
                Room(
                    id_room=r["id_class"],
                    room_number=r["room_number"],
                    room_type=r["room_type"],
                    capacity=r["capacity"],
                    building=r.get("building"),
                )
                for r in rows
            ]

    def get_by_id(self, room_id: int) -> Optional[Room]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute("SELECT * FROM Classes WHERE id_class = ?", (room_id,))
            r = cur.fetchone()
            if not r:
                return None
            return Room(
                id_room=r["id_class"],
                room_number=r["room_number"],
                room_type=r["room_type"],
                capacity=r["capacity"],
                building=r.get("building"),
            )


# ============================================================
# Calendar Repository
# ============================================================

class SqliteCalendarRepository:

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def list_all(self):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute("SELECT * FROM AcademicCalendar ORDER BY id_calendar DESC")
            rows = cur.fetchall()
            return [SimpleNamespace(**r) for r in rows]

    def get_calendar(self, calendar_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute("SELECT * FROM AcademicCalendar WHERE id_calendar = ?", (calendar_id,))
            return cur.fetchone()

    def list_time_slots(self, calendar_id: int) -> List[TimeSlot]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT ts.*
                FROM TimeSlots ts
                JOIN SemesterWeeks sw ON ts.week_id = sw.id_week
                WHERE sw.calendar_id = ?
                """,
                (calendar_id,),
            )
            rows = cur.fetchall()
            return [
                TimeSlot(
                    id_slot=r["id_slot"],
                    week_number_in_semester=r["week_number_in_semester"],
                    week_type=r["week_type"],
                    day_of_week=r["day_of_week"],
                    pair_number=r["pair_number"],
                    is_lunch_break=bool(r.get("is_lunch_break", 0)),
                )
                for r in rows
            ]


# ============================================================
# Curriculum Repository
# ============================================================

class SqliteCurriculumRepository:

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def list_curriculum_items(self, calendar_id: int) -> List[CurriculumItem]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT ci.*
                FROM CurriculumItems ci
                JOIN CurriculumSemesterPlan csp ON csp.curriculum_id = ci.id_curriculum
                WHERE csp.calendar_id = ?
                """,
                (calendar_id,),
            )
            rows = cur.fetchall()
            return [
                CurriculumItem(
                    id_curriculum=r["id_curriculum"],
                    group_id=r["group_id"],
                    subject_id=r["subject_id"],
                    part_type=r["part_type"],
                    required_room_type=r["required_room_type"],
                )
                for r in rows
            ]


# ============================================================
# Schedule Repository
# ============================================================

class SqliteScheduleRepository:

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def list_variants(self, calendar_id: int | None = None):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            if calendar_id is None:
                cur = conn.execute(
                    "SELECT * FROM ScheduleVariants ORDER BY created_at DESC, id_variant DESC"
                )
            else:
                cur = conn.execute(
                    """
                    SELECT * FROM ScheduleVariants
                    WHERE calendar_id = ?
                    ORDER BY created_at DESC, id_variant DESC
                    """,
                    (calendar_id,),
                )
            return cur.fetchall()

    def create_variant(self, calendar_id: int, rule_profile_key: str,
                       name: str, objective_score: int, created_by: str) -> int:
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                INSERT INTO ScheduleVariants(calendar_id, rule_profile_key, name, objective_score, status)
                VALUES (?, ?, ?, ?, 'generated')
                """,
                (calendar_id, rule_profile_key, name, objective_score),
            )
            conn.commit()
            return cur.lastrowid

    def save_solution_entries(self, variant_id: int,
                              solution_entries: List[SolutionEntry]) -> None:
        with self._session_factory() as conn:
            for e in solution_entries:
                conn.execute(
                    """
                    INSERT INTO ScheduleEntries
                    (variant_id, slot_id, teacher_id, room_id, curriculum_id, group_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (variant_id, e.slot_id, e.teacher_id, e.room_id,
                     e.event_id, None),  # group_id можно подтянуть через join при необходимости
                )
            conn.commit()

    def get_variant_dto(self, variant_id: int) -> ScheduleVariantDTO:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                "SELECT * FROM ScheduleVariants WHERE id_variant = ?",
                (variant_id,),
            )
            variant = cur.fetchone()

            cur = conn.execute(
                """
                SELECT se.*, sg.group_name, t.full_name,
                       s.subject_name, c.room_number
                FROM ScheduleEntries se
                LEFT JOIN StudentGroups sg ON se.group_id = sg.id_group
                LEFT JOIN Teachers t ON se.teacher_id = t.id_teacher
                LEFT JOIN Subjects s ON se.curriculum_id = s.id_subject
                LEFT JOIN Classes c ON se.room_id = c.id_class
                WHERE se.variant_id = ?
                """,
                (variant_id,),
            )
            entries = []
            for r in cur.fetchall():
                entries.append(
                    ScheduleEntryDTO(
                        event_id=r["curriculum_id"],
                        week_number=0,
                        week_type=0,
                        day_of_week=0,
                        pair_number=0,
                        group_id=r["group_id"],
                        group_name=r.get("group_name", ""),
                        teacher_id=r["teacher_id"],
                        teacher_name=r.get("full_name", ""),
                        subject_id=r["curriculum_id"],
                        subject_name=r.get("subject_name", ""),
                        part_type="",
                        room_id=r["room_id"],
                        room_number=r.get("room_number", ""),
                        is_locked=False,
                    )
                )

            return ScheduleVariantDTO(
                id_variant=variant["id_variant"],
                name=variant["name"],
                objective_score=variant["objective_score"],
                entries=entries,
            )

    def list_locks_for_calendar(self, calendar_id: int):
        return []