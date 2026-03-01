# app/presentation/viewmodels/base_vm.py
"""
BaseViewModel

Базовый класс для всех ViewModel.

Назначение:
- централизованная обработка ошибок
- сигнал обновления UI
- единый способ выполнения use-cases
- минимальная "реактивность" через Qt signals

Архитектура:
Page (QWidget) <-> ViewModel <-> UseCase

ViewModel:
- не содержит Qt-виджетов
- может использовать Qt signals
- не знает про SQLite напрямую
"""

from __future__ import annotations

from typing import Callable, Any

from PyQt6.QtCore import QObject, pyqtSignal

from app.domain.exceptions import DomainError


class BaseViewModel(QObject):
    """
    Базовый ViewModel.
    """

    # Сигналы
    loading_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)
    info_message = pyqtSignal(str)

    def __init__(self, container):
        super().__init__()
        self.container = container
        self._is_loading = False

    # ---------------------------------------------------------

    @property
    def is_loading(self) -> bool:
        return self._is_loading

    def _set_loading(self, value: bool):
        if self._is_loading != value:
            self._is_loading = value
            self.loading_changed.emit(value)

    # ---------------------------------------------------------

    def execute(self, func: Callable[[], Any]) -> Any:
        """
        Унифицированный вызов use-case или любой логики
        с автоматической обработкой ошибок.
        """

        try:
            self._set_loading(True)
            result = func()
            return result

        except DomainError as e:
            self.error_occurred.emit(str(e))

        except Exception as e:
            # системная ошибка
            self.error_occurred.emit(f"Системная ошибка: {str(e)}")

        finally:
            self._set_loading(False)

        return None

    # ---------------------------------------------------------

    def notify_info(self, message: str):
        self.info_message.emit(message)