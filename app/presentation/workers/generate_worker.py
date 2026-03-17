from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.di import build_container
from app.application.use_cases.generate_schedule import GenerateScheduleCommand


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def progress_cb(stage: str, payload: dict) -> None:
    emit({
        "type": "progress",
        "stage": stage,
        "payload": payload,
        "message": f"{stage}: {payload}",
    })


def main() -> int:
    try:
        if len(sys.argv) < 4:
            emit({
                "type": "error",
                "message": "Недостаточно аргументов. Ожидалось: calendar_id variants_count time_limit_seconds",
            })
            return 2

        calendar_id = int(sys.argv[1])
        variants_count = int(sys.argv[2])
        time_limit_seconds = int(sys.argv[3])

        emit({
            "type": "progress",
            "stage": "worker_started",
            "payload": {
                "project_root": str(PROJECT_ROOT),
                "calendar_id": calendar_id,
                "variants_count": variants_count,
                "time_limit_seconds": time_limit_seconds,
            },
            "message": "worker_started",
        })

        emit({
            "type": "progress",
            "stage": "container_building",
            "payload": {},
            "message": "container_building",
        })

        container = build_container()

        emit({
            "type": "progress",
            "stage": "container_built",
            "payload": {},
            "message": "container_built",
        })

        cmd = GenerateScheduleCommand(
            calendar_id=calendar_id,
            variants_count=variants_count,
            time_limit_seconds=time_limit_seconds,
        )

        result = container.generate_schedule_uc.execute(
            cmd,
            progress_cb=progress_cb,
        )

        variants = getattr(result, "variants", []) or []
        variant_ids = [int(getattr(v, "id_variant", 0) or 0) for v in variants]
        variant_names = [str(getattr(v, "name", "") or "") for v in variants]

        emit({
            "type": "result",
            "calendar_id": calendar_id,
            "variant_count": len(variants),
            "variant_ids": variant_ids,
            "variant_names": variant_names,
        })
        return 0

    except Exception as e:
        emit({
            "type": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        })
        return 1


if __name__ == "__main__":
    raise SystemExit(main())