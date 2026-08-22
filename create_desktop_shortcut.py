"""Create Desktop shortcut for CCTV Business Suite (Windows)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def desktop_dir() -> Path:
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    for name in ("Desktop", "Рабочий стол", "OneDrive\\Desktop", "OneDrive\\Рабочий стол"):
        path = home / name
        if path.is_dir():
            return path
    public = Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"
    if public.is_dir():
        return public
    return home / "Desktop"


def main() -> int:
    if os.name != "nt":
        print("Shortcuts are only created on Windows.")
        return 1

    folder = Path(__file__).resolve().parent
    bat = folder / "START_APP_WINDOWS.bat"
    if not bat.is_file():
        print("START_APP_WINDOWS.bat not found:", bat)
        return 1

    ico = folder / "app_icon.ico"
    desk = desktop_dir()
    desk.mkdir(parents=True, exist_ok=True)
    link = desk / "Бизнес Видеонаблюдение.lnk"

    ico_line = (
        f'$s.IconLocation = "{ico},0"'
        if ico.is_file()
        else ""
    )
    ps = f"""
$w = New-Object -ComObject WScript.Shell
$s = $w.CreateShortcut("{link}")
$s.TargetPath = "{bat}"
$s.WorkingDirectory = "{folder}"
$s.WindowStyle = 1
$s.Description = "CCTV Business Suite"
{ico_line}
$s.Save()
Write-Output $s.FullName
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        print("Failed to create shortcut.")
        return 1

    print("OK: shortcut created")
    print(link)
    return 0


if __name__ == "__main__":
    code = main()
    if os.name == "nt":
        try:
            input("\nPress Enter...")
        except EOFError:
            pass
    raise SystemExit(code)
