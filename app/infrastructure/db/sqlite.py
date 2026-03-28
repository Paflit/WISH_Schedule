from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable


def _load_schema_sql() -> str:
    """
    Загружает актуальную схему из schema.sql рядом с этим файлом.
    """
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


def _run_post_schema_migrations(conn: sqlite3.Connection) -> None:
    """
    Простые additive-миграции для старых БД.
    """

    # ---------------------------------------------------------
    # Classes.room_types_json
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # ScheduleEntries.event_id
    # ---------------------------------------------------------
    if _table_exists(conn, "ScheduleEntries"):
        columns = _get_columns(conn, "ScheduleEntries")
        if "event_id" not in columns:
            conn.execute("ALTER TABLE ScheduleEntries ADD COLUMN event_id INTEGER")

    # ---------------------------------------------------------
    # ScheduleLocks.event_id
    # ---------------------------------------------------------
    if _table_exists(conn, "ScheduleLocks"):
        columns = _get_columns(conn, "ScheduleLocks")
        if "event_id" not in columns:
            conn.execute("ALTER TABLE ScheduleLocks ADD COLUMN event_id INTEGER")

    # ---------------------------------------------------------
    # Индексы, которые зависят от новых колонок
    # ---------------------------------------------------------
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

    Контракт:
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
    """
    Обратная совместимость со старым DI-кодом.

    Поддерживается формат:
        sqlite:///relative/path.db
        sqlite:////absolute/path.db
    """
    if not db_url.startswith("sqlite:///"):
        raise ValueError("Поддерживается только формат sqlite:///...")

    db_path = db_url.replace("sqlite:///", "", 1)
    session_factory = make_session_factory(db_path)
    return None, session_factory