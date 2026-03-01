# app/presentation/viewmodels/generate_vm.py
"""
GenerateViewModel

ViewModel для экрана генерации расписания.

Задачи:
- загрузка списка семестров (календарей)
- предоставление списка профилей правил
- запуск генерации через GenerateScheduleUseCase
- преобразование результата в удобный для UI вид (список вариантов)

Page:
- берёт calendars/profiles из VM
- отображает loading/error/info
- по кнопке вызывает generate(...)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional

from app.presentation.viewmodels.base_vm import BaseViewModel
from app.application.use_cases.generate_schedule import GenerateScheduleCommand


@dataclass(frozen=True)
class VariantItem:
    id_variant: int
    name: str
    score: int


class GenerateViewModel(BaseViewModel):

    def __init__(self, container):
        super().__init__(container)

        self.calendar_repo = container.calendar_repo
        self.rule_profiles = container.rule_profiles
        self.generate_uc = container.generate_schedule_uc
        self.config = container.config

    # ---------------------------------------------------------

    def load_calendars(self) -> List[Dict]:
        """
        Для combo: [{id, title}]
        """
        def _load():
            calendars = self.calendar_repo.list_all()
            return [
                {"id": c.id_calendar, "title": f"{c.academic_year} / Семестр {c.semester}"}
                for c in calendars
            ]

        return self.execute(_load) or []

    def load_profiles(self) -> List[str]:
        return self.rule_profiles.list_keys()

    # ---------------------------------------------------------

    def generate(
        self,
        calendar_id: int,
        profile_key: str,
        variants_count: Optional[int] = None,
        time_limit_seconds: Optional[int] = None,
        random_seed: Optional[int] = None,
        respect_locks: bool = True,
        created_by: str = "admin",
    ) -> List[VariantItem]:
        """
        Запускает генерацию и возвращает список вариантов для UI.
        """
        def _run():
            cmd = GenerateScheduleCommand(
                calendar_id=calendar_id,
                rule_profile_key=profile_key,
                variants_count=variants_count or self.config.solver_variants_count,
                time_limit_seconds=time_limit_seconds or self.config.solver_time_limit_seconds,
                random_seed=random_seed or self.config.solver_random_seed,
                respect_locks=respect_locks,
                created_by=created_by,
            )
            res = self.generate_uc.execute(cmd)
            return [
                VariantItem(
                    id_variant=v.id_variant,
                    name=v.name,
                    score=v.objective_score,
                )
                for v in res.variants
            ]

        result = self.execute(_run) or []
        if result:
            self.notify_info(f"Сгенерировано вариантов: {len(result)}")
        return result