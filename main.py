from __future__ import annotations

import sys

from app.presentation.qt_app import run


def main() -> int:
    return int(run())


if __name__ == "__main__":
    raise SystemExit(main())
