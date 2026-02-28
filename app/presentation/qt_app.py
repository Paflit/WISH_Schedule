# app/presentation/qt_app.py
"""
Entry point для запуска Qt-приложения.

Задачи:
- создать QApplication
- собрать DI-контейнер
- создать MainWindow
- обработать глобальные исключения

Запуск:
    python main.py
или:
    python -m app.presentation.qt_app
"""

import sys
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.di import build_container
from app.presentation.main_window import MainWindow
from app.domain.exceptions import DomainError


def run():
    app = QApplication(sys.argv)

    # -----------------------------
    # DI container
    # -----------------------------
    container = build_container()

    # -----------------------------
    # Main window
    # -----------------------------
    window = MainWindow(container)
    window.show()

    # -----------------------------
    # Global exception hook
    # -----------------------------
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

        if issubclass(exc_type, DomainError):
            QMessageBox.warning(window, "Ошибка бизнес-логики", str(exc_value))
        else:
            QMessageBox.critical(window, "Системная ошибка", message)

    sys.excepthook = handle_exception

    sys.exit(app.exec())


if __name__ == "__main__":
    run()