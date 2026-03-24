from __future__ import annotations

import json
import sys
import traceback

from app.application.use_cases.generate_schedule import GenerateScheduleCommand
from app.di import build_container


def _emit(payload: dict) -> None:
    """
    Пишем только JSON-строки в stdout, чтобы UI мог безопасно парсить события worker-процесса.
    """
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _emit_progress(stage: str, data: dict) -> None:
    _emit(
        {
            "type": "progress",
            "stage": str(stage),
            "data": data or {},
        }
    )


def _emit_error(message: str, *, details: str | None = None) -> None:
    payload = {
        "type": "error",
        "message": str(message),
    }
    if details:
        payload["details"] = str(details)
    _emit(payload)


def _emit_done(result) -> None:
    variants = list(getattr(result, "variants", []) or [])

    payload_variants = []
    for variant in variants:
        payload_variants.append(
            {
                "id_variant": int(getattr(variant, "id_variant", 0) or 0),
                "name": str(getattr(variant, "name", "") or ""),
                "objective_score": int(getattr(variant, "objective_score", 0) or 0),
                "entries_count": len(list(getattr(variant, "entries", []) or [])),
            }
        )

    _emit(
        {
            "type": "done",
            "variants_count": len(payload_variants),
            "variants": payload_variants,
            "message": str(getattr(result, "message", "") or ""),
        }
    )


def _parse_args(argv: list[str]) -> GenerateScheduleCommand:
    """
    Ожидаемый формат:
        python -m app.presentation.workers.generate_worker <calendar_id> <variants_count> <time_limit_seconds>
    """
    if len(argv) < 4:
        raise ValueError(
            "Недостаточно аргументов. Ожидается: "
            "<calendar_id> <variants_count> <time_limit_seconds>"
        )

    try:
        calendar_id = int(argv[1])
        variants_count = int(argv[2])
        time_limit_seconds = int(argv[3])
    except ValueError as exc:
        raise ValueError(
            "Аргументы calendar_id, variants_count и time_limit_seconds должны быть целыми числами."
        ) from exc

    return GenerateScheduleCommand(
        calendar_id=calendar_id,
        variants_count=variants_count,
        time_limit_seconds=time_limit_seconds,
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv

    try:
        command = _parse_args(argv)
    except Exception as exc:
        _emit_error(str(exc))
        return 1

    try:
        _emit(
            {
                "type": "started",
                "calendar_id": int(command.calendar_id),
                "variants_count": int(command.variants_count),
                "time_limit_seconds": int(command.time_limit_seconds),
            }
        )

        container = build_container()
        generate_uc = getattr(container, "generate_schedule_uc", None)
        if generate_uc is None:
            raise RuntimeError(
                "В контейнере не найден generate_schedule_uc. Проверь app/di.py."
            )

        result = generate_uc.execute(command, progress_cb=_emit_progress)
        _emit_done(result)
        return 0

    except Exception as exc:
        _emit_error(
            str(exc),
            details=traceback.format_exc(),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())