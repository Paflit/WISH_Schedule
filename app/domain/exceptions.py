"""
Доменные исключения.

Используются в application/use-cases и domain-логике.
GUI может перехватывать их и показывать пользователю понятное сообщение.
"""


class DomainError(Exception):
    """
    Базовое доменное исключение.
    Все остальные наследуются от него.
    """
    pass


class ValidationError(DomainError):
    """
    Ошибка валидации данных:
    - конфликт расписания
    - неверный статус
    - некорректный ввод
    """
    pass


class NotFoundError(DomainError):
    """
    Объект не найден:
    - вариант расписания
    - календарь
    - запись
    """
    pass


class BusinessRuleViolation(DomainError):
    """
    Нарушение бизнес-правила:
    - превышена нагрузка
    - недопустимый переход статуса
    - нарушение регламента
    """
    pass


class SolverError(DomainError):
    """
    Ошибка при построении модели/решении:
    - нет допустимого решения
    - несовместимые ограничения
    """
    pass


class SolverInfeasibleError(SolverError):
    """Solver не нашёл решение, но вернул диагностические данные."""

    def __init__(self, message: str, diagnostics: dict | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}
