# app/presentation/viewmodels/editor_vm.py
"""
EditorViewModel

ViewModel для экрана ручного редактирования расписания.

Задачи:
- загрузить список вариантов расписания (для combo)
- загрузить вариант и преобразовать в grid-структуру для UI
- применить ручную правку через ApplyManualEditUseCase
- перезагрузить данные после правки

Page (EditorPage) должен:
- подписаться на сигналы error/info/loading
- вызывать методы VM
- отображать grid
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from app.presentation.viewmodels.base_vm import BaseViewModel
from app.application.use_cases.apply_manual_edit import ApplyManualEditCommand


@dataclass(frozen=True)
class GridCell:
    """
    Представление ячейки сетки для UI.
    """
    text: str
    schedule_entry_id: Optional[int] = None
    locked: bool = False


class EditorViewModel(BaseViewModel):

    def __init__(self, container):
        super().__init__(container)

        self.schedule_repo = container.schedule_repo
        self.apply_edit_uc = container.apply_manual_edit_uc

    # ---------------------------------------------------------

    def load_variants(self, calendar_id: Optional[int] = None) -> List[Dict]:
        """
        Возвращает список вариантов для combo.
        """
        def _load():
            variants = self.schedule_repo.list_variants(calendar_id=calendar_id)
            return [
                {
                    "id": v["id_variant"],
                    "name": v["name"],
                    "score": v["objective_score"],
                    "status": v["status"],
                }
                for v in variants
            ]

        return self.execute(_load) or []

    # ---------------------------------------------------------

    def load_variant_grid(self, variant_id: int) -> Tuple[int, Dict[Tuple[int, int], GridCell]]:
        """
        Загружает вариант и строит grid:
        key = (day_of_week, pair_number)
        value = GridCell(text, schedule_entry_id)

        Возвращает:
            max_pair, grid_map
        """
        def _load():
            variant = self.schedule_repo.get_variant_dto(variant_id)

            grid: Dict[Tuple[int, int], List] = {}
            max_pair = 0

            for e in variant.entries:
                max_pair = max(max_pair, e.pair_number)

                key = (e.day_of_week, e.pair_number)
                text = f"{e.group_name}\n{e.subject_name}\n{e.teacher_name}\n{e.room_number}"

                # несколько записей в одной ячейке — сохраняем список
                grid.setdefault(key, []).append((e, text))

            grid_cells: Dict[Tuple[int, int], GridCell] = {}

            for key, items in grid.items():
                merged_text = "\n---\n".join([txt for (_, txt) in items])

                # берём первую запись как "основную" для редактирования
                first_entry = items[0][0]
                grid_cells[key] = GridCell(
                    text=merged_text,
                    schedule_entry_id=getattr(first_entry, "event_id", None),
                    locked=getattr(first_entry, "is_locked", False),
                )

            return max_pair, grid_cells

        result = self.execute(_load)
        if result is None:
            return 0, {}
        return result

    # ---------------------------------------------------------

    def apply_edit(
        self,
        variant_id: int,
        schedule_entry_id: int,
        new_slot_id: Optional[int] = None,
        new_teacher_id: Optional[int] = None,
        new_room_id: Optional[int] = None,
        lock_after_edit: bool = True,
        edited_by: str = "admin",
    ) -> bool:
        """
        Применяет ручное изменение.
        """
        def _apply():
            cmd = ApplyManualEditCommand(
                variant_id=variant_id,
                schedule_entry_id=schedule_entry_id,
                new_slot_id=new_slot_id,
                new_teacher_id=new_teacher_id,
                new_room_id=new_room_id,
                lock_after_edit=lock_after_edit,
                edited_by=edited_by,
            )
            self.apply_edit_uc.execute(cmd)
            return True

        return bool(self.execute(_apply) or False)