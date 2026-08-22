"""Create Desktop shortcut: Hong Kong flag icon, no black console (pythonw)."""
from __future__ import annotations

import os
import shutil
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


def find_pythonw() -> str | None:
    for name in ("pythonw.exe", "pythonw"):
        found = shutil.which(name)
        if found:
            return found
    for name in ("python.exe", "python", "py"):
        found = shutil.which(name)
        if not found:
            continue
        parent = Path(found).resolve().parent
        candidate = parent / "pythonw.exe"
        if candidate.is_file():
            return str(candidate)
        # py launcher often lives elsewhere; try common install paths nearby
    # py -0p can list installs; keep it simple:
    try:
        out = subprocess.check_output(
            ["py", "-3", "-c", "import sys; print(sys.executable)"],
            text=True,
            encoding="utf-8",
            errors="replace",
        ).strip()
        if out:
            candidate = Path(out).with_name("pythonw.exe")
            if candidate.is_file():
                return str(candidate)
    except (OSError, subprocess.CalledProcessError):
        pass
    return None


def shortcut_name() -> str:
    # "Бизнес Видеонаблюдение.lnk" without embedding Cyrillic in source files that break cmd
    return (
        "\u0411\u0438\u0437\u043d\u0435\u0441 \u0412\u0438\u0434\u0435\u043e"
        "\u043d\u0430\u0431\u043b\u044e\u0434\u0435\u043d\u0438\u0435.lnk"
    )


def main() -> int:
    if os.name != "nt":
        print("Windows only.")
        return 1

    folder = Path(__file__).resolve().parent
    script = folder / "app_suite.py"
    if not script.is_file():
        print("app_suite.py not found:", script)
        return 1

    ico = folder / "app_icon.ico"
    pyw = find_pythonw()
    if not pyw:
        print("pythonw.exe not found. Install Python from python.org")
        return 1

    desk = desktop_dir()
    desk.mkdir(parents=True, exist_ok=True)
    link = desk / shortcut_name()

    # Also remove old broken shortcuts that pointed at .bat
    for old in (
        desk / "Business-CCTV.lnk",
        desk / "Business-CCTV.bat",
        desk / "START_APP_WINDOWS.bat - \u044f\u0440\u043b\u044b\u043a.lnk",
    ):
        try:
            if old.is_file():
                old.unlink()
        except OSError:
            pass

    ico_line = f'$s.IconLocation = "{ico},0"' if ico.is_file() else ""
    # Target pythonw directly → no black cmd window. Arguments = app_suite.py
    ps = f"""
$w = New-Object -ComObject WScript.Shell
$s = $w.CreateShortcut("{link}")
$s.TargetPath = "{pyw}"
$s.Arguments = "`"{script}`""
$s.WorkingDirectory = "{folder}"
$s.WindowStyle = 7
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

    print("OK: Hong Kong flag shortcut (no black window)")
    print(link)
    print("pythonw:", pyw)
    return 0


if __name__ == "__main__":
    code = main()
    if os.name == "nt":
        try:
            input("\nPress Enter...")
        except EOFError:
            pass
    raise SystemExit(code)
