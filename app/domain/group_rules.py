from __future__ import annotations

import re


def is_master_group_name(group_name: str) -> bool:
    """
    Магистерские группы кодируются второй цифрой после дефиса.

    Пример: ШИН-171 -> цифры после дефиса "171", вторая цифра "7".
    """
    match = re.search(r"-\s*(\d+)", str(group_name or ""))
    if not match:
        return False
    digits = match.group(1)
    return len(digits) >= 2 and digits[1] == "7"


def is_master_group(group) -> bool:
    return is_master_group_name(str(getattr(group, "group_name", "") or ""))


def min_pairs_per_active_day_for_group(group, default: int = 2) -> int:
    """
    В расписании РУТ группы с кодом уровня/формы `-x7x` фактически учатся
    в вечернем/магистерском режиме: встречаются активные дни с одной парой.
    Для обычных очных групп сохраняем базовое требование не менее 2 пар.
    """
    if is_master_group(group):
        return 1
    return max(1, int(default))


def is_master_slot(slot, max_pair: int) -> bool:
    day = int(getattr(slot, "day_of_week", 0) or 0)
    pair = int(getattr(slot, "pair_number", 0) or 0)
    late_pairs = {max(1, int(max_pair) - 1), int(max_pair)}
    saturday_pairs = {max(1, int(max_pair) - 4), max(1, int(max_pair) - 3), max(1, int(max_pair) - 2), *late_pairs}
    if 1 <= day <= 5:
        return pair in late_pairs
    if day == 6:
        return pair in saturday_pairs
    return False


def master_slot_penalty(slot, max_pair: int) -> int:
    day = int(getattr(slot, "day_of_week", 0) or 0)
    pair = int(getattr(slot, "pair_number", 0) or 0)
    late_pairs = {max(1, int(max_pair) - 1), int(max_pair)}
    if 1 <= day <= 5 and pair in late_pairs:
        return 0
    if day == 6 and pair in late_pairs:
        return 250
    if day == 6:
        return 500
    return 2000
