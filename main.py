from __future__ import annotations

import sys

from app.presentation.qt_app import run


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--generate-worker":
        from app.presentation.workers.generate_worker import main as worker_main

        return int(worker_main([sys.argv[0], *sys.argv[2:]]))

    return int(run())


if __name__ == "__main__":
    raise SystemExit(main())
