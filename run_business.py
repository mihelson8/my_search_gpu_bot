"""Reliable launcher for CCTV Business Suite on Windows."""
from __future__ import annotations

import sys
import traceback


def main() -> int:
    print("============================================================")
    print("  CCTV & China Cargo Business Suite")
    print("  Пульт видеонаблюдения / бизнес")
    print("============================================================")
    print(f"Папка: {sys.path[0] or '.'}")
    print("Сейчас откроется браузер: http://localhost:8765")
    print("Это окно не закрывайте, пока работаете в программе.")
    print("============================================================")
    try:
        from app_suite import start_server

        start_server(port=8765, open_browser=True)
        return 0
    except SystemExit as exc:
        code = int(exc.code) if isinstance(exc.code, int) else 1
        input("\nНажмите Enter, чтобы закрыть окно...")
        return code
    except Exception:
        print("\n[ОШИБКА] Программа не запустилась:\n")
        traceback.print_exc()
        print("\nЧастые причины:")
        print("  - антивирус блокирует Python")
        print("  - порт 8765 занят")
        print("  - повреждены файлы программы")
        input("\nНажмите Enter, чтобы закрыть окно...")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
