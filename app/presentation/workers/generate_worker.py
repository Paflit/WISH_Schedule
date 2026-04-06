from __future__ import annotations

import json
import sys
import traceback

from app.application.use_cases.generate_schedule import GenerateScheduleCommand
from app.di import build_container


def _emit(payload: dict) -> None:
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
            [--draft-id <id>] [--use-draft-as-locks]
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

    draft_id = None
    use_draft_as_locks = False
    base_variant_id = None
    use_base_variant_as_locks = False

    idx = 4
    while idx < len(argv):
        token = str(argv[idx])
        if token == "--draft-id":
            if idx + 1 >= len(argv):
                raise ValueError("После --draft-id должен идти id черновика.")
            try:
                draft_id = int(argv[idx + 1])
            except ValueError as exc:
                raise ValueError("draft_id должен быть целым числом.") from exc
            idx += 2
            continue
        if token == "--use-draft-as-locks":
            use_draft_as_locks = True
            idx += 1
            continue
        if token == "--base-variant-id":
            if idx + 1 >= len(argv):
                raise ValueError("После --base-variant-id должен идти id варианта.")
            try:
                base_variant_id = int(argv[idx + 1])
            except ValueError as exc:
                raise ValueError("base_variant_id должен быть целым числом.") from exc
            idx += 2
            continue
        if token == "--use-base-variant-as-locks":
            use_base_variant_as_locks = True
            idx += 1
            continue
        raise ValueError(f"Неизвестный аргумент: {token}")

    return GenerateScheduleCommand(
        calendar_id=calendar_id,
        variants_count=variants_count,
        time_limit_seconds=time_limit_seconds,
        draft_id=draft_id,
        use_draft_as_locks=use_draft_as_locks,
        base_variant_id=base_variant_id,
        use_base_variant_as_locks=use_base_variant_as_locks,
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
                "draft_id": int(command.draft_id) if command.draft_id else None,
                "use_draft_as_locks": bool(command.use_draft_as_locks),
                "base_variant_id": int(command.base_variant_id) if command.base_variant_id else None,
                "use_base_variant_as_locks": bool(command.use_base_variant_as_locks),
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
