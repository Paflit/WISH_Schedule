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
        raise FileNotFoundError(
            f"Не найден schema.sql по пути: {schema_path}"
        )
    return schema_path.read_text(encoding="utf-8")


def make_session_factory(db_path: str) -> Callable[[], sqlite3.Connection]:
    """
    Возвращает фабрику sqlite3-соединений.

    Контракт:
    - принимает путь к sqlite-файлу;
    - гарантирует существование директории;
    - при первом подключении применяет schema.sql;
    - каждое соединение включает PRAGMA foreign_keys = ON.

    Это согласовано с новым app/di.py.
    """
    path = Path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = _load_schema_sql()

    def session_factory() -> sqlite3.Connection:
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(schema_sql)
        return conn

    # Инициализируем схему один раз при создании factory
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