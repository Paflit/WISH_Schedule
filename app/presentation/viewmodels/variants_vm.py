# app/presentation/viewmodels/variants_vm.py
"""
VariantsViewModel

ViewModel для страницы вариантов расписания.

Задачи:
- загрузить семестры (календарь)
- загрузить список вариантов по семестру
- утвердить/архивировать/переименовать вариант через SaveVariantUseCase

UI получает плоские dict-объекты для таблицы.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional

from app.presentation.viewmodels.base_vm import BaseViewModel
from app.application.use_cases.save_variant import SaveVariantCommand


@dataclass(frozen=True)
class VariantRow:
    id_variant: int
    name: str
    score: int
    status: str
    rule_profile_key: str


class VariantsViewModel(BaseViewModel):

    def __init__(self, container):
        super().__init__(container)

        self.calendar_repo = container.calendar_repo
        self.schedule_repo = container.schedule_repo
        self.save_variant_uc = container.save_variant_uc

    # ---------------------------------------------------------

    def load_calendars(self) -> List[Dict]:
        def _load():
            calendars = self.calendar_repo.list_all()
            return [
                {"id": c.id_calendar, "title": f"{c.academic_year} / Семестр {c.semester}"}
                for c in calendars
            ]

        return self.execute(_load) or []

    def load_variants(self, calendar_id: int) -> List[VariantRow]:
        def _load():
            variants = self.schedule_repo.list_variants(calendar_id=calendar_id)
            return [
                VariantRow(
                    id_variant=v["id_variant"],
                    name=v["name"],
                    score=v["objective_score"],
                    status=v["status"],
                    rule_profile_key=v["rule_profile_key"],
                )
                for v in variants
            ]

        return self.execute(_load) or []

    # ---------------------------------------------------------

    def set_status(self, variant_id: int, status: str) -> bool:
        def _run():
            cmd = SaveVariantCommand(variant_id=variant_id, status=status)
            self.save_variant_uc.execute(cmd)
            return True

        ok = bool(self.execute(_run) or False)
        if ok:
            self.notify_info(f"Статус обновлён: {status}")
        return ok

    def rename(self, variant_id: int, new_name: str) -> bool:
        def _run():
            cmd = SaveVariantCommand(variant_id=variant_id, name=new_name)
            self.save_variant_uc.execute(cmd)
            return True

        ok = bool(self.execute(_run) or False)
        if ok:
            self.notify_info("Название варианта обновлено")
        return ok