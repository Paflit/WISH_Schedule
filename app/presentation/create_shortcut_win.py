import os
import sys
from pathlib import Path

def create_desktop_shortcut(app_name: str = "PracticWISH"):
    # Работает только на Windows
    if os.name != "nt":
        return

    try:
        import winshell  # pip install winshell
        from win32com.client import Dispatch  # pip install pywin32
    except Exception:
        # Если зависимостей нет — просто пропускаем
        return

    exe_path = Path(sys.executable)  # в PyInstaller это путь к .exe
    desktop = Path(winshell.desktop())
    shortcut_path = desktop / f"{app_name}.lnk"

    if shortcut_path.exists():
        return

    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(shortcut_path))
    shortcut.Targetpath = str(exe_path)
    shortcut.WorkingDirectory = str(exe_path.parent)
    shortcut.IconLocation = str(exe_path)  # иконку можно заменить на .ico путь
    shortcut.save()