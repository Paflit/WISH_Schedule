from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from app.application.dto.schedule_dto import GenerationResultDTO, ScheduleVariantDTO


@dataclass(frozen=True)
class GenerateFormState:

    calendar_id: Optional[int] = None

    DEFAULT_VARIANTS_COUNT = 1
    DEFAULT_TIME_LIMIT_SECONDS = 600

    def normalized(self) -> "GenerateFormState":
        calendar_id = int(self.calendar_id) if self.calendar_id is not None else None
        return GenerateFormState(calendar_id=calendar_id)

    @property
    def variants_count(self) -> int:
        return self.DEFAULT_VARIANTS_COUNT

    @property
    def time_limit_seconds(self) -> int:
        return self.DEFAULT_TIME_LIMIT_SECONDS


class GenerateViewModel(QObject):
    """
    Лёгкий ViewModel страницы генерации.
    """

    formChanged = pyqtSignal(object)
    resultChanged = pyqtSignal(object)
    statusChanged = pyqtSignal(str)
    errorChanged = pyqtSignal(str)

    def __init__(self, schedule_repo=None):
        super().__init__()
        self._schedule_repo = schedule_repo

        self._form = GenerateFormState()
        self._last_result: Optional[GenerationResultDTO] = None
        self._last_error: str = ""
        self._is_running: bool = False

    # ---------------------------------------------------------
    # Properties
    # ---------------------------------------------------------
    @property
    def form(self) -> GenerateFormState:
        return self._form

    @property
    def last_result(self) -> Optional[GenerationResultDTO]:
        return self._last_result

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def is_running(self) -> bool:
        return self._is_running

    # ---------------------------------------------------------
    # Form state
    # ---------------------------------------------------------
    def set_calendar_id(self, calendar_id: Optional[int]) -> None:
        self._form = GenerateFormState(
            calendar_id=int(calendar_id) if calendar_id is not None else None,
        ).normalized()
        self.formChanged.emit(self._form)

    def set_form(
        self,
        *,
        calendar_id: Optional[int] = None,
    ) -> None:
        self._form = GenerateFormState(
            calendar_id=(
                int(calendar_id)
                if calendar_id is not None
                else self._form.calendar_id
            ),
        ).normalized()
        self.formChanged.emit(self._form)

    # ---------------------------------------------------------
    # Validation / UI helpers
    # ---------------------------------------------------------
    def validate_form(self) -> bool:
        form = self._form.normalized()

        if form.calendar_id is None or int(form.calendar_id) <= 0:
            self._set_error("Нужно выбрать календарь.")
            return False

        self._clear_error()
        return True

    def export_worker_args(self) -> Optional[list[str]]:
        """
        Возвращает аргументы для worker-процесса в согласованном формате:
        <calendar_id> <variants_count> <time_limit_seconds>

        variants_count и time_limit_seconds фиксированы внутри VM.
        """
        if not self.validate_form():
            return None

        form = self._form.normalized()
        return [
            str(int(form.calendar_id)),
            str(int(form.variants_count)),
            str(int(form.time_limit_seconds)),
        ]

    # ---------------------------------------------------------
    # Worker lifecycle integration
    # ---------------------------------------------------------
    def mark_started(self) -> None:
        self._is_running = True
        self._clear_error()
        self.statusChanged.emit("Генерация запущена…")

    def mark_progress(self, stage: str, payload: Optional[dict] = None) -> None:
        payload = payload or {}
        if payload:
            compact = ", ".join(f"{k}={v}" for k, v in payload.items())
            self.statusChanged.emit(f"{stage}: {compact}")
        else:
            self.statusChanged.emit(stage)

    def mark_finished(self, result: Optional[GenerationResultDTO]) -> None:
        self._is_running = False
        self._last_result = result
        self._clear_error()

        if result is None:
            self.statusChanged.emit("Генерация завершена.")
            self.resultChanged.emit(GenerationResultDTO())
            return

        self.statusChanged.emit(
            f"Генерация завершена. Вариантов: {int(result.variants_count)}"
        )
        self.resultChanged.emit(result)

    def mark_failed(self, message: str) -> None:
        self._is_running = False
        self._set_error(message)

    # ---------------------------------------------------------
    # Data helpers
    # ---------------------------------------------------------
    def load_variant(self, variant_id: int) -> Optional[ScheduleVariantDTO]:
        if self._schedule_repo is None:
            self._set_error("Репозиторий вариантов расписания не подключён.")
            return None

        try:
            dto = self._schedule_repo.get_variant_dto(int(variant_id))
        except Exception as exc:
            self._set_error(f"Не удалось загрузить вариант id={int(variant_id)}: {exc}")
            return None

        self._clear_error()
        return dto

    def load_variants(self, calendar_id: Optional[int] = None) -> list[ScheduleVariantDTO]:
        if self._schedule_repo is None:
            self._set_error("Репозиторий вариантов расписания не подключён.")
            return []

        try:
            variants = self._schedule_repo.list_variants(
                calendar_id=int(calendar_id) if calendar_id is not None else None
            )
            result: list[ScheduleVariantDTO] = []
            for variant in variants:
                variant_id = int(getattr(variant, "id_variant", 0) or 0)
                if variant_id <= 0:
                    continue
                try:
                    result.append(self._schedule_repo.get_variant_dto(variant_id))
                except Exception:
                    continue
        except Exception as exc:
            self._set_error(f"Не удалось загрузить список вариантов: {exc}")
            return []

        self._clear_error()
        return result

    # ---------------------------------------------------------
    # Internal
    # ---------------------------------------------------------
    def _set_error(self, message: str) -> None:
        self._last_error = str(message or "")
        self.errorChanged.emit(self._last_error)
        self.statusChanged.emit("")

    def _clear_error(self) -> None:
        self._last_error = ""
        self.errorChanged.emit("")