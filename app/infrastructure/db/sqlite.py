from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Callable


def _load_schema_sql() -> str:
    if getattr(sys, "frozen", False):
        base_path = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        schema_path = base_path / "app" / "infrastructure" / "db" / "schema.sql"
    else:
        schema_path = Path(__file__).with_name("schema.sql")

    if not schema_path.exists():
        raise FileNotFoundError(f"Не найден schema.sql по пути: {schema_path}")
    return schema_path.read_text(encoding="utf-8")


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name=?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _get_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(r[1]) for r in rows}


def _get_indexes(conn: sqlite3.Connection, table_name: str) -> list[tuple]:
    return conn.execute(f"PRAGMA index_list({table_name})").fetchall()


def _get_index_columns(conn: sqlite3.Connection, index_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
    return [str(r[2]) for r in rows]


def _column_notnull(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    for row in rows:
        if str(row[1]) == column_name:
            return bool(int(row[3]))
    return False


def _rebuild_generation_draft_entries(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE GenerationDraftEntries RENAME TO GenerationDraftEntries_old")
    conn.execute(
        """
        CREATE TABLE GenerationDraftEntries (
            id_draft_entry INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            slot_id INTEGER NOT NULL,
            teacher_id INTEGER,
            room_id INTEGER,
            comment TEXT,
            FOREIGN KEY (draft_id) REFERENCES GenerationDrafts(id_draft) ON DELETE CASCADE,
            FOREIGN KEY (slot_id) REFERENCES TimeSlots(id_slot) ON DELETE CASCADE,
            FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE SET NULL,
            FOREIGN KEY (room_id) REFERENCES Classes(id_class) ON DELETE SET NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO GenerationDraftEntries(id_draft_entry, draft_id, event_id, slot_id, teacher_id, room_id, comment)
        SELECT id_draft_entry, draft_id, event_id, slot_id, teacher_id, room_id, comment
        FROM GenerationDraftEntries_old
        """
    )
    conn.execute("DROP TABLE GenerationDraftEntries_old")


def _rebuild_schedule_entries_nullable_room(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE ScheduleEntries RENAME TO ScheduleEntries_old")
    conn.execute(
        """
        CREATE TABLE ScheduleEntries (
            id_schedule INTEGER PRIMARY KEY AUTOINCREMENT,
            variant_id INTEGER NOT NULL,
            event_id INTEGER,
            slot_id INTEGER NOT NULL,
            group_id INTEGER,
            teacher_id INTEGER,
            curriculum_id INTEGER NOT NULL,
            room_id INTEGER,
            is_locked INTEGER NOT NULL DEFAULT 0,
            comment TEXT,
            FOREIGN KEY (variant_id) REFERENCES ScheduleVariants(id_variant) ON DELETE CASCADE,
            FOREIGN KEY (slot_id) REFERENCES TimeSlots(id_slot) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES StudentGroups(id_group) ON DELETE SET NULL,
            FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE SET NULL,
            FOREIGN KEY (curriculum_id) REFERENCES CurriculumItems(id_curriculum) ON DELETE RESTRICT,
            FOREIGN KEY (room_id) REFERENCES Classes(id_class) ON DELETE SET NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO ScheduleEntries(id_schedule, variant_id, event_id, slot_id, group_id, teacher_id, curriculum_id, room_id, is_locked, comment)
        SELECT id_schedule, variant_id, event_id, slot_id, group_id, teacher_id, curriculum_id, room_id, is_locked, comment
        FROM ScheduleEntries_old
        """
    )
    conn.execute("DROP TABLE ScheduleEntries_old")


def _run_post_schema_migrations(conn: sqlite3.Connection) -> None:

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS TeacherGroupAssignments (
            teacher_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            PRIMARY KEY (teacher_id, group_id),
            FOREIGN KEY (teacher_id) REFERENCES Teachers(id_teacher) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES StudentGroups(id_group) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS RoomSubjectAssignments (
            room_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            PRIMARY KEY (room_id, subject_id),
            FOREIGN KEY (room_id) REFERENCES Classes(id_class) ON DELETE CASCADE,
            FOREIGN KEY (subject_id) REFERENCES Subjects(id_subject) ON DELETE CASCADE
        )
        """
    )

    # Classes.room_types_json
    if _table_exists(conn, "Classes"):
        columns = _get_columns(conn, "Classes")
        if "room_types_json" not in columns:
            conn.execute("ALTER TABLE Classes ADD COLUMN room_types_json TEXT")

        # заполнить новое поле из старого room_type, если оно пустое
        conn.execute(
            """
            UPDATE Classes
            SET room_types_json =
                CASE
                    WHEN room_type IS NULL OR TRIM(room_type) = '' THEN '[]'
                    ELSE '["' || REPLACE(room_type, '"', '') || '"]'
                END
            WHERE room_types_json IS NULL OR TRIM(room_types_json) = ''
            """
        )

    # ScheduleEntries.event_id
    if _table_exists(conn, "ScheduleEntries"):
        columns = _get_columns(conn, "ScheduleEntries")
        if "event_id" not in columns:
            conn.execute("ALTER TABLE ScheduleEntries ADD COLUMN event_id INTEGER")
        if (
            ("room_id" in columns and _column_notnull(conn, "ScheduleEntries", "room_id"))
            or ("teacher_id" in columns and _column_notnull(conn, "ScheduleEntries", "teacher_id"))
        ):
            _rebuild_schedule_entries_nullable_room(conn)

    if _table_exists(conn, "GenerationDraftEntries"):
        for index_row in _get_indexes(conn, "GenerationDraftEntries"):
            index_name = str(index_row[1])
            is_unique = int(index_row[2]) == 1
            if not is_unique:
                continue
            if _get_index_columns(conn, index_name) == ["draft_id", "event_id"]:
                _rebuild_generation_draft_entries(conn)
                break

    # ScheduleLocks.event_id
    if _table_exists(conn, "ScheduleLocks"):
        columns = _get_columns(conn, "ScheduleLocks")
        if "event_id" not in columns:
            conn.execute("ALTER TABLE ScheduleLocks ADD COLUMN event_id INTEGER")

    if _table_exists(conn, "ScheduleEntries"):
        columns = _get_columns(conn, "ScheduleEntries")
        if "event_id" in columns:
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_schedule_entries_event
                ON ScheduleEntries(event_id)
                """
            )

    if _table_exists(conn, "ScheduleLocks"):
        columns = _get_columns(conn, "ScheduleLocks")
        if "event_id" in columns:
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_schedule_locks_event
                ON ScheduleLocks(event_id)
                """
            )


def make_session_factory(db_path: str) -> Callable[[], sqlite3.Connection]:
    """
    Возвращает фабрику sqlite3-соединений.
    - принимает путь к sqlite-файлу;
    - гарантирует существование директории;
    - при первом подключении применяет schema.sql;
    - выполняет простые миграции старой БД;
    - каждое соединение включает PRAGMA foreign_keys = ON.
    """
    path = Path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = _load_schema_sql()

    def session_factory() -> sqlite3.Connection:
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(schema_sql)
        _run_post_schema_migrations(conn)
        conn.commit()
        return conn

    with session_factory() as conn:
        conn.commit()

    return session_factory


def create_engine_and_session_factory(db_url: str):
    if not db_url.startswith("sqlite:///"):
        raise ValueError("Поддерживается только формат sqlite:///...")

    db_path = db_url.replace("sqlite:///", "", 1)
    session_factory = make_session_factory(db_path)
    return None, session_factory
