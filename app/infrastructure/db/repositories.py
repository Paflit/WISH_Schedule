from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, is_dataclass
from types import SimpleNamespace
from typing import Dict, Iterable, List, Optional, Tuple

from app.application.dto.schedule_dto import (
    ScheduleEntryDTO,
    ScheduleVariantDTO,
)
from app.domain.models import (
    AcademicCalendar,
    CurriculumItem,
    Room,
    SemesterPlan,
    SemesterWeek,
    SolutionEntry,
    StudentGroup,
    Subject,
    Teacher,
    TimeSlot,
    WeeklyLoadPlan,
)


# ============================================================
# Helpers
# ============================================================


def _row_to_dict(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def _positive_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _optional_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v


def _bool_to_int(value: bool) -> int:
    return 1 if bool(value) else 0


def _serialize_obj(obj) -> str:
    if obj is None:
        return "null"
    if is_dataclass(obj):
        return json.dumps(asdict(obj), ensure_ascii=False)
    if hasattr(obj, "__dict__"):
        return json.dumps(obj.__dict__, ensure_ascii=False, default=str)
    return json.dumps(str(obj), ensure_ascii=False)


def _part_type_column(part_type: str) -> str:
    pt = (part_type or "").strip().lower()
    mapping = {
        "lecture": "can_lecture",
        "practice": "can_practice",
        "computer_practice": "can_computer_practice",
        "lab": "can_lab",
    }
    return mapping.get(pt, "can_practice")


# ============================================================
# Teachers Repository
# ============================================================


class SqliteTeachersRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def create(
        self,
        full_name: str,
        hard_max: int = 6,
        soft_max: int = 4,
        needs_method_day: bool = True,
        commentary: str | None = None,
    ) -> int:
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                INSERT INTO Teachers(
                    full_name,
                    commentary,
                    max_pairs_per_day_hard,
                    max_pairs_per_day_soft,
                    needs_method_day
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    full_name,
                    commentary,
                    int(hard_max),
                    int(soft_max),
                    _bool_to_int(needs_method_day),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update(
        self,
        id_teacher: int,
        full_name: str,
        hard_max: int,
        soft_max: int,
        needs_method_day: bool,
        commentary: str | None = None,
    ) -> None:
        with self._session_factory() as conn:
            conn.execute(
                """
                UPDATE Teachers
                SET full_name=?,
                    commentary=?,
                    max_pairs_per_day_hard=?,
                    max_pairs_per_day_soft=?,
                    needs_method_day=?
                WHERE id_teacher=?
                """,
                (
                    full_name,
                    commentary,
                    int(hard_max),
                    int(soft_max),
                    _bool_to_int(needs_method_day),
                    int(id_teacher),
                ),
            )
            conn.commit()

    def delete(self, id_teacher: int) -> None:
        with self._session_factory() as conn:
            conn.execute("DELETE FROM Teachers WHERE id_teacher=?", (int(id_teacher),))
            conn.commit()

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
                INSERT INTO Teachers(
                    id_teacher,
                    full_name,
                    commentary,
                    max_pairs_per_day_hard,
                    max_pairs_per_day_soft,
                    needs_method_day
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id_teacher) DO UPDATE SET
                    full_name=excluded.full_name,
                    commentary=excluded.commentary,
                    max_pairs_per_day_hard=excluded.max_pairs_per_day_hard,
                    max_pairs_per_day_soft=excluded.max_pairs_per_day_soft,
                    needs_method_day=excluded.needs_method_day
                """,
                (
                    int(id_teacher),
                    full_name,
                    commentary,
                    int(hard_max),
                    int(soft_max),
                    _bool_to_int(needs_method_day),
                ),
            )
            conn.commit()

    def list_all(self) -> List[Teacher]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                """
                SELECT *
                FROM Teachers
                ORDER BY full_name
                """
            ).fetchall()

        return [
            Teacher(
                id_teacher=int(r["id_teacher"]),
                full_name=str(r["full_name"]),
                hard_max_pairs_per_day=_positive_int(r.get("max_pairs_per_day_hard", 6), 6),
                soft_max_pairs_per_day=_positive_int(r.get("max_pairs_per_day_soft", 4), 4),
                needs_method_day=bool(r.get("needs_method_day", 1)),
            )
            for r in rows
        ]

    def get_by_id(self, id_teacher: int) -> Optional[Teacher]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            row = conn.execute(
                "SELECT * FROM Teachers WHERE id_teacher=?",
                (int(id_teacher),),
            ).fetchone()
        if not row:
            return None
        return Teacher(
            id_teacher=int(row["id_teacher"]),
            full_name=str(row["full_name"]),
            hard_max_pairs_per_day=_positive_int(row.get("max_pairs_per_day_hard", 6), 6),
            soft_max_pairs_per_day=_positive_int(row.get("max_pairs_per_day_soft", 4), 4),
            needs_method_day=bool(row.get("needs_method_day", 1)),
        )

    def get_by_full_name(self, full_name: str) -> Optional[Teacher]:
        normalized_name = str(full_name or "").strip()
        if not normalized_name:
            return None

        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            row = conn.execute(
                """
                SELECT *
                FROM Teachers
                WHERE LOWER(TRIM(full_name)) = LOWER(?)
                """,
                (normalized_name,),
            ).fetchone()

        if not row:
            return None

        return Teacher(
            id_teacher=int(row["id_teacher"]),
            full_name=str(row["full_name"]),
            hard_max_pairs_per_day=_positive_int(row.get("max_pairs_per_day_hard", 6), 6),
            soft_max_pairs_per_day=_positive_int(row.get("max_pairs_per_day_soft", 4), 4),
            needs_method_day=bool(row.get("needs_method_day", 1)),
        )

    def get_teacher_subject_ids(self, teacher_id: int) -> list[int]:
        with self._session_factory() as conn:
            rows = conn.execute(
                """
                SELECT subject_id
                FROM TeacherSubjects
                WHERE teacher_id=?
                ORDER BY subject_id
                """,
                (int(teacher_id),),
            ).fetchall()
        return [int(r[0]) for r in rows]

    def replace_teacher_subjects(self, teacher_id: int, subject_ids: list[int]) -> None:
        with self._session_factory() as conn:
            conn.execute(
                "DELETE FROM TeacherSubjects WHERE teacher_id=?",
                (int(teacher_id),),
            )
            for sid in subject_ids:
                conn.execute(
                    """
                    INSERT INTO TeacherSubjects(
                        teacher_id,
                        subject_id,
                        can_lecture,
                        can_practice,
                        can_computer_practice,
                        can_lab
                    )
                    VALUES (?, ?, 1, 1, 1, 1)
                    """,
                    (int(teacher_id), int(sid)),
                )
            conn.commit()

    def get_teacher_subject_rules(self, teacher_id: int) -> dict[int, dict]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                """
                SELECT subject_id, can_lecture, can_practice, can_computer_practice, can_lab
                FROM TeacherSubjects
                WHERE teacher_id=?
                ORDER BY subject_id
                """,
                (int(teacher_id),),
            ).fetchall()

        result: dict[int, dict] = {}
        for r in rows:
            result[int(r["subject_id"])] = {
                "can_lecture": bool(r["can_lecture"]),
                "can_practice": bool(r["can_practice"]),
                "can_computer_practice": bool(r["can_computer_practice"]),
                "can_lab": bool(r["can_lab"]),
            }
        return result

    def replace_teacher_subject_rules(self, teacher_id: int, subject_rules: list[dict]) -> None:
        with self._session_factory() as conn:
            conn.execute(
                "DELETE FROM TeacherSubjects WHERE teacher_id=?",
                (int(teacher_id),),
            )
            for item in subject_rules:
                conn.execute(
                    """
                    INSERT INTO TeacherSubjects(
                        teacher_id,
                        subject_id,
                        can_lecture,
                        can_practice,
                        can_computer_practice,
                        can_lab
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(teacher_id),
                        int(item["subject_id"]),
                        _bool_to_int(item.get("can_lecture", True)),
                        _bool_to_int(item.get("can_practice", True)),
                        _bool_to_int(item.get("can_computer_practice", True)),
                        _bool_to_int(item.get("can_lab", True)),
                    ),
                )
            conn.commit()

    def get_teacher_subject_matrix(self) -> Dict[Tuple[int, int], bool]:
        with self._session_factory() as conn:
            rows = conn.execute(
                """
                SELECT teacher_id, subject_id
                FROM TeacherSubjects
                """
            ).fetchall()
        return {(int(t), int(s)): True for t, s in rows}

    def get_teacher_part_matrix(self) -> Dict[Tuple[int, int, str], bool]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                """
                SELECT teacher_id, subject_id,
                       can_lecture, can_practice, can_computer_practice, can_lab
                FROM TeacherSubjects
                """
            ).fetchall()

        result: Dict[Tuple[int, int, str], bool] = {}
        for r in rows:
            tid = int(r["teacher_id"])
            sid = int(r["subject_id"])
            result[(tid, sid, "lecture")] = bool(r["can_lecture"])
            result[(tid, sid, "practice")] = bool(r["can_practice"])
            result[(tid, sid, "computer_practice")] = bool(r["can_computer_practice"])
            result[(tid, sid, "lab")] = bool(r["can_lab"])
        return result

    def get_teacher_group_assignments(self) -> Dict[int, set[int]]:
        with self._session_factory() as conn:
            rows = conn.execute(
                """
                SELECT teacher_id, group_id
                FROM TeacherGroupAssignments
                """
            ).fetchall()

        result: Dict[int, set[int]] = {}
        for teacher_id, group_id in rows:
            result.setdefault(int(teacher_id), set()).add(int(group_id))
        return result

    def get_teacher_group_ids(self, teacher_id: int) -> list[int]:
        with self._session_factory() as conn:
            rows = conn.execute(
                """
                SELECT group_id
                FROM TeacherGroupAssignments
                WHERE teacher_id=?
                ORDER BY group_id
                """,
                (int(teacher_id),),
            ).fetchall()
        return [int(r[0]) for r in rows]

    def replace_teacher_group_assignments(self, teacher_id: int, group_ids: list[int]) -> None:
        with self._session_factory() as conn:
            conn.execute(
                "DELETE FROM TeacherGroupAssignments WHERE teacher_id=?",
                (int(teacher_id),),
            )
            for group_id in sorted({int(x) for x in group_ids if int(x) > 0}):
                conn.execute(
                    """
                    INSERT INTO TeacherGroupAssignments(teacher_id, group_id)
                    VALUES (?, ?)
                    """,
                    (int(teacher_id), int(group_id)),
                )
            conn.commit()

    def get_availability_matrix(self, calendar_id: int) -> Dict[Tuple[int, int], bool]:
        with self._session_factory() as conn:
            rows = conn.execute(
                """
                SELECT teacher_id, slot_id, is_available
                FROM TeacherAvailability
                WHERE calendar_id=?
                """,
                (int(calendar_id),),
            ).fetchall()
        return {(int(t), int(s)): bool(a) for t, s, a in rows}

    def list_with_subjects_and_days(self, calendar_id: int | None = None):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict

            if calendar_id is None:
                row = conn.execute(
                    """
                    SELECT id_calendar
                    FROM AcademicCalendar
                    ORDER BY id_calendar DESC
                    LIMIT 1
                    """
                ).fetchone()
                calendar_id = int(row["id_calendar"]) if row else None

            subj_rows = conn.execute(
                """
                SELECT ts.teacher_id, s.subject_name
                FROM TeacherSubjects ts
                JOIN Subjects s ON s.id_subject = ts.subject_id
                ORDER BY ts.teacher_id, s.subject_name
                """
            ).fetchall()

            subj_map: Dict[int, List[str]] = {}
            for r in subj_rows:
                subj_map.setdefault(int(r["teacher_id"]), []).append(str(r["subject_name"]))

            day_map: Dict[int, set[int]] = {}
            if calendar_id is not None:
                rows = conn.execute(
                    """
                    SELECT ta.teacher_id, ts.day_of_week
                    FROM TeacherAvailability ta
                    JOIN TimeSlots ts ON ts.id_slot = ta.slot_id
                    JOIN SemesterWeeks sw ON sw.id_week = ts.week_id
                    WHERE ta.calendar_id=? AND ta.is_available=1
                    GROUP BY ta.teacher_id, ts.day_of_week
                    """,
                    (int(calendar_id),),
                ).fetchall()
                for r in rows:
                    day_map.setdefault(int(r["teacher_id"]), set()).add(int(r["day_of_week"]))

            teachers = conn.execute(
                """
                SELECT id_teacher, full_name
                FROM Teachers
                ORDER BY full_name
                """
            ).fetchall()

        def day_name(d: int) -> str:
            return {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб"}.get(d, str(d))

        result = []
        for r in teachers:
            tid = int(r["id_teacher"])
            result.append(
                SimpleNamespace(
                    id_teacher=tid,
                    full_name=str(r["full_name"]),
                    subjects=", ".join(subj_map.get(tid, [])) if subj_map.get(tid) else "—",
                    working_days=", ".join(day_name(x) for x in sorted(day_map.get(tid, set())))
                    if day_map.get(tid)
                    else "—",
                )
            )
        return result

    def get_teacher_unavailable_slots(self, teacher_id: int, calendar_id: int) -> set[tuple[int, int, int]]:
        with self._session_factory() as conn:
            rows = conn.execute(
                """
                SELECT sw.week_type, ts.day_of_week, ts.pair_number
                FROM TeacherAvailability ta
                JOIN TimeSlots ts ON ts.id_slot = ta.slot_id
                JOIN SemesterWeeks sw ON sw.id_week = ts.week_id
                WHERE ta.teacher_id=? AND ta.calendar_id=? AND ta.is_available=0
                GROUP BY sw.week_type, ts.day_of_week, ts.pair_number
                """,
                (int(teacher_id), int(calendar_id)),
            ).fetchall()

        return {(int(r[0]), int(r[1]), int(r[2])) for r in rows}

    def replace_teacher_availability_grid(
        self,
        teacher_id: int,
        calendar_id: int,
        unavailable_cells: set[tuple[int, ...]],
    ) -> None:
        normalized_unavailable = set()
        for cell in unavailable_cells:
            if len(cell) == 3:
                normalized_unavailable.add((int(cell[0]), int(cell[1]), int(cell[2])))
            elif len(cell) == 2:
                normalized_unavailable.add((0, int(cell[0]), int(cell[1])))

        with self._session_factory() as conn:
            conn.execute(
                """
                DELETE FROM TeacherAvailability
                WHERE teacher_id=? AND calendar_id=?
                """,
                (int(teacher_id), int(calendar_id)),
            )

            slots = conn.execute(
                """
                SELECT ts.id_slot, sw.week_type, ts.day_of_week, ts.pair_number
                FROM TimeSlots ts
                JOIN SemesterWeeks sw ON sw.id_week = ts.week_id
                WHERE sw.calendar_id=?
                GROUP BY ts.id_slot, sw.week_type, ts.day_of_week, ts.pair_number
                """,
                (int(calendar_id),),
            ).fetchall()

            for slot_id, week_type, day_of_week, pair_number in slots:
                cell = (int(week_type), int(day_of_week), int(pair_number))
                legacy_cell = (0, int(day_of_week), int(pair_number))
                is_available = 0 if cell in normalized_unavailable or legacy_cell in normalized_unavailable else 1
                conn.execute(
                    """
                    INSERT INTO TeacherAvailability(
                        calendar_id,
                        teacher_id,
                        slot_id,
                        is_available
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (int(calendar_id), int(teacher_id), int(slot_id), int(is_available)),
                )
            conn.commit()


# ============================================================
# Subjects Repository
# ============================================================


class SqliteSubjectsRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def create(self, subject_name: str) -> int:
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                INSERT INTO Subjects(subject_name)
                VALUES (?)
                """,
                (subject_name,),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update(self, id_subject: int, subject_name: str) -> None:
        with self._session_factory() as conn:
            conn.execute(
                """
                UPDATE Subjects
                SET subject_name=?
                WHERE id_subject=?
                """,
                (subject_name, int(id_subject)),
            )
            conn.commit()

    def delete(self, id_subject: int) -> None:
        with self._session_factory() as conn:
            conn.execute("DELETE FROM Subjects WHERE id_subject=?", (int(id_subject),))
            conn.commit()

    def list_all(self) -> List[Subject]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                """
                SELECT *
                FROM Subjects
                ORDER BY subject_name
                """
            ).fetchall()

        return [
            Subject(
                id_subject=int(r["id_subject"]),
                subject_name=str(r["subject_name"]),
            )
            for r in rows
        ]

    def get_by_id(self, id_subject: int) -> Optional[Subject]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            row = conn.execute(
                "SELECT * FROM Subjects WHERE id_subject=?",
                (int(id_subject),),
            ).fetchone()
        if not row:
            return None
        return Subject(
            id_subject=int(row["id_subject"]),
            subject_name=str(row["subject_name"]),
        )


# ============================================================
# Groups Repository
# ============================================================


class SqliteGroupsRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def create(
        self,
        group_name: str,
        year: int | None,
        quantity: int,
        education_form: str = "full-time",
    ) -> int:
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                INSERT INTO StudentGroups(group_name, year, quantity, education_form)
                VALUES (?, ?, ?, ?)
                """,
                (group_name, year, int(quantity), education_form),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update(
        self,
        id_group: int,
        group_name: str,
        year: int | None,
        quantity: int,
        education_form: str,
    ) -> None:
        with self._session_factory() as conn:
            conn.execute(
                """
                UPDATE StudentGroups
                SET group_name=?, year=?, quantity=?, education_form=?
                WHERE id_group=?
                """,
                (group_name, year, int(quantity), education_form, int(id_group)),
            )
            conn.commit()

    def delete(self, id_group: int) -> None:
        with self._session_factory() as conn:
            conn.execute("DELETE FROM StudentGroups WHERE id_group=?", (int(id_group),))
            conn.commit()

    def list_all(self) -> List[StudentGroup]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                """
                SELECT *
                FROM StudentGroups
                ORDER BY group_name
                """
            ).fetchall()

        return [
            StudentGroup(
                id_group=int(r["id_group"]),
                group_name=str(r["group_name"]),
                quantity=_positive_int(r["quantity"], 0),
                year=_optional_int(r.get("year")),
                education_form=str(r.get("education_form") or "full-time"),
            )
            for r in rows
        ]

    def get_by_id(self, id_group: int) -> Optional[StudentGroup]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            row = conn.execute(
                """
                SELECT *
                FROM StudentGroups
                WHERE id_group=?
                """,
                (int(id_group),),
            ).fetchone()
        if not row:
            return None
        return StudentGroup(
            id_group=int(row["id_group"]),
            group_name=str(row["group_name"]),
            quantity=_positive_int(row["quantity"], 0),
            year=_optional_int(row.get("year")),
            education_form=str(row.get("education_form") or "full-time"),
        )


# ============================================================
# Rooms Repository
# ============================================================

class SqliteRoomsRepository:
    ROOM_TYPE_PRIORITY = ["lab", "computer", "lecture", "classroom"]
    VALID_ROOM_TYPES = set(ROOM_TYPE_PRIORITY)

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def _normalize_room_types(
        self,
        room_type: str | None = None,
        room_types: list[str] | None = None,
    ) -> list[str]:
        raw = list(room_types or [])
        if not raw and room_type:
            raw = [room_type]

        normalized: list[str] = []
        seen = set()

        for value in raw:
            v = str(value or "").strip().lower()
            if not v:
                continue
            if v not in self.VALID_ROOM_TYPES:
                continue
            if v in seen:
                continue

            seen.add(v)
            normalized.append(v)

        normalized.sort(key=lambda x: self.ROOM_TYPE_PRIORITY.index(x))
        return normalized

    def _primary_room_type(
        self,
        room_type: str | None = None,
        room_types: list[str] | None = None,
    ) -> str:
        types = self._normalize_room_types(room_type=room_type, room_types=room_types)
        if not types:
            return "classroom"
        return types[0]

    def create(
        self,
        room_number: str,
        room_type: str,
        capacity: int,
        building: str | None = None,
        room_types: list[str] | None = None,
    ) -> int:
        normalized_types = self._normalize_room_types(
            room_type=room_type,
            room_types=room_types,
        )
        primary_type = self._primary_room_type(
            room_type=room_type,
            room_types=room_types,
        )

        with self._session_factory() as conn:
            cur = conn.execute(
                """
                INSERT INTO Classes(
                    room_number,
                    room_type,
                    room_types_json,
                    capacity,
                    building
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    room_number,
                    primary_type,
                    json.dumps(normalized_types, ensure_ascii=False),
                    int(capacity),
                    building,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update(
        self,
        id_room: int,
        room_number: str,
        room_type: str,
        capacity: int,
        building: str | None = None,
        room_types: list[str] | None = None,
    ) -> None:
        normalized_types = self._normalize_room_types(
            room_type=room_type,
            room_types=room_types,
        )
        primary_type = self._primary_room_type(
            room_type=room_type,
            room_types=room_types,
        )

        with self._session_factory() as conn:
            conn.execute(
                """
                UPDATE Classes
                SET room_number=?,
                    room_type=?,
                    room_types_json=?,
                    capacity=?,
                    building=?
                WHERE id_class=?
                """,
                (
                    room_number,
                    primary_type,
                    json.dumps(normalized_types, ensure_ascii=False),
                    int(capacity),
                    building,
                    int(id_room),
                ),
            )
            conn.commit()

    def delete(self, id_room: int) -> None:
        with self._session_factory() as conn:
            conn.execute("DELETE FROM Classes WHERE id_class=?", (int(id_room),))
            conn.commit()

    def get_room_subject_ids(self, room_id: int) -> list[int]:
        with self._session_factory() as conn:
            rows = conn.execute(
                """
                SELECT subject_id
                FROM RoomSubjectAssignments
                WHERE room_id=?
                ORDER BY subject_id
                """,
                (int(room_id),),
            ).fetchall()
        return [int(r[0]) for r in rows]

    def replace_room_subject_assignments(self, room_id: int, subject_ids: list[int]) -> None:
        with self._session_factory() as conn:
            conn.execute(
                "DELETE FROM RoomSubjectAssignments WHERE room_id=?",
                (int(room_id),),
            )
            for subject_id in sorted({int(x) for x in subject_ids if int(x) > 0}):
                conn.execute(
                    """
                    INSERT INTO RoomSubjectAssignments(room_id, subject_id)
                    VALUES (?, ?)
                    """,
                    (int(room_id), int(subject_id)),
                )
            conn.commit()

    def get_room_subject_assignments(self) -> Dict[int, set[int]]:
        with self._session_factory() as conn:
            rows = conn.execute(
                """
                SELECT room_id, subject_id
                FROM RoomSubjectAssignments
                """
            ).fetchall()
        result: Dict[int, set[int]] = {}
        for room_id, subject_id in rows:
            result.setdefault(int(room_id), set()).add(int(subject_id))
        return result

    def _parse_room_types(self, row: dict) -> list[str]:
        raw_json = row.get("room_types_json")

        if raw_json:
            try:
                data = json.loads(raw_json)
            except (TypeError, ValueError, json.JSONDecodeError):
                data = None

            if isinstance(data, list):
                return self._normalize_room_types(
                    room_types=[str(value) for value in data]
                )

        return self._normalize_room_types(
            room_type=str(row.get("room_type") or "").strip().lower()
        )

    def _room_from_row(self, row: dict) -> Room:
        parsed_types = tuple(self._parse_room_types(row))
        primary_type = self._primary_room_type(
            room_type=str(row.get("room_type") or "").strip().lower(),
            room_types=list(parsed_types),
        )

        return Room(
            id_room=int(row["id_class"]),
            room_number=str(row["room_number"]),
            room_type=primary_type,
            capacity=_positive_int(row["capacity"], 0),
            building=row.get("building"),
            room_types=parsed_types,
        )

    def list_all(self) -> List[Room]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                """
                SELECT *
                FROM Classes
                ORDER BY room_number
                """
            ).fetchall()

            return [self._room_from_row(r) for r in rows]

    def get_by_id(self, id_room: int) -> Optional[Room]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            row = conn.execute(
                "SELECT * FROM Classes WHERE id_class=?",
                (int(id_room),),
            ).fetchone()

            if not row:
                return None

            return self._room_from_row(row)

# ============================================================
# Calendar Repository
# ============================================================


class SqliteCalendarRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @staticmethod
    def _has_table(conn, name: str) -> bool:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name=?
            """,
            (name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _columns(conn, table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(r[1]) for r in rows}

    def has_calendars(self) -> bool:
        with self._session_factory() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM AcademicCalendar
                """
            ).fetchone()
        return bool(row and int(row[0]) > 0)

    def calendar_exists(self, academic_year: str, semester: int) -> bool:
        with self._session_factory() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM AcademicCalendar
                WHERE academic_year=? AND semester=?
                LIMIT 1
                """,
                (str(academic_year).strip(), int(semester)),
            ).fetchone()
        return row is not None

    def create_calendar(
        self,
        academic_year: str,
        semester: int,
        *,
        include_saturday: bool = False,
        pairs_per_day: int = 8,
        weeks_in_semester: int = 18,
        week_type_mode: int = 1,
        comment: str | None = None,
    ) -> int:
        academic_year = str(academic_year or "").strip()
        semester = int(semester)
        pairs_per_day = max(1, int(pairs_per_day))
        weeks_in_semester = max(1, int(weeks_in_semester))

        if not academic_year:
            raise ValueError("academic_year не может быть пустым.")
        if semester not in (1, 2):
            raise ValueError("semester должен быть равен 1 или 2.")

        with self._session_factory() as conn:
            duplicate = conn.execute(
                """
                SELECT id_calendar
                FROM AcademicCalendar
                WHERE academic_year=? AND semester=?
                LIMIT 1
                """,
                (academic_year, semester),
            ).fetchone()
            if duplicate:
                raise ValueError(
                    f"Семестр уже существует: {academic_year}, semester={semester}."
                )

            cur = conn.execute(
                """
                INSERT INTO AcademicCalendar(
                    academic_year,
                    semester,
                    week_type_mode,
                    comment
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    academic_year,
                    semester,
                    int(week_type_mode),
                    comment,
                ),
            )
            calendar_id = int(cur.lastrowid)

            days = [1, 2, 3, 4, 5] + ([6] if include_saturday else [])

            week_ids: List[int] = []
            for week_number in range(1, weeks_in_semester + 1):
                week_type = 1 if week_number % 2 == 1 else 2
                cur = conn.execute(
                    """
                    INSERT INTO SemesterWeeks(
                        calendar_id,
                        week_number_in_semester,
                        week_type,
                        is_study_week,
                        comment
                    )
                    VALUES (?, ?, ?, 1, ?)
                    """,
                    (
                        calendar_id,
                        int(week_number),
                        int(week_type),
                        f"week {week_number}",
                    ),
                )
                week_ids.append(int(cur.lastrowid))

            for week_id in week_ids:
                for day_of_week in days:
                    for pair_number in range(1, pairs_per_day + 1):
                        conn.execute(
                            """
                            INSERT INTO TimeSlots(
                                week_id,
                                day_of_week,
                                pair_number,
                                start_time,
                                end_time,
                                is_lunch_break
                            )
                            VALUES (?, ?, ?, NULL, NULL, 0)
                            """,
                            (int(week_id), int(day_of_week), int(pair_number)),
                        )

            conn.commit()
            return calendar_id

    def ensure_default_calendar(
        self,
        academic_year: str = "2025/2026",
        include_saturday: bool = False,
        pairs_per_day: int = 8,
        weeks_in_semester: int = 18,
    ) -> None:
        with self._session_factory() as conn:
            for t in ("AcademicCalendar", "SemesterWeeks", "TimeSlots"):
                if not self._has_table(conn, t):
                    raise RuntimeError(f"Нет таблицы {t}. Проверь schema.sql/миграции.")

            days = [1, 2, 3, 4, 5] + ([6] if include_saturday else [])

            for semester in (1, 2):
                row = conn.execute(
                    """
                    SELECT id_calendar
                    FROM AcademicCalendar
                    WHERE academic_year=? AND semester=?
                    LIMIT 1
                    """,
                    (academic_year, int(semester)),
                ).fetchone()

                if row:
                    calendar_id = int(row[0])
                else:
                    cur = conn.execute(
                        """
                        INSERT INTO AcademicCalendar(
                            academic_year,
                            semester,
                            week_type_mode,
                            comment
                        )
                        VALUES (?, ?, 1, ?)
                        """,
                        (academic_year, int(semester), "auto-created default calendar"),
                    )
                    calendar_id = int(cur.lastrowid)

                existing_weeks = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM SemesterWeeks
                    WHERE calendar_id=?
                    """,
                    (calendar_id,),
                ).fetchone()[0]

                if int(existing_weeks) == 0:
                    week_ids: List[int] = []
                    for week_number in range(1, int(weeks_in_semester) + 1):
                        week_type = 1 if week_number % 2 == 1 else 2
                        cur = conn.execute(
                            """
                            INSERT INTO SemesterWeeks(
                                calendar_id,
                                week_number_in_semester,
                                week_type,
                                is_study_week,
                                comment
                            )
                            VALUES (?, ?, ?, 1, ?)
                            """,
                            (
                                calendar_id,
                                int(week_number),
                                int(week_type),
                                f"week {week_number}",
                            ),
                        )
                        week_ids.append(int(cur.lastrowid))

                    for week_id in week_ids:
                        for day_of_week in days:
                            for pair_number in range(1, int(pairs_per_day) + 1):
                                conn.execute(
                                    """
                                    INSERT INTO TimeSlots(
                                        week_id,
                                        day_of_week,
                                        pair_number,
                                        start_time,
                                        end_time,
                                        is_lunch_break
                                    )
                                    VALUES (?, ?, ?, NULL, NULL, 0)
                                    """,
                                    (int(week_id), int(day_of_week), int(pair_number)),
                                )

            conn.commit()

    def list_calendars(self) -> List[AcademicCalendar]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                """
                SELECT *
                FROM AcademicCalendar
                ORDER BY academic_year, semester, id_calendar
                """
            ).fetchall()

        return [
            AcademicCalendar(
                id_calendar=int(r["id_calendar"]),
                academic_year=str(r["academic_year"]),
                semester=_positive_int(r["semester"], 0),
                start_date=r.get("start_date"),
                end_date=r.get("end_date"),
                week_type_mode=_positive_int(r.get("week_type_mode", 1), 1),
                comment=r.get("comment"),
            )
            for r in rows
        ]

    def get_calendar(self, calendar_id: int) -> Optional[AcademicCalendar]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            row = conn.execute(
                """
                SELECT *
                FROM AcademicCalendar
                WHERE id_calendar=?
                """,
                (int(calendar_id),),
            ).fetchone()
        if not row:
            return None
        return AcademicCalendar(
            id_calendar=int(row["id_calendar"]),
            academic_year=str(row["academic_year"]),
            semester=_positive_int(row["semester"], 0),
            start_date=row.get("start_date"),
            end_date=row.get("end_date"),
            week_type_mode=_positive_int(row.get("week_type_mode", 1), 1),
            comment=row.get("comment"),
        )

    def get_latest_calendar_id(self) -> Optional[int]:
        with self._session_factory() as conn:
            row = conn.execute(
                """
                SELECT id_calendar
                FROM AcademicCalendar
                ORDER BY id_calendar DESC
                LIMIT 1
                """
            ).fetchone()
        return int(row[0]) if row else None

    def list_semester_weeks(self, calendar_id: int) -> List[SemesterWeek]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                """
                SELECT *
                FROM SemesterWeeks
                WHERE calendar_id=?
                ORDER BY week_number_in_semester, id_week
                """,
                (int(calendar_id),),
            ).fetchall()

        return [
            SemesterWeek(
                id_week=int(r["id_week"]),
                calendar_id=int(r["calendar_id"]),
                week_type=_positive_int(r["week_type"], 1),
                week_number_in_semester=_positive_int(r.get("week_number_in_semester", 0), 0),
                is_study_week=bool(r.get("is_study_week", 1)),
                comment=r.get("comment"),
            )
            for r in rows
        ]

    def list_time_slots(self, calendar_id: int) -> List[TimeSlot]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                """
                SELECT
                    ts.id_slot,
                    ts.day_of_week,
                    ts.pair_number,
                    ts.is_lunch_break,
                    sw.week_type,
                    sw.week_number_in_semester
                FROM TimeSlots ts
                JOIN SemesterWeeks sw ON sw.id_week = ts.week_id
                WHERE sw.calendar_id=?
                ORDER BY sw.week_number_in_semester, sw.week_type, ts.day_of_week, ts.pair_number, ts.id_slot
                """,
                (int(calendar_id),),
            ).fetchall()

        return [
            TimeSlot(
                id_slot=int(r["id_slot"]),
                week_type=_positive_int(r["week_type"], 1),
                day_of_week=_positive_int(r["day_of_week"], 0),
                pair_number=_positive_int(r["pair_number"], 0),
                week_number_in_semester=_positive_int(r.get("week_number_in_semester", 0), 0),
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

    def _get_or_create_subject_id(self, conn, subject_name: str) -> int:
        subject_name = (subject_name or "").strip()
        row = conn.execute(
            """
            SELECT id_subject
            FROM Subjects
            WHERE subject_name=?
            """,
            (subject_name,),
        ).fetchone()
        if row:
            return int(row[0])
        cur = conn.execute(
            """
            INSERT INTO Subjects(subject_name)
            VALUES (?)
            """,
            (subject_name,),
        )
        return int(cur.lastrowid)

    def _required_room_type(self, part_type: str) -> str:
        pt = (part_type or "").strip().lower()
        if pt == "lecture":
            return "lecture"
        if pt == "lab":
            return "lab"
        if pt == "computer_practice":
            return "computer"
        return "classroom"

    def create_curriculum_item(
        self,
        group_id: int,
        subject_id: int,
        part_type: str,
        required_room_type: Optional[str] = None,
        hours_total_year: int = 0,
        comment: Optional[str] = None,
    ) -> int:
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                INSERT INTO CurriculumItems(
                    group_id,
                    subject_id,
                    part_type,
                    required_room_type,
                    hours_total_year,
                    comment
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(group_id),
                    int(subject_id),
                    part_type,
                    required_room_type or self._required_room_type(part_type),
                    int(hours_total_year),
                    comment,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def upsert_curriculum_item(
        self,
        curriculum_id: Optional[int],
        group_id: int,
        subject_id: int,
        part_type: str,
        required_room_type: Optional[str] = None,
        hours_total_year: int = 0,
        comment: Optional[str] = None,
    ) -> int:
        if curriculum_id is None:
            return self.create_curriculum_item(
                group_id=group_id,
                subject_id=subject_id,
                part_type=part_type,
                required_room_type=required_room_type,
                hours_total_year=hours_total_year,
                comment=comment,
            )

        with self._session_factory() as conn:
            conn.execute(
                """
                INSERT INTO CurriculumItems(
                    id_curriculum,
                    group_id,
                    subject_id,
                    part_type,
                    required_room_type,
                    hours_total_year,
                    comment
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id_curriculum) DO UPDATE SET
                    group_id=excluded.group_id,
                    subject_id=excluded.subject_id,
                    part_type=excluded.part_type,
                    required_room_type=excluded.required_room_type,
                    hours_total_year=excluded.hours_total_year,
                    comment=excluded.comment
                """,
                (
                    int(curriculum_id),
                    int(group_id),
                    int(subject_id),
                    part_type,
                    required_room_type or self._required_room_type(part_type),
                    int(hours_total_year),
                    comment,
                ),
            )
            conn.commit()
            return int(curriculum_id)

    def create_semester_plan(
        self,
        curriculum_id: int,
        calendar_id: int,
        hours_in_semester: int,
        credits: Optional[float] = None,
        spread_mode: str = "auto_even",
        comment: Optional[str] = None,
    ) -> int:
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                INSERT INTO CurriculumSemesterPlan(
                    curriculum_id,
                    calendar_id,
                    hours_in_semester,
                    credits,
                    spread_mode,
                    comment
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(curriculum_id),
                    int(calendar_id),
                    int(hours_in_semester),
                    credits,
                    spread_mode,
                    comment,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_curriculum_item(self, curriculum_id: int) -> Optional[CurriculumItem]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            row = conn.execute(
                """
                SELECT *
                FROM CurriculumItems
                WHERE id_curriculum=?
                """,
                (int(curriculum_id),),
            ).fetchone()
        if not row:
            return None
        return CurriculumItem(
            id_curriculum=int(row["id_curriculum"]),
            group_id=int(row["group_id"]),
            subject_id=int(row["subject_id"]),
            part_type=str(row["part_type"]),
            required_room_type=str(row["required_room_type"]),
        )

    def get_curriculum_items_for_plans(self, semester_plans: Iterable[object]) -> Dict[int, CurriculumItem]:
        plan_curriculum_ids = [
            _positive_int(getattr(p, "curriculum_id", 0), 0) for p in semester_plans
        ]
        plan_curriculum_ids = [x for x in plan_curriculum_ids if x > 0]
        if not plan_curriculum_ids:
            return {}

        placeholders = ",".join("?" for _ in plan_curriculum_ids)
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                f"""
                SELECT *
                FROM CurriculumItems
                WHERE id_curriculum IN ({placeholders})
                """,
                tuple(plan_curriculum_ids),
            ).fetchall()

        result: Dict[int, CurriculumItem] = {}
        for r in rows:
            result[int(r["id_curriculum"])] = CurriculumItem(
                id_curriculum=int(r["id_curriculum"]),
                group_id=int(r["group_id"]),
                subject_id=int(r["subject_id"]),
                part_type=str(r["part_type"]),
                required_room_type=str(r["required_room_type"]),
            )
        return result

    def get_semester_plans(self, calendar_id: int) -> List[SemesterPlan]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                """
                SELECT *
                FROM CurriculumSemesterPlan
                WHERE calendar_id=?
                ORDER BY id_plan
                """,
                (int(calendar_id),),
            ).fetchall()

        return [
            SemesterPlan(
                id_plan=int(r["id_plan"]),
                curriculum_id=int(r["curriculum_id"]),
                calendar_id=int(r["calendar_id"]),
                hours_in_semester=_positive_int(r["hours_in_semester"], 0),
                credits=r.get("credits"),
                spread_mode=str(r.get("spread_mode") or "auto_even"),
                comment=r.get("comment"),
            )
            for r in rows
        ]

    def get_weekly_plans(self, calendar_id: int) -> List[WeeklyLoadPlan]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                """
                SELECT
                    wlp.id_week_plan,
                    wlp.plan_id,
                    wlp.week_id,
                    wlp.hours_this_week,
                    wlp.comment,
                    sw.week_type,
                    sw.week_number_in_semester,
                    sw.is_study_week
                FROM WeeklyLoadPlan wlp
                JOIN SemesterWeeks sw ON sw.id_week = wlp.week_id
                JOIN CurriculumSemesterPlan csp ON csp.id_plan = wlp.plan_id
                WHERE csp.calendar_id=?
                ORDER BY wlp.plan_id, sw.week_number_in_semester, sw.id_week
                """,
                (int(calendar_id),),
            ).fetchall()

        return [
            WeeklyLoadPlan(
                id_week_plan=int(r["id_week_plan"]),
                plan_id=int(r["plan_id"]),
                week_id=int(r["week_id"]),
                hours_this_week=_positive_int(r["hours_this_week"], 0),
                week_type=_positive_int(r.get("week_type", 1), 1),
                week_number_in_semester=_positive_int(r.get("week_number_in_semester", 0), 0),
                comment=r.get("comment"),
            )
            for r in rows
        ]

    def rebuild_all_weekly_plans(self) -> None:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict

            plans = conn.execute(
                """
                SELECT id_plan, calendar_id, hours_in_semester, spread_mode
                FROM CurriculumSemesterPlan
                ORDER BY id_plan
                """
            ).fetchall()

            for plan in plans:
                plan_id = int(plan["id_plan"])
                calendar_id = int(plan["calendar_id"])
                hours_in_semester = _positive_int(plan["hours_in_semester"], 0)

                weeks = conn.execute(
                    """
                    SELECT id_week, week_number_in_semester, is_study_week
                    FROM SemesterWeeks
                    WHERE calendar_id=?
                    ORDER BY week_number_in_semester, id_week
                    """,
                    (calendar_id,),
                ).fetchall()

                study_weeks = [w for w in weeks if bool(w["is_study_week"])]
                conn.execute("DELETE FROM WeeklyLoadPlan WHERE plan_id=?", (plan_id,))

                if not study_weeks or hours_in_semester <= 0:
                    continue

                pairs_total = hours_in_semester // 2
                base_pairs = pairs_total // len(study_weeks)
                remainder = pairs_total % len(study_weeks)

                for idx, w in enumerate(study_weeks, start=1):
                    pairs_this_week = base_pairs + (1 if idx <= remainder else 0)
                    hours_this_week = pairs_this_week * 2
                    if hours_this_week <= 0:
                        continue

                    conn.execute(
                        """
                        INSERT INTO WeeklyLoadPlan(
                            plan_id,
                            week_id,
                            hours_this_week,
                            comment
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            plan_id,
                            int(w["id_week"]),
                            int(hours_this_week),
                            "auto rebuilt",
                        ),
                    )

            conn.commit()


# ============================================================
# Schedule Repository
# ============================================================


class SqliteScheduleRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._generation_events: Dict[int, object] = {}

    def set_generation_events(self, events: List[object]) -> None:
        self._generation_events = {
            _positive_int(getattr(e, "id_event", 0), 0): e
            for e in events
            if _positive_int(getattr(e, "id_event", 0), 0) > 0
        }

    def get_generation_event(self, event_id: int):
        return self._generation_events.get(int(event_id))

    def create_generation_draft(self, calendar_id: int, name: str, comment: str | None = None) -> int:
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                INSERT INTO GenerationDrafts(calendar_id, name, comment)
                VALUES (?, ?, ?)
                """,
                (int(calendar_id), str(name), comment),
            )
            conn.commit()
            return int(cur.lastrowid)

    def delete_generation_draft(self, draft_id: int) -> None:
        with self._session_factory() as conn:
            conn.execute("DELETE FROM GenerationDrafts WHERE id_draft=?", (int(draft_id),))
            conn.commit()

    def list_generation_drafts(self, calendar_id: Optional[int] = None):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            if calendar_id is None:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM GenerationDrafts
                    ORDER BY id_draft DESC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM GenerationDrafts
                    WHERE calendar_id=?
                    ORDER BY id_draft DESC
                    """,
                    (int(calendar_id),),
                ).fetchall()
        return [SimpleNamespace(**r) for r in rows]

    def list_generation_draft_entries(self, draft_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                """
                SELECT
                    gde.id_draft_entry,
                    gde.draft_id,
                    gde.event_id,
                    gde.slot_id,
                    gde.teacher_id,
                    gde.room_id,
                    gde.comment,
                    ts.day_of_week,
                    ts.pair_number,
                    sw.week_type,
                    sw.week_number_in_semester,
                    t.full_name AS teacher_name,
                    c.room_number
                FROM GenerationDraftEntries gde
                JOIN TimeSlots ts ON ts.id_slot = gde.slot_id
                JOIN SemesterWeeks sw ON sw.id_week = ts.week_id
                LEFT JOIN Teachers t ON t.id_teacher = gde.teacher_id
                LEFT JOIN Classes c ON c.id_class = gde.room_id
                WHERE gde.draft_id=?
                ORDER BY sw.week_type, ts.day_of_week, ts.pair_number, gde.id_draft_entry
                """,
                (int(draft_id),),
            ).fetchall()
        return [SimpleNamespace(**r) for r in rows]

    def upsert_generation_draft_entry(
        self,
        draft_id: int,
        event_id: int,
        slot_id: int,
        teacher_id: int | None = None,
        room_id: int | None = None,
        comment: str | None = None,
        draft_entry_id: int | None = None,
    ) -> int:
        with self._session_factory() as conn:
            if draft_entry_id is not None:
                conn.execute(
                    """
                    UPDATE GenerationDraftEntries
                    SET slot_id=?, teacher_id=?, room_id=?, comment=?
                    WHERE id_draft_entry=?
                    """,
                    (
                        int(slot_id),
                        int(teacher_id) if teacher_id is not None else None,
                        int(room_id) if room_id is not None else None,
                        comment,
                        int(draft_entry_id),
                    ),
                )
                conn.commit()
                return int(draft_entry_id)

            cur = conn.execute(
                """
                INSERT INTO GenerationDraftEntries(draft_id, event_id, slot_id, teacher_id, room_id, comment)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(draft_id),
                    int(event_id),
                    int(slot_id),
                    int(teacher_id) if teacher_id is not None else None,
                    int(room_id) if room_id is not None else None,
                    comment,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def delete_generation_draft_entry(self, draft_entry_id: int) -> None:
        with self._session_factory() as conn:
            conn.execute(
                "DELETE FROM GenerationDraftEntries WHERE id_draft_entry=?",
                (int(draft_entry_id),),
            )
            conn.commit()

    def create_variant(
        self,
        calendar_id: int,
        rule_profile_key: str,
        name: str,
        objective_score: int = 0,
        created_by: str | None = None,
        status: str = "generated",
        comment: str | None = None,
    ) -> int:
        final_comment = comment
        if created_by:
            final_comment = f"[created_by={created_by}] {comment or ''}".strip()

        with self._session_factory() as conn:
            cur = conn.execute(
                """
                INSERT INTO ScheduleVariants(
                    calendar_id,
                    rule_profile_key,
                    name,
                    objective_score,
                    status,
                    comment
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(calendar_id),
                    rule_profile_key,
                    name,
                    int(objective_score),
                    status,
                    final_comment,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_variant(self, variant_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            row = conn.execute(
                """
                SELECT *
                FROM ScheduleVariants
                WHERE id_variant=?
                """,
                (int(variant_id),),
            ).fetchone()
        if not row:
            return None
        return SimpleNamespace(**row)

    def update_variant(
        self,
        variant_id: int,
        name: Optional[str] = None,
        status: Optional[str] = None,
        comment: Optional[str] = None,
        objective_score: Optional[int] = None,
    ) -> None:
        fields = []
        params = []

        if name is not None:
            fields.append("name=?")
            params.append(name)
        if status is not None:
            fields.append("status=?")
            params.append(status)
        if comment is not None:
            fields.append("comment=?")
            params.append(comment)
        if objective_score is not None:
            fields.append("objective_score=?")
            params.append(int(objective_score))

        if not fields:
            return

        params.append(int(variant_id))
        with self._session_factory() as conn:
            conn.execute(
                f"""
                UPDATE ScheduleVariants
                SET {", ".join(fields)}
                WHERE id_variant=?
                """,
                tuple(params),
            )
            conn.commit()

    def list_variants(self, calendar_id: Optional[int] = None):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            if calendar_id is None:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM ScheduleVariants
                    ORDER BY id_variant DESC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM ScheduleVariants
                    WHERE calendar_id=?
                    ORDER BY id_variant DESC
                    """,
                    (int(calendar_id),),
                ).fetchall()
        return [SimpleNamespace(**r) for r in rows]

    def save_solution_entries(self, variant_id: int, solution_entries: List[SolutionEntry]) -> None:
        with self._session_factory() as conn:
            for entry in solution_entries:
                event = self.get_generation_event(int(entry.event_id))
                if event is None:
                    raise ValueError(
                        f"Не найдено generation event для event_id={entry.event_id}. "
                        f"Перед save_solution_entries нужно вызвать set_generation_events(...)."
                    )

                group_curriculum_pairs = [
                    (
                        _positive_int(group_id, 0),
                        _positive_int(curriculum_id, 0),
                    )
                    for group_id, curriculum_id in list(getattr(event, "group_curriculum_pairs", []) or [])
                    if _positive_int(group_id, 0) > 0 and _positive_int(curriculum_id, 0) > 0
                ]
                if not group_curriculum_pairs:
                    curriculum_id = _positive_int(getattr(event, "curriculum_id", 0), 0)
                    group_id = _positive_int(getattr(event, "group_id", 0), 0)
                    group_curriculum_pairs = [(group_id, curriculum_id)]

                for group_id, curriculum_id in group_curriculum_pairs:
                    conn.execute(
                        """
                        INSERT INTO ScheduleEntries(
                            variant_id,
                            event_id,
                            slot_id,
                            group_id,
                            teacher_id,
                            curriculum_id,
                            room_id,
                            is_locked,
                            comment
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                        """,
                        (
                            int(variant_id),
                            int(entry.event_id),
                            int(entry.slot_id),
                            int(group_id) if int(group_id) > 0 else None,
                            int(entry.teacher_id) if entry.teacher_id is not None else None,
                            int(curriculum_id),
                            int(entry.room_id) if entry.room_id is not None else None,
                            json.dumps({"event_id": int(entry.event_id)}, ensure_ascii=False),
                        ),
                    )
            conn.commit()

    def _entry_query(self) -> str:
        return """
            SELECT
                se.id_schedule,
                se.variant_id,
                se.event_id,
                se.slot_id,
                se.group_id,
                se.teacher_id,
                se.curriculum_id,
                se.room_id,
                se.is_locked,
                se.comment AS schedule_comment,

                ts.day_of_week,
                ts.pair_number,
                sw.week_type,
                sw.week_number_in_semester,

                sg.group_name,
                t.full_name AS teacher_name,
                c.room_number,

                ci.subject_id,
                ci.part_type,
                s.subject_name

            FROM ScheduleEntries se
            JOIN TimeSlots ts ON ts.id_slot = se.slot_id
            JOIN SemesterWeeks sw ON sw.id_week = ts.week_id
            LEFT JOIN StudentGroups sg ON sg.id_group = se.group_id
            LEFT JOIN Teachers t ON t.id_teacher = se.teacher_id
            LEFT JOIN Classes c ON c.id_class = se.room_id
            JOIN CurriculumItems ci ON ci.id_curriculum = se.curriculum_id
            JOIN Subjects s ON s.id_subject = ci.subject_id
        """

    def _extract_event_id_from_comment(self, comment_value: Optional[str]) -> int:
        if not comment_value:
            return 0
        try:
            payload = json.loads(comment_value)
            if isinstance(payload, dict):
                return _positive_int(payload.get("event_id", 0), 0)
        except Exception:
            pass
        return 0

    def to_dto(self, entry) -> ScheduleEntryDTO:
        if isinstance(entry, ScheduleEntryDTO):
            return entry

        if isinstance(entry, dict):
            r = entry
        else:
            r = entry.__dict__

        return ScheduleEntryDTO(
            id_schedule=_positive_int(r.get("id_schedule", 0), 0),
            variant_id=_positive_int(r.get("variant_id", 0), 0),
            curriculum_id=_positive_int(r.get("curriculum_id", 0), 0),
            event_id=_positive_int(
                r.get("event_id", 0)
                or self._extract_event_id_from_comment(r.get("schedule_comment")),
                0,
            ),
            slot_id=_positive_int(r.get("slot_id", 0), 0),
            week_number=_positive_int(r.get("week_number_in_semester", 0), 0),
            week_type=_positive_int(r.get("week_type", 0), 0),
            day_of_week=_positive_int(r.get("day_of_week", 0), 0),
            pair_number=_positive_int(r.get("pair_number", 0), 0),
            group_id=_positive_int(r.get("group_id", 0), 0),
            group_name=str(r.get("group_name") or ""),
            teacher_id=_positive_int(r.get("teacher_id", 0), 0),
            teacher_name=str(r.get("teacher_name") or ""),
            subject_id=_positive_int(r.get("subject_id", 0), 0),
            subject_name=str(r.get("subject_name") or ""),
            part_type=str(r.get("part_type") or ""),
            room_id=_positive_int(r.get("room_id", 0), 0),
            room_number=str(r.get("room_number") or ""),
            is_locked=bool(r.get("is_locked", 0)),
        )

    def list_entries(self, variant_id: int) -> List[ScheduleEntryDTO]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                self._entry_query()
                + """
                WHERE se.variant_id=?
                ORDER BY sw.week_number_in_semester, ts.day_of_week, ts.pair_number, se.id_schedule
                """,
                (int(variant_id),),
            ).fetchall()
        return [self.to_dto(r) for r in rows]

    def get_entry_by_id(self, variant_id: int, schedule_entry_id: int) -> Optional[ScheduleEntryDTO]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            row = conn.execute(
                self._entry_query()
                + """
                WHERE se.variant_id=? AND se.id_schedule=?
                LIMIT 1
                """,
                (int(variant_id), int(schedule_entry_id)),
            ).fetchone()
        return self.to_dto(row) if row else None

    def get_variant_dto(self, variant_id: int) -> ScheduleVariantDTO:
        variant = self.get_variant(variant_id)
        if variant is None:
            raise ValueError(f"Вариант id={variant_id} не найден.")

        entries = self.list_entries(int(variant_id))
        return ScheduleVariantDTO(
            id_variant=int(variant.id_variant),
            name=str(variant.name),
            objective_score=_positive_int(getattr(variant, "objective_score", 0), 0),
            entries=entries,
        )

    def exists_group_conflict(
        self,
        variant_id: int,
        group_id: int,
        slot_id: int,
        exclude_entry_id: Optional[int] = None,
        allow_same_event_id: Optional[int] = None,
    ) -> bool:
        with self._session_factory() as conn:
            if exclude_entry_id is None:
                if allow_same_event_id is None:
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM ScheduleEntries
                        WHERE variant_id=? AND group_id=? AND slot_id=?
                        LIMIT 1
                        """,
                        (int(variant_id), int(group_id), int(slot_id)),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM ScheduleEntries
                        WHERE variant_id=? AND group_id=? AND slot_id=?
                          AND COALESCE(event_id, 0)<>?
                        LIMIT 1
                        """,
                        (int(variant_id), int(group_id), int(slot_id), int(allow_same_event_id)),
                    ).fetchone()
            else:
                if allow_same_event_id is None:
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM ScheduleEntries
                        WHERE variant_id=? AND group_id=? AND slot_id=? AND id_schedule<>?
                        LIMIT 1
                        """,
                        (
                            int(variant_id),
                            int(group_id),
                            int(slot_id),
                            int(exclude_entry_id),
                        ),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM ScheduleEntries
                        WHERE variant_id=? AND group_id=? AND slot_id=? AND id_schedule<>?
                          AND COALESCE(event_id, 0)<>?
                        LIMIT 1
                        """,
                        (
                            int(variant_id),
                            int(group_id),
                            int(slot_id),
                            int(exclude_entry_id),
                            int(allow_same_event_id),
                        ),
                    ).fetchone()
        return row is not None

    def exists_teacher_conflict(
        self,
        variant_id: int,
        teacher_id: int,
        slot_id: int,
        exclude_entry_id: Optional[int] = None,
        allow_same_event_id: Optional[int] = None,
    ) -> bool:
        with self._session_factory() as conn:
            if exclude_entry_id is None:
                if allow_same_event_id is None:
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM ScheduleEntries
                        WHERE variant_id=? AND teacher_id=? AND slot_id=?
                        LIMIT 1
                        """,
                        (int(variant_id), int(teacher_id), int(slot_id)),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM ScheduleEntries
                        WHERE variant_id=? AND teacher_id=? AND slot_id=?
                          AND COALESCE(event_id, 0)<>?
                        LIMIT 1
                        """,
                        (int(variant_id), int(teacher_id), int(slot_id), int(allow_same_event_id)),
                    ).fetchone()
            else:
                if allow_same_event_id is None:
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM ScheduleEntries
                        WHERE variant_id=? AND teacher_id=? AND slot_id=? AND id_schedule<>?
                        LIMIT 1
                        """,
                        (
                            int(variant_id),
                            int(teacher_id),
                            int(slot_id),
                            int(exclude_entry_id),
                        ),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM ScheduleEntries
                        WHERE variant_id=? AND teacher_id=? AND slot_id=? AND id_schedule<>?
                          AND COALESCE(event_id, 0)<>?
                        LIMIT 1
                        """,
                        (
                            int(variant_id),
                            int(teacher_id),
                            int(slot_id),
                            int(exclude_entry_id),
                            int(allow_same_event_id),
                        ),
                    ).fetchone()
        return row is not None

    def exists_room_conflict(
        self,
        variant_id: int,
        room_id: int,
        slot_id: int,
        exclude_entry_id: Optional[int] = None,
        allow_same_event_id: Optional[int] = None,
    ) -> bool:
        with self._session_factory() as conn:
            if exclude_entry_id is None:
                if allow_same_event_id is None:
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM ScheduleEntries
                        WHERE variant_id=? AND room_id=? AND slot_id=?
                        LIMIT 1
                        """,
                        (int(variant_id), int(room_id), int(slot_id)),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM ScheduleEntries
                        WHERE variant_id=? AND room_id=? AND slot_id=?
                          AND COALESCE(event_id, 0)<>?
                        LIMIT 1
                        """,
                        (int(variant_id), int(room_id), int(slot_id), int(allow_same_event_id)),
                    ).fetchone()
            else:
                if allow_same_event_id is None:
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM ScheduleEntries
                        WHERE variant_id=? AND room_id=? AND slot_id=? AND id_schedule<>?
                        LIMIT 1
                        """,
                        (
                            int(variant_id),
                            int(room_id),
                            int(slot_id),
                            int(exclude_entry_id),
                        ),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM ScheduleEntries
                        WHERE variant_id=? AND room_id=? AND slot_id=? AND id_schedule<>?
                          AND COALESCE(event_id, 0)<>?
                        LIMIT 1
                        """,
                        (
                            int(variant_id),
                            int(room_id),
                            int(slot_id),
                            int(exclude_entry_id),
                            int(allow_same_event_id),
                        ),
                    ).fetchone()
        return row is not None

    def update_entry(self, entry: ScheduleEntryDTO) -> None:
        with self._session_factory() as conn:
            conn.execute(
                """
                UPDATE ScheduleEntries
                SET slot_id=?,
                    group_id=?,
                    teacher_id=?,
                    curriculum_id=?,
                    room_id=?,
                    is_locked=?,
                    comment=?,
                    event_id=?
                WHERE id_schedule=? AND variant_id=?
                """,
                (
                    int(entry.slot_id),
                    int(entry.group_id) if int(entry.group_id) > 0 else None,
                    int(entry.teacher_id) if int(entry.teacher_id) > 0 else None,
                    int(entry.curriculum_id),
                    int(entry.room_id) if int(entry.room_id) > 0 else None,
                    _bool_to_int(entry.is_locked),
                    json.dumps({"event_id": int(entry.event_id)}, ensure_ascii=False),
                    int(entry.event_id),
                    int(entry.id_schedule),
                    int(entry.variant_id),
                ),
            )
            conn.commit()

    def create_entry(self, entry: ScheduleEntryDTO) -> int:
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                INSERT INTO ScheduleEntries(
                    variant_id,
                    event_id,
                    slot_id,
                    group_id,
                    teacher_id,
                    curriculum_id,
                    room_id,
                    is_locked,
                    comment
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(entry.variant_id),
                    int(entry.event_id),
                    int(entry.slot_id),
                    int(entry.group_id) if int(entry.group_id) > 0 else None,
                    int(entry.teacher_id) if int(entry.teacher_id) > 0 else None,
                    int(entry.curriculum_id),
                    int(entry.room_id) if int(entry.room_id) > 0 else None,
                    _bool_to_int(entry.is_locked),
                    json.dumps({"event_id": int(entry.event_id)}, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def lock_entry(self, variant_id: int, schedule_entry_id: int, comment: str | None = None) -> None:
        with self._session_factory() as conn:
            conn.execute(
                """
                UPDATE ScheduleEntries
                SET is_locked=1
                WHERE id_schedule=? AND variant_id=?
                """,
                (int(schedule_entry_id), int(variant_id)),
            )

            existing = conn.execute(
                """
                SELECT 1
                FROM ScheduleLocks
                WHERE variant_id=? AND schedule_id=?
                """,
                (int(variant_id), int(schedule_entry_id)),
            ).fetchone()

            if not existing:
                event_row = conn.execute(
                    """
                    SELECT event_id
                    FROM ScheduleEntries
                    WHERE id_schedule=? AND variant_id=?
                    LIMIT 1
                    """,
                    (int(schedule_entry_id), int(variant_id)),
                ).fetchone()

                event_id = int(event_row[0]) if event_row and event_row[0] is not None else None

                conn.execute(
                    """
                    INSERT INTO ScheduleLocks(
                        variant_id,
                        schedule_id,
                        event_id,
                        lock_slot,
                        lock_teacher,
                        lock_class,
                        comment
                    )
                    VALUES (?, ?, ?, 1, 1, 1, ?)
                    """,
                    (
                        int(variant_id),
                        int(schedule_entry_id),
                        event_id,
                        comment,
                    ),
                )
            conn.commit()

    def log_edit(
        self,
        variant_id: int,
        edited_by: str,
        action: str,
        before,
        after,
        comment: Optional[str] = None,
    ) -> None:
        with self._session_factory() as conn:
            conn.execute(
                """
                INSERT INTO ScheduleEditsLog(
                    variant_id,
                    edited_by,
                    action,
                    before_json,
                    after_json,
                    comment
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(variant_id),
                    edited_by,
                    action,
                    _serialize_obj(before),
                    _serialize_obj(after),
                    comment,
                ),
            )
            conn.commit()

    def get_curriculum(self, curriculum_id: int) -> Optional[CurriculumItem]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            row = conn.execute(
                """
                SELECT *
                FROM CurriculumItems
                WHERE id_curriculum=?
                """,
                (int(curriculum_id),),
            ).fetchone()
        if not row:
            return None
        return CurriculumItem(
            id_curriculum=int(row["id_curriculum"]),
            group_id=int(row["group_id"]),
            subject_id=int(row["subject_id"]),
            part_type=str(row["part_type"]),
            required_room_type=str(row["required_room_type"]),
        )

    def get_group(self, group_id: int) -> Optional[StudentGroup]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            row = conn.execute(
                """
                SELECT *
                FROM StudentGroups
                WHERE id_group=?
                """,
                (int(group_id),),
            ).fetchone()
        if not row:
            return None
        return StudentGroup(
            id_group=int(row["id_group"]),
            group_name=str(row["group_name"]),
            quantity=_positive_int(row["quantity"], 0),
            year=_optional_int(row.get("year")),
            education_form=str(row.get("education_form") or "full-time"),
        )

    def list_locks_for_calendar(self, calendar_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            rows = conn.execute(
                """
                SELECT
                    sl.id_lock,
                    sl.variant_id,
                    sl.schedule_id,
                    sl.event_id,
                    sl.lock_slot,
                    sl.lock_teacher,
                    sl.lock_class,
                    sl.comment,
                    se.slot_id,
                    se.teacher_id,
                    se.room_id
                FROM ScheduleLocks sl
                JOIN ScheduleVariants sv ON sv.id_variant = sl.variant_id
                JOIN ScheduleEntries se ON se.id_schedule = sl.schedule_id
                WHERE sv.calendar_id=?
                ORDER BY sl.id_lock
                """,
                (int(calendar_id),),
            ).fetchall()

        result = []
        for r in rows:
            result.append(
                SimpleNamespace(
                    id_lock=int(r["id_lock"]),
                    variant_id=int(r["variant_id"]),
                    schedule_id=int(r["schedule_id"]),
                    event_id=_positive_int(r.get("event_id", 0), 0),
                    slot_id=int(r["slot_id"]) if bool(r["lock_slot"]) else None,
                    teacher_id=int(r["teacher_id"]) if bool(r["lock_teacher"]) else None,
                    room_id=int(r["room_id"]) if bool(r["lock_class"]) else None,
                    comment=r.get("comment"),
                )
            )
        return result
