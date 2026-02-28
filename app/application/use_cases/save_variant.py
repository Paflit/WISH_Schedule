# app/application/use_cases/save_variant.py
"""
Use-case: сохранение/обновление метаданных варианта расписания.

Зачем нужен отдельный use-case:
- GUI может переименовать вариант, изменить статус ("approved"/"archived")
- можно сохранить комментарий или итоговую оценку после ручных правок
- use-case гарантирует корректный переход статусов и базовую валидацию
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.domain.exceptions import ValidationError


# ------------------------------------------------------------
# Команда сохранения
# ------------------------------------------------------------

@dataclass(frozen=True)
class SaveVariantCommand:
    variant_id: int

    name: Optional[str] = None
    status: Optional[str] = None  # "generated" | "edited" | "approved" | "archived"
    comment: Optional[str] = None

    # если после ручных правок пересчитали score — можно обновить
    objective_score: Optional[int] = None


# ------------------------------------------------------------
# Use-case
# ------------------------------------------------------------

class SaveVariantUseCase:
    ALLOWED_STATUSES = {"generated", "edited", "approved", "archived"}

    def __init__(self, schedule_repo):
        self._schedule_repo = schedule_repo

    def execute(self, command: SaveVariantCommand) -> None:
        variant = self._schedule_repo.get_variant(command.variant_id)
        if variant is None:
            raise ValidationError("Вариант расписания не найден.")

        if command.status is not None and command.status not in self.ALLOWED_STATUSES:
            raise ValidationError(f"Недопустимый статус: {command.status}")

        # Пример правил переходов статусов (можешь расширить):
        # generated -> edited/approved/archived
        # edited    -> approved/archived
        # approved  -> archived
        # archived  -> (нельзя менять)
        if variant.status == "archived":
            raise ValidationError("Архивный вариант нельзя изменять.")

        if command.status is not None:
            if not self._is_status_transition_allowed(variant.status, command.status):
                raise ValidationError(f"Нельзя изменить статус {variant.status} -> {command.status}")

        self._schedule_repo.update_variant(
            variant_id=command.variant_id,
            name=command.name,
            status=command.status,
            comment=command.comment,
            objective_score=command.objective_score,
        )

    def _is_status_transition_allowed(self, old: str, new: str) -> bool:
        allowed = {
            "generated": {"generated", "edited", "approved", "archived"},
            "edited": {"edited", "approved", "archived"},
            "approved": {"approved", "archived"},
        }
        return new in allowed.get(old, set())