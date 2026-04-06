from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from app.domain.exceptions import ValidationError
from app.domain.schedule_validation import GroupScheduleLimits


@dataclass
class FeasibilityIssue:
    severity: str  # "critical", "warning"
    category: str  # "load_rate", "teacher_coverage", "room_coverage", etc.
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class FeasibilityReport:
    is_feasible: bool
    critical_issues: list[FeasibilityIssue] = field(default_factory=list)
    warnings: list[FeasibilityIssue] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


class ValidateFeasibilityUseCase:
    """
    Проверка реализуемости расписания перед генерацией.
    
    Выполняет диагностику:
    - LoadRate для каждой группы
    - TeacherCoverage для каждой (subject, part_type)
    - RoomCoverage для каждой (subject, part_type)
    - TeacherDeficit по (subject, part_type)
    - RoomDeficit по типу аудитории
    - Bottleneck (минимальная доступность)
    - Loss (потери часов)
    """

    def __init__(
        self,
        calendar_repo,
        curriculum_repo,
        groups_repo,
        subjects_repo,
        teachers_repo,
        rooms_repo,
        event_builder=None,
        config=None,
        rules=None,
    ):
        self._calendar_repo = calendar_repo
        self._curriculum_repo = curriculum_repo
        self._groups_repo = groups_repo
        self._subjects_repo = subjects_repo
        self._teachers_repo = teachers_repo
        self._rooms_repo = rooms_repo
        self._event_builder = event_builder
        self._config = config
        self._rules = rules

    def execute(self, calendar_id: int) -> FeasibilityReport:
        if calendar_id <= 0:
            raise ValidationError("calendar_id должен быть положительным числом.")

        report = FeasibilityReport(is_feasible=True)

        try:
            # Загружаем данные
            calendar = self._calendar_repo.get_calendar(calendar_id)
            if not calendar:
                report.is_feasible = False
                report.critical_issues.append(
                    FeasibilityIssue(
                        severity="critical",
                        category="calendar",
                        message=f"Календарь с id={calendar_id} не найден.",
                    )
                )
                return report

            groups = self._groups_repo.list_all()
            subjects = self._subjects_repo.list_all()
            teachers = self._teachers_repo.list_all()
            rooms = self._rooms_repo.list_all()

            # Загружаем учебный план
            semester_plans = [
                p
                for p in self._curriculum_repo.get_semester_plans(calendar_id)
                if int(getattr(p, "hours_in_semester", 0) or 0) > 0
            ]
            curriculum_map = self._curriculum_repo.get_curriculum_items_for_plans(semester_plans)

            curriculum_items = []
            hours_by_curriculum_id = {
                int(getattr(plan, "curriculum_id", 0) or 0): int(
                    getattr(plan, "hours_in_semester", 0) or 0
                )
                for plan in semester_plans
            }

            subject_names_by_id = {
                int(getattr(subject, "id_subject", 0) or 0): str(
                    getattr(subject, "subject_name", "") or ""
                )
                for subject in subjects
            }

            for curriculum_id, item in curriculum_map.items():
                subject_id = int(getattr(item, "subject_id", 0) or 0)
                curriculum_items.append(
                    {
                        "id_curriculum": int(curriculum_id),
                        "group_id": int(getattr(item, "group_id", 0) or 0),
                        "subject_id": subject_id,
                        "subject_name": subject_names_by_id.get(subject_id, f"ID={subject_id}"),
                        "part_type": str(getattr(item, "part_type", "") or ""),
                        "required_room_type": str(getattr(item, "required_room_type", "") or ""),
                        "hours_in_semester": int(hours_by_curriculum_id.get(int(curriculum_id), 0) or 0),
                    }
                )

            if not curriculum_items:
                report.warnings.append(
                    FeasibilityIssue(
                        severity="warning",
                        category="curriculum",
                        message="Учебный план пуст. Нечего генерировать.",
                    )
                )
                return report

            # Загружаем слоты
            slots = self._calendar_repo.list_time_slots(calendar_id)
            template_slots = self._canonical_template_slots(slots)
            slots_by_week_type = defaultdict(int)
            for slot in template_slots:
                wt = int(getattr(slot, "week_type", 0) or 0)
                if wt > 0:
                    slots_by_week_type[wt] += 1
            total_slots = len(template_slots)
            teacher_part_matrix = self._teachers_repo.get_teacher_part_matrix()
            teacher_availability = self._teachers_repo.get_availability_matrix(calendar_id)

            events = []
            if self._event_builder is not None and self._config is not None:
                events = list(
                    self._event_builder.build_events(
                        calendar_id=int(calendar_id),
                        hours_per_pair=int(getattr(self._config, "hours_per_pair", 2) or 2),
                        locks=[],
                    )
                    or []
                )

            if total_slots == 0:
                report.is_feasible = False
                report.critical_issues.append(
                    FeasibilityIssue(
                        severity="critical",
                        category="slots",
                        message="Нет доступных временных слотов.",
                    )
                )
                return report

            # Выполняем проверки
            self._check_load_rate(report, curriculum_items, groups, total_slots, events, slots_by_week_type)
            self._check_group_rule_consistency(report, groups, events, slots_by_week_type)
            self._check_teacher_coverage(report, curriculum_items, teachers, teacher_part_matrix)
            self._check_room_coverage(report, curriculum_items, rooms)
            self._check_teacher_deficit(report, curriculum_items, teachers, total_slots, teacher_part_matrix, events)
            self._check_room_deficit(report, curriculum_items, rooms, total_slots, events)
            self._check_bottlenecks(
                report,
                curriculum_items,
                teachers,
                rooms,
                total_slots,
                teacher_part_matrix,
                teacher_availability,
                template_slots,
                events,
            )
            self._check_loss(report, curriculum_items, total_slots, events)

            # Формируем рекомендации
            self._generate_recommendations(report)

        except Exception as exc:
            report.is_feasible = False
            report.critical_issues.append(
                FeasibilityIssue(
                    severity="critical",
                    category="error",
                    message=f"Ошибка при проверке реализуемости: {exc}",
                )
            )

        return report

    def _check_load_rate(
        self,
        report: FeasibilityReport,
        curriculum_items: list,
        groups: list,
        total_slots: int,
        events: list,
        slots_by_week_type: dict,
    ) -> None:
        """
        Проверка LoadRate для каждой группы.
        LoadRate = (требуемые пары) / (доступные шаблонные слоты)
        """
        group_pairs = defaultdict(int)
        if events:
            for event in events:
                week_type = int(getattr(event, "fixed_week_type", 0) or 0)
                for group_id in list(getattr(event, "group_ids", []) or [getattr(event, "group_id", 0)]):
                    gid = int(group_id or 0)
                    if gid <= 0:
                        continue
                    group_pairs[(gid, week_type)] += 1
        else:
            hours_per_pair = int(getattr(self._config, "hours_per_pair", 2) or 2) if self._config is not None else 2
            for item in curriculum_items:
                group_id = item.get("group_id")
                hours = int(item.get("hours_in_semester", 0) or 0)
                group_pairs[(group_id, 0)] += max(0, hours // max(1, hours_per_pair))

        for group in groups:
            group_id = group.id_group
            group_loads = [
                (week_type, required_pairs)
                for (gid, week_type), required_pairs in group_pairs.items()
                if int(gid) == int(group_id) and int(required_pairs) > 0
            ]
            for week_type, required_pairs in group_loads:
                capacity = int(slots_by_week_type.get(int(week_type), total_slots) or total_slots or 1)
                load_rate = required_pairs / capacity if capacity > 0 else float("inf")

                if load_rate > 0.9:
                    report.critical_issues.append(
                        FeasibilityIssue(
                            severity="critical",
                            category="load_rate",
                            message=f"Группа '{group.group_name}', неделя {week_type}: перегрузка {load_rate:.1%}",
                            details={
                                "group_id": group_id,
                                "group_name": group.group_name,
                                "week_type": week_type,
                                "required_pairs": required_pairs,
                                "total_slots": capacity,
                                "load_rate": load_rate,
                            },
                        )
                    )
                    report.is_feasible = False
                elif load_rate > 0.7:
                    report.warnings.append(
                        FeasibilityIssue(
                            severity="warning",
                            category="load_rate",
                            message=f"Группа '{group.group_name}', неделя {week_type}: высокая загрузка {load_rate:.1%}",
                            details={
                                "group_id": group_id,
                                "group_name": group.group_name,
                                "week_type": week_type,
                                "required_pairs": required_pairs,
                                "total_slots": capacity,
                                "load_rate": load_rate,
                            },
                        )
                    )

    def _required_event_counts(self, curriculum_items: list, events: list) -> dict:
        if events:
            required_pairs = defaultdict(int)
            for event in events:
                subject_id = int(getattr(event, "subject_id", 0) or 0)
                part_type = str(getattr(event, "part_type", "") or "")
                required_pairs[(subject_id, part_type)] += 1
            return required_pairs

        hours_per_pair = int(getattr(self._config, "hours_per_pair", 2) or 2) if self._config is not None else 2
        required_pairs = defaultdict(int)
        for item in curriculum_items:
            subject_id = item.get("subject_id")
            part_type = item.get("part_type")
            hours = int(item.get("hours_in_semester", 0) or 0)
            required_pairs[(subject_id, part_type)] += max(0, hours // max(1, hours_per_pair))
        return required_pairs

    def _check_group_rule_consistency(
        self,
        report: FeasibilityReport,
        groups: list,
        events: list,
        slots_by_week_type: dict,
    ) -> None:
        if not events:
            return

        limits = GroupScheduleLimits.from_rules(self._rules)
        group_pairs = defaultdict(int)
        for event in events:
            week_type = int(getattr(event, "fixed_week_type", 0) or 0)
            for group_id in list(getattr(event, "group_ids", []) or [getattr(event, "group_id", 0)]):
                gid = int(group_id or 0)
                if gid > 0:
                    group_pairs[(gid, week_type)] += 1

        groups_by_id = {int(getattr(group, "id_group", 0) or 0): group for group in groups}
        max_pairs_per_week = int(limits.max_pairs_per_day) * int(limits.max_active_days_per_week)

        for (group_id, week_type), required_pairs in sorted(group_pairs.items()):
            if required_pairs <= 0:
                continue
            group = groups_by_id.get(int(group_id))
            group_name = str(getattr(group, "group_name", f"id={group_id}") or f"id={group_id}")
            if required_pairs < int(limits.min_pairs_per_day):
                report.warnings.append(
                    FeasibilityIssue(
                        severity="warning",
                        category="group_rule_bounds",
                        message=(
                            f"Группа '{group_name}', неделя {week_type}: {required_pairs} пар. "
                            f"Это ниже минимальной дневной нагрузки {int(limits.min_pairs_per_day)}."
                        ),
                    )
                )
            if required_pairs > max_pairs_per_week:
                report.critical_issues.append(
                    FeasibilityIssue(
                        severity="critical",
                        category="group_rule_bounds",
                        message=(
                            f"Группа '{group_name}', неделя {week_type}: {required_pairs} пар. "
                            f"Это выше предела {max_pairs_per_week} пар при текущих правилах."
                        ),
                    )
                )
                report.is_feasible = False

            capacity = int(slots_by_week_type.get(int(week_type), 0) or 0)
            if capacity and required_pairs > capacity:
                report.critical_issues.append(
                    FeasibilityIssue(
                        severity="critical",
                        category="group_rule_bounds",
                        message=(
                            f"Группа '{group_name}', неделя {week_type}: требуется {required_pairs} пар, "
                            f"доступно только {capacity} шаблонных слотов."
                        ),
                    )
                )
                report.is_feasible = False

    @staticmethod
    def _canonical_template_slots(slots: list) -> list:
        seen = set()
        result = []
        for slot in sorted(
            slots,
            key=lambda s: (
                int(getattr(s, "week_number_in_semester", 0) or 0),
                int(getattr(s, "week_type", 0) or 0),
                int(getattr(s, "day_of_week", 0) or 0),
                int(getattr(s, "pair_number", 0) or 0),
                int(getattr(s, "id_slot", 0) or 0),
            ),
        ):
            if bool(getattr(slot, "is_lunch_break", False)):
                continue
            key = (
                int(getattr(slot, "week_type", 0) or 0),
                int(getattr(slot, "day_of_week", 0) or 0),
                int(getattr(slot, "pair_number", 0) or 0),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(slot)
        return result

    def _check_teacher_coverage(
        self,
        report: FeasibilityReport,
        curriculum_items: list,
        teachers: list,
        teacher_part_matrix: dict,
    ) -> None:
        # Собираем требования
        required = defaultdict(set)
        for item in curriculum_items:
            subject_id = item.get("subject_id")
            part_type = item.get("part_type")
            key = (subject_id, part_type)
            required[key].add(item.get("subject_name", ""))

        # Собираем доступных преподавателей
        teacher_capabilities = defaultdict(set)
        for (teacher_id, subject_id, part_type), allowed in teacher_part_matrix.items():
            if allowed:
                teacher_capabilities[(subject_id, part_type)].add(int(teacher_id))

        # Проверяем покрытие
        for key, subject_names in required.items():
            subject_id, part_type = key
            available_teachers = teacher_capabilities.get(key, set())

            if not available_teachers:
                subject_name = list(subject_names)[0] if subject_names else f"ID={subject_id}"
                report.critical_issues.append(
                    FeasibilityIssue(
                        severity="critical",
                        category="teacher_coverage",
                        message=f"Нет преподавателей для '{subject_name}' ({part_type})",
                        details={
                            "subject_id": subject_id,
                            "subject_name": subject_name,
                            "part_type": part_type,
                        },
                    )
                )
                report.is_feasible = False

    def _check_room_coverage(
        self,
        report: FeasibilityReport,
        curriculum_items: list,
        rooms: list,
    ) -> None:
        required_room_types = set()
        for item in curriculum_items:
            room_type = item.get("required_room_type")
            if room_type:
                required_room_types.add(room_type)

        # Собираем доступные типы аудиторий
        available_room_types = defaultdict(int)
        for room in rooms:
            room_types = getattr(room, "room_types", None)
            if room_types:
                for rt in room_types:
                    available_room_types[rt.lower()] += 1
            else:
                rt = getattr(room, "room_type", "")
                if rt:
                    available_room_types[rt.lower()] += 1

        # Проверяем покрытие
        for room_type in required_room_types:
            count = available_room_types.get(room_type.lower(), 0)
            if count == 0:
                report.critical_issues.append(
                    FeasibilityIssue(
                        severity="critical",
                        category="room_coverage",
                        message=f"Нет аудиторий типа '{room_type}'",
                        details={"room_type": room_type},
                    )
                )
                report.is_feasible = False
            elif count < 2:
                report.warnings.append(
                    FeasibilityIssue(
                        severity="warning",
                        category="room_coverage",
                        message=f"Мало аудиторий типа '{room_type}' (всего {count})",
                        details={"room_type": room_type, "count": count},
                    )
                )

    def _check_teacher_deficit(
        self,
        report: FeasibilityReport,
        curriculum_items: list,
        teachers: list,
        total_slots: int,
        teacher_part_matrix: dict,
        events: list,
    ) -> None:
        required_pairs = self._required_event_counts(curriculum_items, events)

        # Собираем доступность преподавателей
        teacher_capacity = defaultdict(int)
        for (teacher_id, subject_id, part_type), allowed in teacher_part_matrix.items():
            if allowed:
                key = (subject_id, part_type)
                # Предполагаем, что преподаватель может вести до 50% слотов
                teacher_capacity[key] += int(total_slots * 0.5)

        # Проверяем дефицит
        for key, pairs_count in required_pairs.items():
            capacity = teacher_capacity.get(key, 0)
            if capacity < pairs_count:
                subject_id, part_type = key
                deficit = pairs_count - capacity
                report.warnings.append(
                    FeasibilityIssue(
                        severity="warning",
                        category="teacher_deficit",
                        message=f"Дефицит преподавателей для subject_id={subject_id} ({part_type}): {deficit} пар",
                        details={
                            "subject_id": subject_id,
                            "part_type": part_type,
                            "required_pairs": pairs_count,
                            "capacity": capacity,
                            "deficit": deficit,
                        },
                    )
                )

    def _check_room_deficit(
        self,
        report: FeasibilityReport,
        curriculum_items: list,
        rooms: list,
        total_slots: int,
        events: list,
    ) -> None:
        required_pairs = defaultdict(int)
        source_items = events if events else curriculum_items
        for item in source_items:
            room_type = item.get("required_room_type", "") if isinstance(item, dict) else ""
            if not room_type:
                room_type = str(getattr(item, "required_room_type", "") or "")
            if room_type:
                required_pairs[room_type.lower()] += 1

        # Собираем доступность аудиторий
        room_capacity = defaultdict(int)
        for room in rooms:
            room_types = getattr(room, "room_types", None)
            if room_types:
                for rt in room_types:
                    room_capacity[rt.lower()] += total_slots
            else:
                rt = getattr(room, "room_type", "")
                if rt:
                    room_capacity[rt.lower()] += total_slots

        # Проверяем дефицит
        for room_type, pairs_count in required_pairs.items():
            capacity = room_capacity.get(room_type, 0)
            if capacity < pairs_count:
                deficit = pairs_count - capacity
                report.critical_issues.append(
                    FeasibilityIssue(
                        severity="critical",
                        category="room_deficit",
                        message=f"Дефицит аудиторий типа '{room_type}': {deficit} пар",
                        details={
                            "room_type": room_type,
                            "required_pairs": pairs_count,
                            "capacity": capacity,
                            "deficit": deficit,
                        },
                    )
                )
                report.is_feasible = False

    def _check_bottlenecks(
        self,
        report: FeasibilityReport,
        curriculum_items: list,
        teachers: list,
        rooms: list,
        total_slots: int,
        teacher_part_matrix: dict,
        teacher_availability: dict,
        slots: list,
        events: list,
    ) -> None:
        # Находим минимальную доступность по событиям
        min_availability = float("inf")
        bottleneck_event = None

        source_items = events if events else curriculum_items
        for item in source_items:
            subject_id = int(getattr(item, "subject_id", 0) or 0) if not isinstance(item, dict) else item.get("subject_id")
            part_type = str(getattr(item, "part_type", "") or "") if not isinstance(item, dict) else item.get("part_type")
            room_type = str(getattr(item, "required_room_type", "") or "") if not isinstance(item, dict) else item.get("required_room_type", "")

            # Считаем доступных преподавателей
            teacher_ids = {
                int(teacher_id)
                for (teacher_id, sid, pt), allowed in teacher_part_matrix.items()
                if allowed and int(sid) == int(subject_id) and str(pt) == str(part_type)
            }
            teacher_count = len(teacher_ids)

            available_teacher_slots = 0
            if teacher_ids and slots:
                for teacher_id in teacher_ids:
                    for slot in slots:
                        slot_id = int(getattr(slot, "id_slot", 0) or 0)
                        if teacher_availability.get((teacher_id, slot_id), True):
                            available_teacher_slots += 1

            # Считаем доступные аудитории
            room_count = 0
            for room in rooms:
                room_types = getattr(room, "room_types", None)
                if room_types:
                    if room_type.lower() in [rt.lower() for rt in room_types]:
                        room_count += 1
                else:
                    rt = getattr(room, "room_type", "")
                    if rt.lower() == room_type.lower():
                        room_count += 1

            teacher_availability_score = available_teacher_slots if available_teacher_slots > 0 else 0
            availability = min(
                teacher_count if teacher_count > 0 else 0,
                room_count if room_count > 0 else 0,
                teacher_availability_score if teacher_count > 0 else 0,
                total_slots,
            )

            if availability < min_availability:
                min_availability = availability
                bottleneck_event = item

        if min_availability < 5:
            if isinstance(bottleneck_event, dict):
                subject_name = bottleneck_event.get("subject_name", "") if bottleneck_event else ""
                part_type = bottleneck_event.get("part_type", "") if bottleneck_event else ""
            else:
                subject_name = str(getattr(bottleneck_event, "subject_name", "") or "") if bottleneck_event else ""
                part_type = str(getattr(bottleneck_event, "part_type", "") or "") if bottleneck_event else ""
            report.warnings.append(
                FeasibilityIssue(
                    severity="warning",
                    category="bottleneck",
                    message=f"Узкое место: '{subject_name}' ({part_type}) - доступность {min_availability}",
                    details={
                        "subject_name": subject_name,
                        "part_type": part_type,
                        "availability": min_availability,
                    },
                )
            )

        report.metrics["min_availability"] = min_availability

    def _check_loss(
        self,
        report: FeasibilityReport,
        curriculum_items: list,
        total_slots: int,
        events: list,
    ) -> None:
        if events:
            total_required = len(events)
            report.metrics["total_required_pairs"] = total_required
        else:
            hours_per_pair = int(getattr(self._config, "hours_per_pair", 2) or 2) if self._config is not None else 2
            total_required = sum(max(0, int(item.get("hours_in_semester", 0) or 0) // max(1, hours_per_pair)) for item in curriculum_items)
            report.metrics["total_required_pairs"] = total_required

        report.metrics["total_slots"] = total_slots
        report.metrics["utilization"] = (total_required / total_slots) if total_slots > 0 else 0

    def _generate_recommendations(self, report: FeasibilityReport) -> None:
        if not report.is_feasible:
            report.recommendations.append(
                "Расписание не может быть сгенерировано. Необходимо устранить критические проблемы."
            )

        # Рекомендации по категориям
        categories = defaultdict(int)
        for issue in report.critical_issues + report.warnings:
            categories[issue.category] += 1

        if categories.get("load_rate", 0) > 0:
            report.recommendations.append(
                "Уменьшите нагрузку на перегруженные группы или увеличьте количество слотов."
            )

        if categories.get("teacher_coverage", 0) > 0:
            report.recommendations.append(
                "Добавьте преподавателей для дисциплин без покрытия или назначьте существующим."
            )

        if categories.get("room_coverage", 0) > 0:
            report.recommendations.append(
                "Добавьте аудитории требуемых типов или измените типы существующих."
            )

        if categories.get("teacher_deficit", 0) > 0:
            report.recommendations.append(
                "Увеличьте количество преподавателей или распределите нагрузку."
            )

        if categories.get("room_deficit", 0) > 0:
            report.recommendations.append(
                "Увеличьте количество аудиторий или уменьшите часы в учебном плане."
            )

        if report.metrics.get("utilization", 0) and report.metrics.get("utilization", 0) > 1.5:
            report.recommendations.append(
                "Общая учебная нагрузка высокая. Проверьте баланс часов по группам, преподавателям и аудиториям."
            )
