from app.presentation.qt_app import run
from app.di import build_container


def main() -> None:
    #container = build_container()
    run()


if __name__ == "__main__":
    main()