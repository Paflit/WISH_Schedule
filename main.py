from app.presentation.qt_app import run
from app.di import build_container
from app.presentation.create_shortcut_win import create_desktop_shortcut

def main():
    container = build_container()
    create_desktop_shortcut("PracticWISH")
    run(container)

if __name__ == "__main__":
    main()