from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtWidgets import QInputDialog


def list_database_files() -> list[Path]:
    base_dir = Path(os.getenv("APP_BASE_DIR", Path.cwd()))
    data_dir = base_dir / "data"
    if not data_dir.exists():
        return []
    return sorted(
        [p for p in data_dir.iterdir() if p.is_file() and p.suffix.lower() in {".db", ".bd"}],
        key=lambda p: p.name.lower(),
    )


def choose_database(parent=None, *, force: bool = False) -> Path | None:
    db_files = list_database_files()
    if len(db_files) <= 1:
        if force and db_files:
            return db_files[0]
        return None

    names = [p.name for p in db_files]
    selected, ok = QInputDialog.getItem(
        parent,
        "Выбор базы данных",
        "Выберите базу данных для работы:",
        names,
        0,
        False,
    )
    if ok and selected:
        selected_path = next((p for p in db_files if p.name == selected), None)
        if selected_path is not None:
            os.environ["APP_DB_PATH"] = str(selected_path)
            return selected_path
    return None


def choose_database_if_needed(parent=None) -> Path | None:
    return choose_database(parent, force=False)
