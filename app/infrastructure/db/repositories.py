from __future__ import annotations
import json
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

def _row_to_dict(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


# ============================================================
# Teachers Repository
# ============================================================

class SqliteTeachersRepository:

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def create(self, full_name: str, hard_max: int = 6, soft_max: int = 4,
           needs_method_day: bool = True, commentary: str | None = None) -> int:
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                INSERT INTO Teachers(full_name, commentary, max_pairs_per_day_hard, max_pairs_per_day_soft, needs_method_day)
                VALUES (?, ?, ?, ?, ?)
                """,
                (full_name, commentary, int(hard_max), int(soft_max), 1 if needs_method_day else 0),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update(self, id_teacher: int, full_name: str, hard_max: int, soft_max: int,
            needs_method_day: bool, commentary: str | None = None) -> None:
        with self._session_factory() as conn:
            conn.execute(
                """
                UPDATE Teachers
                SET full_name=?, commentary=?, max_pairs_per_day_hard=?, max_pairs_per_day_soft=?, needs_method_day=?
                WHERE id_teacher=?
                """,
                (full_name, commentary, int(hard_max), int(soft_max), 1 if needs_method_day else 0, int(id_teacher)),
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
        
    def list_with_subjects_and_days(self, calendar_id: int | None = None):
        """
        Возвращает список:
        id_teacher, full_name, subjects (строка), working_days (строка)

        working_days строим из TeacherAvailability (is_available=1) + TimeSlots.day_of_week.
        Если calendar_id не передан — берём последний календарь.
        """
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict

            # если календарь не задан — берём последний
            if calendar_id is None:
                cur = conn.execute("SELECT id_calendar FROM AcademicCalendar ORDER BY id_calendar DESC LIMIT 1")
                row = cur.fetchone()
                calendar_id = row["id_calendar"] if row else None

            # дисциплины преподавателя
            subj_map = {}
            cur = conn.execute("""
                SELECT ts.teacher_id, s.subject_name
                FROM TeacherSubjects ts
                JOIN Subjects s ON s.id_subject = ts.subject_id
                ORDER BY ts.teacher_id, s.subject_name
            """)
            for r in cur.fetchall():
                subj_map.setdefault(r["teacher_id"], []).append(r["subject_name"])

            # рабочие дни по доступности
            # day_of_week: 1..6 (Пн..Сб)
            day_map = {}
            if calendar_id is not None:
                cur = conn.execute("""
                    SELECT ta.teacher_id, t.day_of_week
                    FROM TeacherAvailability ta
                    JOIN TimeSlots t ON t.id_slot = ta.slot_id
                    WHERE ta.calendar_id = ? AND ta.is_available = 1
                """, (calendar_id,))
                for r in cur.fetchall():
                    day_map.setdefault(r["teacher_id"], set()).add(int(r["day_of_week"]))

            def day_name(d: int) -> str:
                return {1:"Пн",2:"Вт",3:"Ср",4:"Чт",5:"Пт",6:"Сб"}.get(d, str(d))

            cur = conn.execute("SELECT id_teacher, full_name FROM Teachers ORDER BY full_name")
            teachers = []
            for r in cur.fetchall():
                tid = r["id_teacher"]
                subjects = subj_map.get(tid, [])
                days = sorted(list(day_map.get(tid, set())))
                teachers.append(SimpleNamespace(
                    id_teacher=tid,
                    full_name=r["full_name"],
                    subjects=", ".join(subjects) if subjects else "—",
                    working_days=", ".join(day_name(d) for d in days) if days else "—",
                ))
            return teachers
        
    def get_teacher_subject_ids(self, teacher_id: int) -> list[int]:
        with self._session_factory() as conn:
            cur = conn.execute(
                "SELECT subject_id FROM TeacherSubjects WHERE teacher_id=? ORDER BY subject_id",
                (int(teacher_id),),
            )
            return [int(r[0]) for r in cur.fetchall()]

    def replace_teacher_subjects(self, teacher_id: int, subject_ids: list[int]) -> None:
        with self._session_factory() as conn:
            conn.execute("DELETE FROM TeacherSubjects WHERE teacher_id=?", (int(teacher_id),))
            for sid in subject_ids:
                conn.execute(
                    "INSERT INTO TeacherSubjects(teacher_id, subject_id) VALUES (?, ?)",
                    (int(teacher_id), int(sid)),
                )
            conn.commit()

    def get_teacher_unavailable_slots(self, teacher_id: int, calendar_id: int) -> set[tuple[int, int]]:
        """
        Возвращает множество (day_of_week, pair_number), где преподаватель НЕДОСТУПЕН.
        """
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                SELECT ts.day_of_week, ts.pair_number
                FROM TeacherAvailability ta
                JOIN TimeSlots ts ON ts.id_slot = ta.slot_id
                JOIN SemesterWeeks sw ON sw.id_week = ts.week_id
                WHERE ta.teacher_id = ?
                AND ta.calendar_id = ?
                AND ta.is_available = 0
                GROUP BY ts.day_of_week, ts.pair_number
                """,
                (int(teacher_id), int(calendar_id)),
            )
            return {(int(r[0]), int(r[1])) for r in cur.fetchall()}

    def replace_teacher_availability_grid(
        self,
        teacher_id: int,
        calendar_id: int,
        unavailable_cells: set[tuple[int, int]],
    ) -> None:
        """
        unavailable_cells = {(day_of_week, pair_number), ...}
        Для всех слотов календаря выставляет is_available:
        0 -> если слот в unavailable_cells
        1 -> иначе
        """
        with self._session_factory() as conn:
            # удалим старые записи по преподавателю и календарю
            conn.execute(
                "DELETE FROM TeacherAvailability WHERE teacher_id=? AND calendar_id=?",
                (int(teacher_id), int(calendar_id)),
            )

            cur = conn.execute(
                """
                SELECT ts.id_slot, ts.day_of_week, ts.pair_number
                FROM TimeSlots ts
                JOIN SemesterWeeks sw ON sw.id_week = ts.week_id
                WHERE sw.calendar_id = ?
                GROUP BY ts.id_slot, ts.day_of_week, ts.pair_number
                """,
                (int(calendar_id),),
            )
            slots = cur.fetchall()

            for slot_id, day_of_week, pair_number in slots:
                is_available = 0 if (int(day_of_week), int(pair_number)) in unavailable_cells else 1
                conn.execute(
                    """
                    INSERT INTO TeacherAvailability(teacher_id, calendar_id, slot_id, is_available)
                    VALUES (?, ?, ?, ?)
                    """,
                    (int(teacher_id), int(calendar_id), int(slot_id), int(is_available)),
                )

            conn.commit()
    def get_teacher_subject_rules(self, teacher_id: int) -> dict[int, dict]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT subject_id, can_lecture, can_practice, can_computer_practice, can_lab
                FROM TeacherSubjects
                WHERE teacher_id = ?
                """,
                (int(teacher_id),),
            )
            rows = cur.fetchall()
            result = {}
            for r in rows:
                result[int(r["subject_id"])] = {
                    "can_lecture": bool(r["can_lecture"]),
                    "can_practice": bool(r["can_practice"]),
                    "can_computer_practice": bool(r["can_computer_practice"]),
                    "can_lab": bool(r["can_lab"]),
                }
            return result

    def replace_teacher_subject_rules(self, teacher_id: int, subject_rules: list[dict]) -> None:
        """
        subject_rules = [
            {
                "subject_id": 1,
                "can_lecture": True,
                "can_practice": True,
                "can_computer_practice": True,
                "can_lab": True,
            },
            ...
        ]
        """
        with self._session_factory() as conn:
            conn.execute("DELETE FROM TeacherSubjects WHERE teacher_id=?", (int(teacher_id),))
            for item in subject_rules:
                conn.execute(
                    """
                    INSERT INTO TeacherSubjects(
                        teacher_id, subject_id,
                        can_lecture, can_practice, can_computer_practice, can_lab
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(teacher_id),
                        int(item["subject_id"]),
                        1 if item.get("can_lecture", True) else 0,
                        1 if item.get("can_practice", True) else 0,
                        1 if item.get("can_computer_practice", True) else 0,
                        1 if item.get("can_lab", True) else 0,
                    ),
                )
            conn.commit()

    def get_teacher_part_matrix(self) -> Dict[Tuple[int, int, str], bool]:
        """
        Возвращает матрицу допуска:
        (teacher_id, subject_id, part_type) -> True/False
        """
        result: Dict[Tuple[int, int, str], bool] = {}
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT teacher_id, subject_id, can_lecture, can_practice, can_computer_practice, can_lab
                FROM TeacherSubjects
                """
            )
            rows = cur.fetchall()

            for r in rows:
                tid = int(r["teacher_id"])
                sid = int(r["subject_id"])
                result[(tid, sid, "lecture")] = bool(r["can_lecture"])
                result[(tid, sid, "practice")] = bool(r["can_practice"])
                result[(tid, sid, "computer_practice")] = bool(r["can_computer_practice"])
                result[(tid, sid, "lab")] = bool(r["can_lab"])

        return result


# ============================================================
# Groups Repository
# ============================================================

class SqliteGroupsRepository:

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def create(self, group_name: str, year: int | None, quantity: int, education_form: str = "full-time") -> int:
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

    def update(self, id_group: int, group_name: str, year: int | None, quantity: int, education_form: str) -> None:
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

    def list_all(self) -> List[StudentGroup]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute("SELECT * FROM StudentGroups")
            rows = cur.fetchall()
            return [
                StudentGroup(
                    id_group=r["id_group"],
                    group_name=r["group_name"],
                    year=r.get("year"),
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

    def create(self, subject_name: str) -> int:
        with self._session_factory() as conn:
            cur = conn.execute(
                "INSERT INTO Subjects(subject_name) VALUES (?)",
                (subject_name,),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update(self, id_subject: int, subject_name: str) -> None:
        with self._session_factory() as conn:
            conn.execute(
                "UPDATE Subjects SET subject_name=? WHERE id_subject=?",
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


# ============================================================
# Rooms Repository
# ============================================================

class SqliteRoomsRepository:

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def create(self, room_number: str, room_type: str, capacity: int, building: str | None = None) -> int:
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                INSERT INTO Classes(room_number, room_type, capacity, building)
                VALUES (?, ?, ?, ?)
                """,
                (room_number, room_type, int(capacity), building),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update(self, id_room: int, room_number: str, room_type: str, capacity: int, building: str | None = None) -> None:
        with self._session_factory() as conn:
            conn.execute(
                """
                UPDATE Classes
                SET room_number=?, room_type=?, capacity=?, building=?
                WHERE id_class=?
                """,
                (room_number, room_type, int(capacity), building, int(id_room)),
            )
            conn.commit()

    def delete(self, id_room: int) -> None:
        with self._session_factory() as conn:
            conn.execute("DELETE FROM Classes WHERE id_class=?", (int(id_room),))
            conn.commit()

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

    @staticmethod
    def _has_table(conn, name: str) -> bool:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        )
        return cur.fetchone() is not None

    @staticmethod
    def _columns(conn, table: str) -> set[str]:
        cur = conn.execute(f"PRAGMA table_info({table})")
        return {r[1] for r in cur.fetchall()}

    def ensure_default_calendar(
        self,
        academic_year: str = "2025/2026",
        include_saturday: bool = False,
        pairs_per_day: int = 8,
        weeks_in_semester: int = 18,
    ) -> None:
        """
        Создаёт 2 календаря (1 и 2 семестр) и НОРМАЛЬНЫЙ набор недель:
        week_number_in_semester = 1..weeks_in_semester
        week_type чередуется: 1,2,1,2,...

        Это важное исправление weekly-model:
        раньше создавались только две записи week_type=1/2,
        из-за чего week_number_in_semester был фактически мёртвым.
        """
        with self._session_factory() as conn:
            for t in ("AcademicCalendar", "SemesterWeeks", "TimeSlots"):
                if not self._has_table(conn, t):
                    raise RuntimeError(f"Нет таблицы {t}. Проверь schema.sql/миграции.")

            cal_cols = self._columns(conn, "AcademicCalendar")
            weeks_cols = self._columns(conn, "SemesterWeeks")
            slots_cols = self._columns(conn, "TimeSlots")

            cal1 = self._get_or_create_calendar(conn, cal_cols, academic_year, 1)
            cal2 = self._get_or_create_calendar(conn, cal_cols, academic_year, 2)

            week_ids_cal1 = self._ensure_semester_weeks(
                conn=conn,
                weeks_cols=weeks_cols,
                calendar_id=cal1,
                weeks_in_semester=weeks_in_semester,
            )
            week_ids_cal2 = self._ensure_semester_weeks(
                conn=conn,
                weeks_cols=weeks_cols,
                calendar_id=cal2,
                weeks_in_semester=weeks_in_semester,
            )

            days = [1, 2, 3, 4, 5] + ([6] if include_saturday else [])
            for week_id in week_ids_cal1 + week_ids_cal2:
                self._ensure_slots_for_week(conn, slots_cols, week_id, days, pairs_per_day)

            conn.commit()

    def get_default_calendar_ids(self, academic_year: str = "2025/2026") -> tuple[Optional[int], Optional[int]]:
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                SELECT semester, id_calendar
                FROM AcademicCalendar
                WHERE academic_year = ?
                ORDER BY id_calendar DESC
                """,
                (academic_year,),
            )
            sem_to_id = {}
            for sem, cid in cur.fetchall():
                sem = int(sem)
                if sem not in sem_to_id:
                    sem_to_id[sem] = int(cid)
            return sem_to_id.get(1), sem_to_id.get(2)

    def list_time_slots(self, calendar_id: int) -> List[TimeSlot]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT
                    ts.id_slot,
                    sw.week_number_in_semester,
                    sw.week_type,
                    ts.day_of_week,
                    ts.pair_number,
                    ts.is_lunch_break
                FROM TimeSlots ts
                JOIN SemesterWeeks sw
                    ON ts.week_id = sw.id_week
                WHERE sw.calendar_id = ?
                ORDER BY
                    sw.week_number_in_semester,
                    sw.week_type,
                    ts.day_of_week,
                    ts.pair_number
                """,
                (int(calendar_id),),
            )
            rows = cur.fetchall()

            return [
                TimeSlot(
                    id_slot=int(r["id_slot"]),
                    week_number_in_semester=int(r.get("week_number_in_semester", 0) or 0),
                    week_type=int(r.get("week_type", 0) or 0),
                    day_of_week=int(r["day_of_week"]),
                    pair_number=int(r["pair_number"]),
                    is_lunch_break=bool(r.get("is_lunch_break", 0) or 0),
                )
                for r in rows
            ]

    def list_all(self):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute("SELECT * FROM AcademicCalendar ORDER BY id_calendar DESC")
            rows = cur.fetchall()
            return [SimpleNamespace(**r) for r in rows]

    def get_calendar(self, calendar_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                "SELECT * FROM AcademicCalendar WHERE id_calendar = ?",
                (int(calendar_id),),
            )
            row = cur.fetchone()
            return SimpleNamespace(**row) if row else None

    def _get_or_create_calendar(self, conn, cal_cols: set[str], academic_year: str, semester: int) -> int:
        cur = conn.execute(
            """
            SELECT id_calendar
            FROM AcademicCalendar
            WHERE academic_year=? AND semester=?
            ORDER BY id_calendar DESC
            LIMIT 1
            """,
            (academic_year, int(semester)),
        )
        row = cur.fetchone()
        if row:
            return int(row[0])

        if "week_type_mode" in cal_cols:
            cur = conn.execute(
                """
                INSERT INTO AcademicCalendar(academic_year, semester, week_type_mode)
                VALUES (?, ?, 1)
                """,
                (academic_year, int(semester)),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO AcademicCalendar(academic_year, semester)
                VALUES (?, ?)
                """,
                (academic_year, int(semester)),
            )
        return int(cur.lastrowid)

    def _ensure_semester_weeks(
        self,
        conn,
        weeks_cols: set[str],
        calendar_id: int,
        weeks_in_semester: int,
    ) -> list[int]:
        """
        Обеспечивает существование НОРМАЛЬНОГО набора недель:
        1..weeks_in_semester, где
        week_type = 1 для нечётных, 2 для чётных.
        """
        conn.row_factory = _row_to_dict

        cur = conn.execute(
            """
            SELECT id_week, week_number_in_semester, week_type
            FROM SemesterWeeks
            WHERE calendar_id = ?
            ORDER BY week_number_in_semester, id_week
            """,
            (int(calendar_id),),
        )
        rows = cur.fetchall()

        existing_by_number: dict[int, int] = {}
        for r in rows:
            wn = int(r.get("week_number_in_semester", 0) or 0)
            if wn > 0 and wn not in existing_by_number:
                existing_by_number[wn] = int(r["id_week"])

        result_ids: list[int] = []

        for week_number in range(1, int(weeks_in_semester) + 1):
            existing_id = existing_by_number.get(week_number)
            desired_week_type = 1 if week_number % 2 == 1 else 2

            if existing_id is not None:
                conn.execute(
                    """
                    UPDATE SemesterWeeks
                    SET week_type = ?,
                        is_study_week = COALESCE(is_study_week, 1)
                    WHERE id_week = ?
                    """,
                    (int(desired_week_type), int(existing_id)),
                )
                result_ids.append(int(existing_id))
                continue

            cols = ["calendar_id", "week_number_in_semester", "week_type"]
            vals = [int(calendar_id), int(week_number), int(desired_week_type)]

            if "is_study_week" in weeks_cols:
                cols.append("is_study_week")
                vals.append(1)

            if "comment" in weeks_cols:
                cols.append("comment")
                vals.append(None)

            placeholders = ",".join(["?"] * len(cols))
            cur = conn.execute(
                f"""
                INSERT INTO SemesterWeeks({','.join(cols)})
                VALUES ({placeholders})
                """,
                tuple(vals),
            )
            result_ids.append(int(cur.lastrowid))

        return result_ids

    def _ensure_slots_for_week(
        self,
        conn,
        slots_cols: set[str],
        week_id: int,
        days: list[int],
        pairs_per_day: int,
    ) -> None:
        for d in days:
            for p in range(1, pairs_per_day + 1):
                cur = conn.execute(
                    """
                    SELECT 1
                    FROM TimeSlots
                    WHERE week_id=? AND day_of_week=? AND pair_number=?
                    LIMIT 1
                    """,
                    (int(week_id), int(d), int(p)),
                )
                if cur.fetchone():
                    continue

                cols = ["week_id", "day_of_week", "pair_number"]
                vals = [int(week_id), int(d), int(p)]

                if "is_lunch_break" in slots_cols:
                    cols.append("is_lunch_break")
                    vals.append(0)

                if "start_time" in slots_cols:
                    cols.append("start_time")
                    vals.append(None)

                if "end_time" in slots_cols:
                    cols.append("end_time")
                    vals.append(None)

                placeholders = ",".join(["?"] * len(cols))
                conn.execute(
                    f"INSERT INTO TimeSlots({','.join(cols)}) VALUES ({placeholders})",
                    tuple(vals),
                )

# ============================================================
# Curriculum Repository
# ============================================================

class SqliteCurriculumRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    # ---------- helpers ----------
    def _get_or_create_subject(self, conn, subject_name: str) -> int:
        subject_name = subject_name.strip()
        cur = conn.execute("SELECT id_subject FROM Subjects WHERE subject_name = ?", (subject_name,))
        row = cur.fetchone()
        if row:
            return int(row[0]) if not isinstance(row, dict) else int(row["id_subject"])

        cur = conn.execute("INSERT INTO Subjects(subject_name) VALUES (?)", (subject_name,))
        return int(cur.lastrowid)

    def _room_type_from_part(self, part_type: str) -> str:
        pt = (part_type or "").lower()
        if pt == "lecture":
            return "lecture"
        if pt == "lab":
            return "lab"
        if pt == "computer_practice":
            return "computer"
        return "classroom"

    def _get_or_create_subject_id(self, conn, subject_name: str) -> int:
        subject_name = subject_name.strip()
        cur = conn.execute("SELECT id_subject FROM Subjects WHERE subject_name = ?", (subject_name,))
        row = cur.fetchone()
        if row:
            return int(row[0]) if not isinstance(row, dict) else int(row["id_subject"])
        cur = conn.execute("INSERT INTO Subjects(subject_name) VALUES (?)", (subject_name,))
        return int(cur.lastrowid)

    def _required_room_type(self, part_type: str) -> str:
        pt = (part_type or "").lower()
        if pt == "lecture":
            return "lecture"
        if pt == "lab":
            return "lab"
        if pt == "computer_practice":
            return "computer"
        return "classroom"

    def _get_or_create_curriculum_item(self, conn, group_id: int, subject_id: int, part_type: str) -> int:
        cur = conn.execute(
            """
            SELECT id_curriculum FROM CurriculumItems
            WHERE group_id=? AND subject_id=? AND part_type=?
            """,
            (int(group_id), int(subject_id), part_type),
        )
        row = cur.fetchone()
        if row:
            return int(row[0]) if not isinstance(row, dict) else int(row["id_curriculum"])

        req = self._required_room_type(part_type)
        cur = conn.execute(
            """
            INSERT INTO CurriculumItems(group_id, subject_id, part_type, required_room_type, hours_total_year, comment)
            VALUES (?, ?, ?, ?, 0, NULL)
            """,
            (int(group_id), int(subject_id), part_type, req),
        )
        return int(cur.lastrowid)

    def _set_sem_hours(self, conn, curriculum_id: int, calendar_id: int, hours: int) -> None:
        if int(hours) <= 0:
            # удалить semester plan
            cur = conn.execute(
                "SELECT id_plan FROM CurriculumSemesterPlan WHERE curriculum_id=? AND calendar_id=?",
                (int(curriculum_id), int(calendar_id)),
            )
            row = cur.fetchone()
            if row:
                plan_id = int(row[0]) if not isinstance(row, dict) else int(row["id_plan"])
                conn.execute("DELETE FROM WeeklyLoadPlan WHERE plan_id=?", (int(plan_id),))
            conn.execute(
                "DELETE FROM CurriculumSemesterPlan WHERE curriculum_id=? AND calendar_id=?",
                (int(curriculum_id), int(calendar_id)),
            )
            return

        cur = conn.execute(
            "SELECT id_plan FROM CurriculumSemesterPlan WHERE curriculum_id=? AND calendar_id=?",
            (int(curriculum_id), int(calendar_id)),
        )
        row = cur.fetchone()

        if row:
            plan_id = int(row[0]) if not isinstance(row, dict) else int(row["id_plan"])
            conn.execute(
                "UPDATE CurriculumSemesterPlan SET hours_in_semester=? WHERE id_plan=?",
                (int(hours), int(plan_id)),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO CurriculumSemesterPlan(curriculum_id, calendar_id, hours_in_semester, credits, spread_mode, comment)
                VALUES (?, ?, ?, NULL, 'auto_even', NULL)
                """,
                (int(curriculum_id), int(calendar_id), int(hours)),
            )
            plan_id = int(cur.lastrowid)

        # ВАЖНО: пересобираем WeeklyLoadPlan
        self._rebuild_weekly_plan_for_plan(
            conn=conn,
            plan_id=int(plan_id),
            calendar_id=int(calendar_id),
            hours_in_semester=int(hours),
        )
    # ---------- CRUD CurriculumItems + SemesterPlan ----------
    def create_curriculum_item(self, group_id: int, subject_name: str, part_type: str) -> int:
        with self._session_factory() as conn:
            subject_id = self._get_or_create_subject(conn, subject_name)
            required_room_type = self._room_type_from_part(part_type)
            cur = conn.execute(
                """
                INSERT INTO CurriculumItems(group_id, subject_id, part_type, required_room_type, hours_total_year, comment)
                VALUES (?, ?, ?, ?, 0, NULL)
                """,
                (int(group_id), int(subject_id), part_type, required_room_type),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_curriculum_item(self, curriculum_id: int, group_id: int, subject_name: str, part_type: str) -> None:
        with self._session_factory() as conn:
            subject_id = self._get_or_create_subject(conn, subject_name)
            required_room_type = self._room_type_from_part(part_type)
            conn.execute(
                """
                UPDATE CurriculumItems
                SET group_id=?, subject_id=?, part_type=?, required_room_type=?
                WHERE id_curriculum=?
                """,
                (int(group_id), int(subject_id), part_type, required_room_type, int(curriculum_id)),
            )
            conn.commit()

    def delete_curriculum_item(self, curriculum_id: int) -> None:
        with self._session_factory() as conn:
            conn.execute("DELETE FROM CurriculumItems WHERE id_curriculum=?", (int(curriculum_id),))
            conn.commit()

    def upsert_semester_hours(self, curriculum_id: int, calendar_id: int, hours_in_semester: int) -> None:
        with self._session_factory() as conn:
            if int(hours_in_semester) <= 0:
                cur = conn.execute(
                    """
                    SELECT id_plan
                    FROM CurriculumSemesterPlan
                    WHERE curriculum_id=? AND calendar_id=?
                    """,
                    (int(curriculum_id), int(calendar_id)),
                )
                row = cur.fetchone()
                if row:
                    plan_id = int(row[0]) if not isinstance(row, dict) else int(row["id_plan"])
                    conn.execute("DELETE FROM WeeklyLoadPlan WHERE plan_id=?", (int(plan_id),))
                conn.execute(
                    """
                    DELETE FROM CurriculumSemesterPlan
                    WHERE curriculum_id=? AND calendar_id=?
                    """,
                    (int(curriculum_id), int(calendar_id)),
                )
                conn.commit()
                return

            cur = conn.execute(
                """
                SELECT id_plan
                FROM CurriculumSemesterPlan
                WHERE curriculum_id=? AND calendar_id=?
                """,
                (int(curriculum_id), int(calendar_id)),
            )
            row = cur.fetchone()

            if row:
                plan_id = int(row[0]) if not isinstance(row, dict) else int(row["id_plan"])
                conn.execute(
                    """
                    UPDATE CurriculumSemesterPlan
                    SET hours_in_semester=?
                    WHERE id_plan=?
                    """,
                    (int(hours_in_semester), int(plan_id)),
                )
            else:
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
                    VALUES (?, ?, ?, NULL, 'auto_even', NULL)
                    """,
                    (int(curriculum_id), int(calendar_id), int(hours_in_semester)),
                )
                plan_id = int(cur.lastrowid)

            self._rebuild_weekly_plan_for_plan(
                conn=conn,
                plan_id=int(plan_id),
                calendar_id=int(calendar_id),
                hours_in_semester=int(hours_in_semester),
            )
            conn.commit()

    def upsert_subject_bundle(
        self,
        group_id: int,
        subject_name: str,
        cal_h1_id: int,
        cal_h2_id: int,
        lec_h1: int, lec_h2: int,
        pr_h1: int, pr_h2: int,
        cpr_h1: int, cpr_h2: int,
        lab_h1: int, lab_h2: int,
    ) -> None:
        with self._session_factory() as conn:
            subject_id = self._get_or_create_subject_id(conn, subject_name)

            parts = [
                ("lecture", int(lec_h1), int(lec_h2)),
                ("practice", int(pr_h1), int(pr_h2)),
                ("computer_practice", int(cpr_h1), int(cpr_h2)),
                ("lab", int(lab_h1), int(lab_h2)),
            ]

            cur = conn.execute(
                """
                SELECT id_curriculum, part_type
                FROM CurriculumItems
                WHERE group_id=? AND subject_id=?
                """,
                (int(group_id), int(subject_id)),
            )
            existing = {row[1]: int(row[0]) for row in cur.fetchall()}

            for part_type, h1, h2 in parts:
                if h1 <= 0 and h2 <= 0:
                    if part_type in existing:
                        conn.execute("DELETE FROM CurriculumItems WHERE id_curriculum=?", (existing[part_type],))
                    continue

                cid = existing.get(part_type)
                if cid is None:
                    cid = self._get_or_create_curriculum_item(conn, group_id, subject_id, part_type)

                if cal_h1_id and int(cal_h1_id) > 0:
                    self._set_sem_hours(conn, cid, int(cal_h1_id), h1)
                if cal_h2_id and int(cal_h2_id) > 0:
                    self._set_sem_hours(conn, cid, int(cal_h2_id), h2)

            conn.commit()

    def delete_subject_bundle(self, group_id: int, subject_name: str) -> None:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute("SELECT id_subject FROM Subjects WHERE subject_name=?", (subject_name.strip(),))
            row = cur.fetchone()
            if not row:
                return
            sid = int(row["id_subject"])
            conn.execute(
                "DELETE FROM CurriculumItems WHERE group_id=? AND subject_id=?",
                (int(group_id), int(sid)),
            )
            conn.commit()

    # ---------- UI ----------
    def list_curriculum_table(self, sem1_calendar_id: int, sem2_calendar_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict

            cur = conn.execute(
                """
                SELECT
                    ci.id_curriculum AS curriculum_id,
                    ci.group_id AS group_id,
                    sg.group_name AS group_name,
                    s.subject_name AS subject_name,
                    ci.part_type AS part_type,
                    csp.hours_in_semester AS hours
                FROM CurriculumSemesterPlan csp
                JOIN CurriculumItems ci ON ci.id_curriculum = csp.curriculum_id
                JOIN StudentGroups sg ON sg.id_group = ci.group_id
                JOIN Subjects s ON s.id_subject = ci.subject_id
                WHERE csp.calendar_id = ?
                """,
                (int(sem1_calendar_id),),
            )
            sem1 = cur.fetchall()

            cur = conn.execute(
                """
                SELECT
                    ci.id_curriculum AS curriculum_id,
                    csp.hours_in_semester AS hours
                FROM CurriculumSemesterPlan csp
                JOIN CurriculumItems ci ON ci.id_curriculum = csp.curriculum_id
                WHERE csp.calendar_id = ?
                """,
                (int(sem2_calendar_id),),
            )
            sem2_rows = cur.fetchall()
            sem2_map = {int(r["curriculum_id"]): int(r["hours"]) for r in sem2_rows}

            rows = []
            for r in sem1:
                cid = int(r["curriculum_id"])
                rows.append({
                    "group_id": int(r["group_id"]),
                    "group_name": r["group_name"],
                    "curriculum_id": cid,
                    "subject_name": r["subject_name"],
                    "part_type": r["part_type"],
                    "sem1_hours": int(r["hours"] or 0),
                    "sem2_hours": int(sem2_map.get(cid, 0)),
                })

            sem1_ids = {int(r["curriculum_id"]) for r in sem1}
            cur = conn.execute(
                """
                SELECT
                    ci.id_curriculum AS curriculum_id,
                    ci.group_id AS group_id,
                    sg.group_name AS group_name,
                    s.subject_name AS subject_name,
                    ci.part_type AS part_type,
                    csp.hours_in_semester AS hours
                FROM CurriculumSemesterPlan csp
                JOIN CurriculumItems ci ON ci.id_curriculum = csp.curriculum_id
                JOIN StudentGroups sg ON sg.id_group = ci.group_id
                JOIN Subjects s ON s.id_subject = ci.subject_id
                WHERE csp.calendar_id = ?
                """,
                (int(sem2_calendar_id),),
            )
            only2 = cur.fetchall()
            for r in only2:
                cid = int(r["curriculum_id"])
                if cid in sem1_ids:
                    continue
                rows.append({
                    "group_id": int(r["group_id"]),
                    "group_name": r["group_name"],
                    "curriculum_id": cid,
                    "subject_name": r["subject_name"],
                    "part_type": r["part_type"],
                    "sem1_hours": 0,
                    "sem2_hours": int(r["hours"] or 0),
                })

            order_part = {"lecture": 0, "practice": 1, "computer_practice": 2, "lab": 3}
            rows.sort(key=lambda x: (x["group_name"], x["subject_name"], order_part.get(x["part_type"], 9)))
            return rows

    def list_subject_bundle_table(self, cal_h1_id: int, cal_h2_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict

            cur = conn.execute(
                """
                SELECT
                    sg.id_group AS group_id,
                    sg.group_name AS group_name,
                    s.subject_name AS subject_name,
                    ci.part_type AS part_type,
                    COALESCE(p1.hours_in_semester, 0) AS h1,
                    COALESCE(p2.hours_in_semester, 0) AS h2
                FROM CurriculumItems ci
                JOIN StudentGroups sg ON sg.id_group = ci.group_id
                JOIN Subjects s ON s.id_subject = ci.subject_id
                LEFT JOIN CurriculumSemesterPlan p1
                    ON p1.curriculum_id = ci.id_curriculum AND p1.calendar_id = ?
                LEFT JOIN CurriculumSemesterPlan p2
                    ON p2.curriculum_id = ci.id_curriculum AND p2.calendar_id = ?
                ORDER BY sg.group_name, s.subject_name, ci.part_type
                """,
                (int(cal_h1_id), int(cal_h2_id)),
            )
            rows = cur.fetchall()

            out = {}
            for r in rows:
                key = (r["group_id"], r["subject_name"])
                item = out.setdefault(
                    key,
                    {
                        "group_id": r["group_id"],
                        "group_name": r["group_name"],
                        "subject_name": r["subject_name"],
                        "lec_h1": 0, "lec_h2": 0,
                        "pr_h1": 0, "pr_h2": 0,
                        "cpr_h1": 0, "cpr_h2": 0,
                        "lab_h1": 0, "lab_h2": 0,
                    },
                )
                pt = r["part_type"]
                if pt == "lecture":
                    item["lec_h1"] = int(r["h1"]); item["lec_h2"] = int(r["h2"])
                elif pt == "practice":
                    item["pr_h1"] = int(r["h1"]); item["pr_h2"] = int(r["h2"])
                elif pt == "computer_practice":
                    item["cpr_h1"] = int(r["h1"]); item["cpr_h2"] = int(r["h2"])
                elif pt == "lab":
                    item["lab_h1"] = int(r["h1"]); item["lab_h2"] = int(r["h2"])

            result = list(out.values())
            result.sort(key=lambda x: (x["group_name"], x["subject_name"]))
            return result

    def list_subject_bundle_table_filtered(self, cal_h1_id: int | None, cal_h2_id: int | None):
        if not cal_h1_id and not cal_h2_id:
            return []

        h1 = int(cal_h1_id) if cal_h1_id else 0
        h2 = int(cal_h2_id) if cal_h2_id else 0

        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict

            cur = conn.execute(
                """
                SELECT
                    sg.id_group AS group_id,
                    sg.group_name AS group_name,
                    s.subject_name AS subject_name,
                    ci.part_type AS part_type,
                    CASE WHEN ? > 0 THEN COALESCE(p1.hours_in_semester, 0) ELSE 0 END AS h1,
                    CASE WHEN ? > 0 THEN COALESCE(p2.hours_in_semester, 0) ELSE 0 END AS h2
                FROM CurriculumItems ci
                JOIN StudentGroups sg ON sg.id_group = ci.group_id
                JOIN Subjects s ON s.id_subject = ci.subject_id
                LEFT JOIN CurriculumSemesterPlan p1
                    ON p1.curriculum_id = ci.id_curriculum AND p1.calendar_id = ?
                LEFT JOIN CurriculumSemesterPlan p2
                    ON p2.curriculum_id = ci.id_curriculum AND p2.calendar_id = ?
                ORDER BY sg.group_name, s.subject_name, ci.part_type
                """,
                (h1, h2, h1, h2),
            )
            rows = cur.fetchall()

            out = {}
            for r in rows:
                key = (r["group_id"], r["subject_name"])
                item = out.setdefault(
                    key,
                    {
                        "group_id": int(r["group_id"]),
                        "group_name": r["group_name"],
                        "subject_name": r["subject_name"],
                        "lec_h1": 0, "lec_h2": 0,
                        "pr_h1": 0, "pr_h2": 0,
                        "cpr_h1": 0, "cpr_h2": 0,
                        "lab_h1": 0, "lab_h2": 0,
                    },
                )

                pt = r["part_type"]
                h1v = int(r["h1"] or 0)
                h2v = int(r["h2"] or 0)

                if pt == "lecture":
                    item["lec_h1"] = h1v; item["lec_h2"] = h2v
                elif pt == "practice":
                    item["pr_h1"] = h1v; item["pr_h2"] = h2v
                elif pt == "computer_practice":
                    item["cpr_h1"] = h1v; item["cpr_h2"] = h2v
                elif pt == "lab":
                    item["lab_h1"] = h1v; item["lab_h2"] = h2v

            result = []
            for it in out.values():
                sum_selected = 0
                if h1 > 0:
                    sum_selected += it["lec_h1"] + it["pr_h1"] + it["cpr_h1"] + it["lab_h1"]
                if h2 > 0:
                    sum_selected += it["lec_h2"] + it["pr_h2"] + it["cpr_h2"] + it["lab_h2"]

                if sum_selected > 0:
                    result.append(it)

            result.sort(key=lambda x: (x["group_name"], x["subject_name"]))
            return result

    # ---------- compatibility for generator ----------
    def list_curriculum_items(self, calendar_id: int) -> List[CurriculumItem]:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT DISTINCT
                    ci.id_curriculum,
                    ci.group_id,
                    ci.subject_id,
                    ci.part_type,
                    ci.required_room_type
                FROM CurriculumItems ci
                JOIN CurriculumSemesterPlan csp
                    ON csp.curriculum_id = ci.id_curriculum
                WHERE csp.calendar_id = ?
                ORDER BY ci.group_id, ci.subject_id, ci.part_type
                """,
                (int(calendar_id),),
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

    def get_semester_plans(self, calendar_id: int):
        """
        Совместимость со старой логикой генератора.
        Возвращает список объектов с доступом через точку.
        """
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT
                    csp.id_plan,
                    csp.curriculum_id,
                    csp.calendar_id,
                    csp.hours_in_semester,
                    csp.credits,
                    csp.spread_mode,
                    csp.comment,
                    ci.group_id,
                    ci.subject_id,
                    ci.part_type,
                    ci.required_room_type,
                    ci.hours_total_year
                FROM CurriculumSemesterPlan csp
                JOIN CurriculumItems ci
                    ON ci.id_curriculum = csp.curriculum_id
                WHERE csp.calendar_id = ?
                ORDER BY ci.group_id, ci.subject_id, ci.part_type
                """,
                (int(calendar_id),),
            )
            rows = cur.fetchall()
            return [SimpleNamespace(**r) for r in rows]

    def get_hours_for_curriculum(self, calendar_id: int) -> Dict[int, int]:
        with self._session_factory() as conn:
            cur = conn.execute(
                """
                SELECT curriculum_id, hours_in_semester
                FROM CurriculumSemesterPlan
                WHERE calendar_id = ?
                """,
                (int(calendar_id),),
            )
            return {int(cid): int(hours) for cid, hours in cur.fetchall()}

    def get_group_subject_load(self, calendar_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT
                    ci.id_curriculum,
                    ci.group_id,
                    ci.subject_id,
                    ci.part_type,
                    ci.required_room_type,
                    csp.hours_in_semester
                FROM CurriculumItems ci
                JOIN CurriculumSemesterPlan csp
                    ON csp.curriculum_id = ci.id_curriculum
                WHERE csp.calendar_id = ?
                ORDER BY ci.group_id, ci.subject_id, ci.part_type
                """,
                (int(calendar_id),),
            )
            return cur.fetchall()
        
    def get_curriculum_items_for_plans(self, plans_or_calendar_id):
        """
        Совместимость со старой логикой генератора.

        Поддерживает 2 варианта вызова:
        1) get_curriculum_items_for_plans(calendar_id: int)
        -> возвращает dict {curriculum_id: SimpleNamespace(...)}

        2) get_curriculum_items_for_plans(plans: list)
        -> возвращает dict {curriculum_id: SimpleNamespace(...)}

        Генератору нужен именно dict, чтобы дальше делать .get(...)
        """
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict

            # Вариант 1: передали calendar_id
            if isinstance(plans_or_calendar_id, int):
                cur = conn.execute(
                    """
                    SELECT
                        ci.id_curriculum,
                        ci.group_id,
                        ci.subject_id,
                        ci.part_type,
                        ci.required_room_type,
                        ci.hours_total_year
                    FROM CurriculumItems ci
                    JOIN CurriculumSemesterPlan csp
                        ON csp.curriculum_id = ci.id_curriculum
                    WHERE csp.calendar_id = ?
                    ORDER BY ci.group_id, ci.subject_id, ci.part_type
                    """,
                    (int(plans_or_calendar_id),),
                )
                rows = cur.fetchall()
                return {
                    int(r["id_curriculum"]): SimpleNamespace(**r)
                    for r in rows
                }

            # Вариант 2: передали список планов
            if isinstance(plans_or_calendar_id, list):
                curriculum_ids = []
                for p in plans_or_calendar_id:
                    if hasattr(p, "curriculum_id"):
                        curriculum_ids.append(int(p.curriculum_id))
                    elif isinstance(p, dict) and "curriculum_id" in p:
                        curriculum_ids.append(int(p["curriculum_id"]))

                curriculum_ids = list(dict.fromkeys(curriculum_ids))
                if not curriculum_ids:
                    return {}

                placeholders = ",".join("?" for _ in curriculum_ids)
                cur = conn.execute(
                    f"""
                    SELECT
                        ci.id_curriculum,
                        ci.group_id,
                        ci.subject_id,
                        ci.part_type,
                        ci.required_room_type,
                        ci.hours_total_year
                    FROM CurriculumItems ci
                    WHERE ci.id_curriculum IN ({placeholders})
                    ORDER BY ci.group_id, ci.subject_id, ci.part_type
                    """,
                    tuple(curriculum_ids),
                )
                rows = cur.fetchall()
                return {
                    int(r["id_curriculum"]): SimpleNamespace(**r)
                    for r in rows
                }

            raise TypeError(
                f"get_curriculum_items_for_plans ожидает int или list, получено: {type(plans_or_calendar_id).__name__}"
            )
        
    def _rebuild_weekly_plan_for_plan(self, conn, plan_id: int, calendar_id: int, hours_in_semester: int) -> None:
        """
        Пересобирает WeeklyLoadPlan для semester-plan.

        Логика:
        - берём реальные учебные недели семестра
        - распределяем часы по реальным week_number_in_semester
        - сохраняем порядок недель
        - не создаём записи с 0 часов
        """
        conn.execute("DELETE FROM WeeklyLoadPlan WHERE plan_id = ?", (int(plan_id),))

        total_hours = int(hours_in_semester or 0)
        if total_hours <= 0:
            return

        conn.row_factory = _row_to_dict
        cur = conn.execute(
            """
            SELECT
                id_week,
                COALESCE(week_number_in_semester, 0) AS week_number_in_semester,
                COALESCE(week_type, 0) AS week_type
            FROM SemesterWeeks
            WHERE calendar_id = ?
              AND COALESCE(is_study_week, 1) = 1
            ORDER BY week_number_in_semester, id_week
            """,
            (int(calendar_id),),
        )
        weeks = cur.fetchall()
        if not weeks:
            return

        week_ids = [int(w["id_week"]) for w in weeks]
        week_count = len(week_ids)

        base = total_hours // week_count
        rem = total_hours % week_count

        for i, week_id in enumerate(week_ids):
            hours_this_week = base + (1 if i < rem else 0)
            if hours_this_week <= 0:
                continue

            conn.execute(
                """
                INSERT INTO WeeklyLoadPlan(plan_id, week_id, hours_this_week, comment)
                VALUES (?, ?, ?, NULL)
                """,
                (int(plan_id), int(week_id), int(hours_this_week)),
            )

    def get_weekly_plans(self, calendar_id: int):
        """
        Возвращает weekly load plan по calendar_id
        с РЕАЛЬНЫМ week_number_in_semester.
        """
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT
                    wlp.id_week_plan,
                    wlp.plan_id,
                    wlp.week_id,
                    wlp.hours_this_week,

                    csp.curriculum_id,
                    csp.calendar_id,
                    csp.hours_in_semester,
                    csp.spread_mode,

                    ci.group_id,
                    ci.subject_id,
                    ci.part_type,
                    ci.required_room_type,

                    sw.week_type,
                    COALESCE(sw.week_number_in_semester, 0) AS week_number_in_semester,
                    COALESCE(sw.is_study_week, 1) AS is_study_week

                FROM WeeklyLoadPlan wlp
                JOIN CurriculumSemesterPlan csp
                    ON csp.id_plan = wlp.plan_id
                JOIN CurriculumItems ci
                    ON ci.id_curriculum = csp.curriculum_id
                JOIN SemesterWeeks sw
                    ON sw.id_week = wlp.week_id
                WHERE csp.calendar_id = ?
                ORDER BY
                    ci.group_id,
                    ci.subject_id,
                    ci.part_type,
                    sw.week_number_in_semester,
                    wlp.week_id
                """,
                (int(calendar_id),),
            )
            rows = cur.fetchall()
            return [SimpleNamespace(**r) for r in rows]
    
    def rebuild_all_weekly_plans(self) -> None:
        """
        Полностью пересобирает WeeklyLoadPlan для всех semester plan.
        """
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict

            conn.execute("DELETE FROM WeeklyLoadPlan")

            cur = conn.execute(
                """
                SELECT id_plan, calendar_id, hours_in_semester
                FROM CurriculumSemesterPlan
                ORDER BY id_plan
                """
            )
            plans = cur.fetchall()

            for p in plans:
                self._rebuild_weekly_plan_for_plan(
                    conn=conn,
                    plan_id=int(p["id_plan"]),
                    calendar_id=int(p["calendar_id"]),
                    hours_in_semester=int(p["hours_in_semester"] or 0),
                )

            conn.commit()

# ============================================================
# Schedule Repository
# ============================================================

class SqliteScheduleRepository:

    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._event_index: dict[int, object] = {}

    def set_generation_events(self, events: list[object]) -> None:
        self._event_index = {int(e.id_event): e for e in events}

    def list_variants(self, calendar_id: int | None = None):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            if calendar_id is None:
                cur = conn.execute(
                    """
                    SELECT *
                    FROM ScheduleVariants
                    ORDER BY created_at DESC, id_variant DESC
                    """
                )
            else:
                cur = conn.execute(
                    """
                    SELECT *
                    FROM ScheduleVariants
                    WHERE calendar_id = ?
                    ORDER BY created_at DESC, id_variant DESC
                    """,
                    (int(calendar_id),),
                )
            return cur.fetchall()

    def create_variant(
        self,
        calendar_id: int,
        rule_profile_key: str,
        name: str,
        objective_score: int,
        created_by: str,
    ) -> int:
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
                VALUES (?, ?, ?, ?, 'generated', ?)
                """,
                (
                    int(calendar_id),
                    str(rule_profile_key),
                    str(name),
                    int(objective_score),
                    f"created_by={created_by}",
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        
    def get_variant(self, variant_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT
                    id_variant,
                    calendar_id,
                    rule_profile_key,
                    name,
                    objective_score,
                    status,
                    comment,
                    created_at
                FROM ScheduleVariants
                WHERE id_variant = ?
                LIMIT 1
                """,
                (int(variant_id),),
            )
            row = cur.fetchone()
            return SimpleNamespace(**row) if row else None

    def update_variant(
        self,
        variant_id: int,
        name: str | None = None,
        status: str | None = None,
        comment: str | None = None,
        objective_score: int | None = None,
    ) -> None:
        fields = []
        params = []

        if name is not None:
            fields.append("name = ?")
            params.append(str(name))

        if status is not None:
            fields.append("status = ?")
            params.append(str(status))

        if comment is not None:
            fields.append("comment = ?")
            params.append(str(comment))

        if objective_score is not None:
            fields.append("objective_score = ?")
            params.append(int(objective_score))

        if not fields:
            return

        params.append(int(variant_id))

        with self._session_factory() as conn:
            conn.execute(
                f"""
                UPDATE ScheduleVariants
                SET {", ".join(fields)}
                WHERE id_variant = ?
                """,
                tuple(params),
            )
            conn.commit()

    def save_solution_entries(
        self,
        variant_id: int,
        solution_entries: List[SolutionEntry],
    ) -> None:
        with self._session_factory() as conn:
            for se in solution_entries:
                event_obj = self._event_index.get(int(se.event_id))

                if event_obj is None:
                    conn.execute(
                        """
                        INSERT INTO ScheduleEntries
                        (variant_id, slot_id, teacher_id, room_id, curriculum_id, group_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(variant_id),
                            int(se.slot_id),
                            int(se.teacher_id),
                            int(se.room_id),
                            int(se.event_id),
                            None,
                        ),
                    )
                    continue

                curriculum_ids = list(getattr(event_obj, "curriculum_ids", []))
                group_ids = list(getattr(event_obj, "group_ids", []))

                if not curriculum_ids:
                    curriculum_ids = [int(getattr(event_obj, "curriculum_id"))]
                if not group_ids:
                    group_ids = [int(getattr(event_obj, "group_id"))]

                merged = bool(getattr(event_obj, "merged", False))

                if merged:
                    if len(curriculum_ids) != len(group_ids):
                        raise ValueError(
                            f"Merged event save error: curriculum_ids count != group_ids count "
                            f"for event_id={se.event_id}"
                        )

                    for curriculum_id, group_id in zip(curriculum_ids, group_ids):
                        conn.execute(
                            """
                            INSERT INTO ScheduleEntries
                            (variant_id, slot_id, teacher_id, room_id, curriculum_id, group_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                int(variant_id),
                                int(se.slot_id),
                                int(se.teacher_id),
                                int(se.room_id),
                                int(curriculum_id),
                                int(group_id),
                            ),
                        )
                else:
                    conn.execute(
                        """
                        INSERT INTO ScheduleEntries
                        (variant_id, slot_id, teacher_id, room_id, curriculum_id, group_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(variant_id),
                            int(se.slot_id),
                            int(se.teacher_id),
                            int(se.room_id),
                            int(curriculum_ids[0]),
                            int(group_ids[0]),
                        ),
                    )

            conn.commit()

    def get_variant_dto(self, variant_id: int) -> ScheduleVariantDTO:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict

            cur = conn.execute(
                """
                SELECT
                    id_variant,
                    name,
                    objective_score
                FROM ScheduleVariants
                WHERE id_variant = ?
                """,
                (int(variant_id),),
            )
            variant = cur.fetchone()
            if not variant:
                raise ValueError(f"Вариант расписания с id={variant_id} не найден")

            cur = conn.execute(
                """
                SELECT
                    se.id_schedule,
                    se.variant_id,
                    se.slot_id,
                    se.group_id,
                    se.teacher_id,
                    se.curriculum_id,
                    se.room_id,
                    se.is_locked,

                    sg.group_name,
                    t.full_name AS teacher_name,
                    s.subject_name,
                    c.room_number,

                    ci.subject_id,
                    ci.part_type,
                    ts.day_of_week,
                    ts.pair_number,
                    sw.week_type,
                    COALESCE(sw.week_number_in_semester, 0) AS week_number

                FROM ScheduleEntries se
                LEFT JOIN StudentGroups sg
                    ON se.group_id = sg.id_group
                LEFT JOIN Teachers t
                    ON se.teacher_id = t.id_teacher
                LEFT JOIN CurriculumItems ci
                    ON se.curriculum_id = ci.id_curriculum
                LEFT JOIN Subjects s
                    ON ci.subject_id = s.id_subject
                LEFT JOIN Classes c
                    ON se.room_id = c.id_class
                LEFT JOIN TimeSlots ts
                    ON se.slot_id = ts.id_slot
                LEFT JOIN SemesterWeeks sw
                    ON ts.week_id = sw.id_week
                WHERE se.variant_id = ?
                ORDER BY
                    sw.week_number_in_semester,
                    sw.week_type,
                    ts.day_of_week,
                    ts.pair_number,
                    sg.group_name
                """,
                (int(variant_id),),
            )

            entries: List[ScheduleEntryDTO] = []
            for r in cur.fetchall():
                entries.append(
                    ScheduleEntryDTO(
                        id_schedule=int(r["id_schedule"]),
                        variant_id=int(r["variant_id"]),
                        curriculum_id=int(r["curriculum_id"]) if r.get("curriculum_id") is not None else 0,
                        event_id=int(r["curriculum_id"]) if r.get("curriculum_id") is not None else 0,
                        slot_id=int(r["slot_id"]),
                        week_number=int(r.get("week_number", 0) or 0),
                        week_type=int(r.get("week_type", 0) or 0),
                        day_of_week=int(r.get("day_of_week", 0) or 0),
                        pair_number=int(r.get("pair_number", 0) or 0),
                        group_id=int(r["group_id"]) if r["group_id"] is not None else 0,
                        group_name=r.get("group_name", "") or "",
                        teacher_id=int(r["teacher_id"]) if r["teacher_id"] is not None else 0,
                        teacher_name=r.get("teacher_name", "") or "",
                        subject_id=int(r["subject_id"]) if r.get("subject_id") is not None else 0,
                        subject_name=r.get("subject_name", "") or "",
                        part_type=r.get("part_type", "") or "",
                        room_id=int(r["room_id"]) if r["room_id"] is not None else 0,
                        room_number=r.get("room_number", "") or "",
                        is_locked=bool(r.get("is_locked", 0)),
                    )
                )

            return ScheduleVariantDTO(
                id_variant=int(variant["id_variant"]),
                name=str(variant["name"]),
                objective_score=int(variant.get("objective_score", 0) or 0),
                entries=entries,
            )

    def get_entry_by_id(self, variant_id: int, schedule_entry_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT
                    se.id_schedule,
                    se.variant_id,
                    se.slot_id,
                    se.group_id,
                    se.teacher_id,
                    se.curriculum_id,
                    se.room_id,
                    se.is_locked,
                    ts.day_of_week,
                    ts.pair_number,
                    sw.week_type,
                    COALESCE(sw.week_number_in_semester, 0) AS week_number
                FROM ScheduleEntries se
                LEFT JOIN TimeSlots ts
                    ON ts.id_slot = se.slot_id
                LEFT JOIN SemesterWeeks sw
                    ON sw.id_week = ts.week_id
                WHERE se.variant_id = ?
                  AND se.id_schedule = ?
                LIMIT 1
                """,
                (int(variant_id), int(schedule_entry_id)),
            )
            row = cur.fetchone()
            return SimpleNamespace(**row) if row else None

    def update_entry(self, entry) -> None:
        with self._session_factory() as conn:
            conn.execute(
                """
                UPDATE ScheduleEntries
                SET slot_id = ?,
                    teacher_id = ?,
                    room_id = ?,
                    is_locked = ?
                WHERE id_schedule = ?
                """,
                (
                    int(entry.slot_id),
                    int(entry.teacher_id),
                    int(entry.room_id),
                    1 if bool(getattr(entry, "is_locked", False)) else 0,
                    int(entry.id_schedule),
                ),
            )
            conn.commit()

    def lock_entry(self, variant_id: int, schedule_entry_id: int) -> None:
        with self._session_factory() as conn:
            conn.execute(
                """
                UPDATE ScheduleEntries
                SET is_locked = 1
                WHERE variant_id = ? AND id_schedule = ?
                """,
                (int(variant_id), int(schedule_entry_id)),
            )

            cur = conn.execute(
                """
                SELECT 1
                FROM ScheduleLocks
                WHERE variant_id = ? AND schedule_id = ?
                LIMIT 1
                """,
                (int(variant_id), int(schedule_entry_id)),
            )
            exists = cur.fetchone() is not None

            if not exists:
                conn.execute(
                    """
                    INSERT INTO ScheduleLocks(
                        variant_id,
                        schedule_id,
                        lock_slot,
                        lock_teacher,
                        lock_class,
                        comment
                    )
                    VALUES (?, ?, 1, 1, 1, NULL)
                    """,
                    (int(variant_id), int(schedule_entry_id)),
                )

            conn.commit()

    def exists_group_conflict(
        self,
        variant_id: int,
        group_id: int,
        slot_id: int,
        exclude_entry_id: Optional[int] = None,
    ) -> bool:
        with self._session_factory() as conn:
            params = [int(variant_id), int(group_id), int(slot_id)]
            sql = """
                SELECT 1
                FROM ScheduleEntries
                WHERE variant_id = ?
                  AND group_id = ?
                  AND slot_id = ?
            """
            if exclude_entry_id is not None:
                sql += " AND id_schedule <> ?"
                params.append(int(exclude_entry_id))
            sql += " LIMIT 1"
            cur = conn.execute(sql, tuple(params))
            return cur.fetchone() is not None

    def exists_teacher_conflict(
        self,
        variant_id: int,
        teacher_id: int,
        slot_id: int,
        exclude_entry_id: Optional[int] = None,
    ) -> bool:
        with self._session_factory() as conn:
            params = [int(variant_id), int(teacher_id), int(slot_id)]
            sql = """
                SELECT 1
                FROM ScheduleEntries
                WHERE variant_id = ?
                  AND teacher_id = ?
                  AND slot_id = ?
            """
            if exclude_entry_id is not None:
                sql += " AND id_schedule <> ?"
                params.append(int(exclude_entry_id))
            sql += " LIMIT 1"
            cur = conn.execute(sql, tuple(params))
            return cur.fetchone() is not None

    def exists_room_conflict(
        self,
        variant_id: int,
        room_id: int,
        slot_id: int,
        exclude_entry_id: Optional[int] = None,
    ) -> bool:
        with self._session_factory() as conn:
            params = [int(variant_id), int(room_id), int(slot_id)]
            sql = """
                SELECT 1
                FROM ScheduleEntries
                WHERE variant_id = ?
                  AND room_id = ?
                  AND slot_id = ?
            """
            if exclude_entry_id is not None:
                sql += " AND id_schedule <> ?"
                params.append(int(exclude_entry_id))
            sql += " LIMIT 1"
            cur = conn.execute(sql, tuple(params))
            return cur.fetchone() is not None

    def get_curriculum(self, curriculum_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT *
                FROM CurriculumItems
                WHERE id_curriculum = ?
                LIMIT 1
                """,
                (int(curriculum_id),),
            )
            row = cur.fetchone()
            return SimpleNamespace(**row) if row else None

    def get_group(self, group_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT *
                FROM StudentGroups
                WHERE id_group = ?
                LIMIT 1
                """,
                (int(group_id),),
            )
            row = cur.fetchone()
            return SimpleNamespace(**row) if row else None

    def to_dto(self, entry) -> ScheduleEntryDTO:
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT
                    se.id_schedule,
                    se.variant_id,
                    se.slot_id,
                    se.group_id,
                    se.teacher_id,
                    se.curriculum_id,
                    se.room_id,
                    se.is_locked,

                    sg.group_name,
                    t.full_name AS teacher_name,
                    s.subject_name,
                    c.room_number,

                    ci.subject_id,
                    ci.part_type,
                    ts.day_of_week,
                    ts.pair_number,
                    sw.week_type,
                    COALESCE(sw.week_number_in_semester, 0) AS week_number

                FROM ScheduleEntries se
                LEFT JOIN StudentGroups sg
                    ON se.group_id = sg.id_group
                LEFT JOIN Teachers t
                    ON se.teacher_id = t.id_teacher
                LEFT JOIN CurriculumItems ci
                    ON se.curriculum_id = ci.id_curriculum
                LEFT JOIN Subjects s
                    ON ci.subject_id = s.id_subject
                LEFT JOIN Classes c
                    ON se.room_id = c.id_class
                LEFT JOIN TimeSlots ts
                    ON se.slot_id = ts.id_slot
                LEFT JOIN SemesterWeeks sw
                    ON ts.week_id = sw.id_week
                WHERE se.id_schedule = ?
                LIMIT 1
                """,
                (int(entry.id_schedule),),
            )
            r = cur.fetchone()
            if not r:
                raise ValueError(f"Запись id_schedule={entry.id_schedule} не найдена")

            return ScheduleEntryDTO(
                id_schedule=int(r["id_schedule"]),
                variant_id=int(r["variant_id"]),
                curriculum_id=int(r["curriculum_id"]) if r.get("curriculum_id") is not None else 0,
                event_id=int(r["curriculum_id"]) if r.get("curriculum_id") is not None else 0,
                slot_id=int(r["slot_id"]),
                week_number=int(r.get("week_number", 0) or 0),
                week_type=int(r.get("week_type", 0) or 0),
                day_of_week=int(r.get("day_of_week", 0) or 0),
                pair_number=int(r.get("pair_number", 0) or 0),
                group_id=int(r["group_id"]) if r["group_id"] is not None else 0,
                group_name=r.get("group_name", "") or "",
                teacher_id=int(r["teacher_id"]) if r["teacher_id"] is not None else 0,
                teacher_name=r.get("teacher_name", "") or "",
                subject_id=int(r["subject_id"]) if r.get("subject_id") is not None else 0,
                subject_name=r.get("subject_name", "") or "",
                part_type=r.get("part_type", "") or "",
                room_id=int(r["room_id"]) if r["room_id"] is not None else 0,
                room_number=r.get("room_number", "") or "",
                is_locked=bool(r.get("is_locked", 0)),
            )

    def log_edit(
        self,
        variant_id: int,
        edited_by: str,
        action: str,
        before,
        after,
        comment: str | None = None,
    ) -> None:
        def _to_jsonable(obj):
            if obj is None:
                return None
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            return str(obj)

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
                    str(edited_by),
                    str(action),
                    json.dumps(_to_jsonable(before), ensure_ascii=False, default=str),
                    json.dumps(_to_jsonable(after), ensure_ascii=False, default=str),
                    comment,
                ),
            )
            conn.commit()

    def list_locks_for_calendar(self, calendar_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT
                    sl.id_lock,
                    sl.variant_id,
                    sl.schedule_id,
                    sl.lock_slot,
                    sl.lock_teacher,
                    sl.lock_class,
                    se.slot_id,
                    se.teacher_id,
                    se.room_id,
                    se.curriculum_id,
                    se.group_id
                FROM ScheduleLocks sl
                JOIN ScheduleEntries se
                    ON se.id_schedule = sl.schedule_id
                JOIN ScheduleVariants sv
                    ON sv.id_variant = sl.variant_id
                WHERE sv.calendar_id = ?
                ORDER BY sl.id_lock
                """,
                (int(calendar_id),),
            )
            return [SimpleNamespace(**r) for r in cur.fetchall()]
        
    def list_groups_for_variant(self, variant_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT DISTINCT
                    se.group_id,
                    sg.group_name
                FROM ScheduleEntries se
                JOIN StudentGroups sg ON sg.id_group = se.group_id
                WHERE se.variant_id = ?
                AND se.group_id IS NOT NULL
                ORDER BY sg.group_name
                """,
                (int(variant_id),),
            )
            return [SimpleNamespace(**r) for r in cur.fetchall()]

    def list_teachers_for_variant(self, variant_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT DISTINCT
                    se.teacher_id,
                    t.full_name AS teacher_name
                FROM ScheduleEntries se
                JOIN Teachers t ON t.id_teacher = se.teacher_id
                WHERE se.variant_id = ?
                AND se.teacher_id IS NOT NULL
                ORDER BY t.full_name
                """,
                (int(variant_id),),
            )
            return [SimpleNamespace(**r) for r in cur.fetchall()]

    def list_rooms_for_variant(self, variant_id: int):
        with self._session_factory() as conn:
            conn.row_factory = _row_to_dict
            cur = conn.execute(
                """
                SELECT DISTINCT
                    se.room_id,
                    c.room_number
                FROM ScheduleEntries se
                JOIN Classes c ON c.id_class = se.room_id
                WHERE se.variant_id = ?
                AND se.room_id IS NOT NULL
                ORDER BY c.room_number
                """,
                (int(variant_id),),
            )
            return [SimpleNamespace(**r) for r in cur.fetchall()]

    def get_variant_entries_filtered(
        self,
        variant_id: int,
        group_id: int | None = None,
        teacher_id: int | None = None,
        room_id: int | None = None,
    ) -> list[ScheduleEntryDTO]:
        dto = self.get_variant_dto(int(variant_id))
        entries = list(dto.entries)

        if group_id is not None:
            entries = [e for e in entries if int(getattr(e, "group_id", 0) or 0) == int(group_id)]

        if teacher_id is not None:
            entries = [e for e in entries if int(getattr(e, "teacher_id", 0) or 0) == int(teacher_id)]

        if room_id is not None:
            entries = [e for e in entries if int(getattr(e, "room_id", 0) or 0) == int(room_id)]

        return entries