from __future__ import annotations

import sys

from app.di import build_container
from app.presentation.qt_app import run


def main() -> int:
    """
    Финальная точка входа приложения.

    Здесь остаются только:
    - создание контейнера зависимостей;
    - запуск UI.

    Никакой автоматической правки БД / календаря / weekly plan на старте
    здесь больше не выполняется.
    """
    container = build_container()
    return int(run(container))


if __name__ == "__main__":
    raise SystemExit(main())