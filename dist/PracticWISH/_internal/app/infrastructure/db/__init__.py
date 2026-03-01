# app/infrastructure/db/__init__.py
"""
Database layer (SQLite implementation).

Здесь находятся:
- создание подключения (engine/session)
- реализация репозиториев (repositories.py)
- опционально: schema.sql или Alembic миграции

Infrastructure-слой:
- реализует порты из app.domain.ports
- знает про SQL/ORM
- НЕ должен содержать бизнес-логику

Использование:
    from app.infrastructure.db.sqlite import create_engine_and_session_factory
    from app.infrastructure.db.repositories import SqliteTeachersRepository
"""

__all__ = [
    "sqlite",
    "repositories",
]