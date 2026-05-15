import sys
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.di import build_container
from app.presentation.database_selector import choose_database_if_needed
from app.presentation.main_window import MainWindow
from app.domain.exceptions import DomainError


def run(container=None):
    app = QApplication(sys.argv)

    if container is None:
        choose_database_if_needed()

    # если контейнер не передали — соберём внутри
    if container is None:
        container = build_container()

    window = MainWindow(container)
    window.show()

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
