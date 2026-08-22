"""Desktop GUI: capture Seetong live view, OCR plates, own/foreign database."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from anpr.config import (
    OFFICIAL_SEETONG_SHOTS_DIR,
    load_config,
    save_config,
    sanitize_shots_dir,
    side_window_geometry,
)
from anpr.database import AnprDB
from anpr.plates import category_label, format_plate, format_plate_parts, is_osd_text, normalize_plate, parse_category, plate_is_valid
from anpr.version import APP_TITLE, APP_VERSION

STATUS_COLORS = {
    "own": "#16a34a",
    "foreign": "#dc2626",
    "unknown": "#ca8a04",
}
SOURCE_LABELS = {
    "seetong_folder": "Папка снимков Seetong",
    "http": "Камера по сети (снимок)",
    "rtsp": "Камера по сети (RTSP)",
    "seetong_window": "Скриншот окна Seetong",
    "file": "Файл / фото",
    "monitor": "Весь экран — не использовать",
}
SOURCE_VALUES = {label: key for key, label in SOURCE_LABELS.items()}


class AnprApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.minsize(720, 520)
        self.root.geometry(
            side_window_geometry(self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        )

        self.bg = "#0f172a"
        self.card = "#1e293b"
        self.text = "#f8fafc"
        self.muted = "#94a3b8"
        self.accent = "#38bdf8"
        self.root.configure(bg=self.bg)

        self.db = AnprDB()
        self.cfg = load_config()
        if self.cfg.get("source") not in ("http", "rtsp", "file"):
            self.cfg["source"] = "seetong_folder"
        self.cfg["shots_dir"] = sanitize_shots_dir(str(self.cfg.get("shots_dir") or OFFICIAL_SEETONG_SHOTS_DIR))
        self._running = False
        self._busy = False
        self._last_frame = None
        self._last_plate = ""
        self._last_category = "unknown"
        self._preview_photo = None
        self._zoom_photo = None
        self._status_after = None

        self._setup_styles()
        self._build()
        self.refresh_windows()
        self.refresh_vehicles()
        self.refresh_events()
        self._set_detection(
            "—",
            "unknown",
            "Seetong слева, это окно справа. Съёмка начнётся сама. Нужен номер вида «А 000 АА | 00».",
            0.0,
        )
        self.root.after(200, self._warn_missing_packages)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _warn_missing_packages(self) -> None:
        try:
            from anpr.capture import missing_capture_packages

            missing = missing_capture_packages()
        except Exception:
            missing = ["numpy", "Pillow", "mss"]
        if not missing:
            self.root.after(500, self.start_capture)
            return
        names = ", ".join(missing)
        text = (
            "Нет библиотек для скриншота: "
            + names
            + "\n\nВ командной строке выполните:\npython -m pip install -r requirements-anpr.txt\n\n"
            "Потом закройте это окно и снова запустите:\npython anpr_gui.py"
        )
        self.preview_label.config(text=text)
        messagebox.showwarning("Нужна установка пакетов", text)

    def _setup_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.bg)
        style.configure("Card.TFrame", background=self.card)
        style.configure("TLabel", background=self.bg, foreground=self.text, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.card, foreground=self.text, font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"), foreground=self.accent, background=self.bg)
        style.configure("Muted.TLabel", foreground=self.muted, background=self.bg)
        style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=6)
        style.configure("TNotebook", background=self.bg)
        style.configure("TNotebook.Tab", padding=(12, 6))
        style.configure("Treeview", font=("Segoe UI", 9), rowheight=26)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _build(self) -> None:
        header = ttk.Frame(self.root, padding="14 10")
        header.pack(fill="x")
        ttk.Label(header, text="Автономера · Seetong", style="Header.TLabel").pack(side="left")
        ttk.Label(header, text=f"v{APP_VERSION} · окно справа, камера слева", style="Muted.TLabel").pack(
            side="left", padx=(12, 0)
        )
        self.stats_label = ttk.Label(header, text="", style="Muted.TLabel")
        self.stats_label.pack(side="right")

        top = ttk.Frame(self.root, padding="14 0")
        top.pack(fill="x")
        self.btn_start = ttk.Button(top, text="▶ Старт", command=self.start_capture)
        self.btn_start.pack(side="left", padx=(0, 6))
        self.btn_stop = ttk.Button(top, text="■ Стоп", command=self.stop_capture, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 6))
        ttk.Button(top, text="Снимок сейчас", command=self.capture_once).pack(side="left", padx=(0, 8))
        ttk.Button(top, text="Камера / IP", command=self.open_camera_dialog).pack(side="left", padx=(0, 16))

        self.source_var = tk.StringVar(value=SOURCE_LABELS.get(self.cfg.get("source"), SOURCE_LABELS["seetong_folder"]))
        self.run_label = ttk.Label(top, text="запуск…", style="Muted.TLabel")
        self.run_label.pack(side="right")

        self.camera_ip_var = tk.StringVar(value=self.cfg.get("camera_ip", "192.168.0.123"))
        self.camera_user_var = tk.StringVar(value=self.cfg.get("camera_user", "admin"))
        self.camera_pass_var = tk.StringVar(value=self.cfg.get("camera_password", "123456"))
        self.device_id_var = tk.StringVar(value=self.cfg.get("device_id", "35918051"))

        body = ttk.Frame(self.root, padding="14 10")
        body.pack(fill="both", expand=True)

        preview_card = tk.Frame(body, bg=self.card, highlightthickness=0)
        preview_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ttk.Label(preview_card, text="Форма авто и рамка при обнаружении", style="Card.TLabel").pack(anchor="w", padx=12, pady=(10, 4))
        self.preview_label = tk.Label(
            preview_card,
            text="Откройте Seetong слева. Съёмка начнётся сама.",
            bg="#020617",
            fg=self.muted,
            font=("Segoe UI", 11),
            justify="center",
        )
        self.preview_label.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        side = tk.Frame(body, bg=self.card, width=360)
        side.pack(side="right", fill="y")
        side.pack_propagate(False)
        ttk.Label(side, text="Распознанный номер (тип 1)", style="Card.TLabel").pack(anchor="w", padx=16, pady=(14, 4))
        plate_outer = tk.Frame(side, bg="#111111", padx=2, pady=2)
        plate_outer.pack(anchor="w", padx=16, pady=(0, 6))
        self.plate_widget = tk.Frame(plate_outer, bg="#f4f4f4")
        self.plate_widget.pack()
        left_plate = tk.Frame(self.plate_widget, bg="#f4f4f4")
        left_plate.pack(side="left", padx=(12, 8), pady=8)
        self.plate_body_label = tk.Label(
            left_plate, text="А 000 АА", bg="#f4f4f4", fg="#111111", font=("Consolas", 22, "bold")
        )
        self.plate_body_label.pack()
        tk.Frame(self.plate_widget, bg="#111111", width=2).pack(side="left", fill="y", pady=6)
        right_plate = tk.Frame(self.plate_widget, bg="#f4f4f4")
        right_plate.pack(side="left", padx=(8, 10), pady=4)
        self.plate_region_label = tk.Label(
            right_plate, text="00", bg="#f4f4f4", fg="#111111", font=("Consolas", 18, "bold")
        )
        self.plate_region_label.pack()
        rus_row = tk.Frame(right_plate, bg="#f4f4f4")
        rus_row.pack(pady=(2, 0))
        tk.Label(rus_row, text="RUS", bg="#f4f4f4", fg="#111111", font=("Segoe UI", 8, "bold")).pack(side="left")
        flag = tk.Frame(rus_row, bg="#f4f4f4")
        flag.pack(side="left", padx=(6, 0))
        for color in ("#ffffff", "#0039a6", "#d52b1e"):
            tk.Frame(flag, bg=color, width=18, height=4).pack()
        self.plate_label = self.plate_body_label
        ttk.Label(side, text="Крупно: авто с рамкой", style="Card.TLabel").pack(anchor="w", padx=16, pady=(10, 4))
        self.zoom_label = tk.Label(
            side,
            text="Когда найдётся машина, здесь будет её форма крупно.",
            bg="#020617",
            fg=self.muted,
            font=("Segoe UI", 9),
            wraplength=320,
            justify="center",
            height=11,
        )
        self.zoom_label.pack(fill="x", padx=16, pady=(0, 8))
        self.category_label_widget = tk.Label(
            side, text="НЕИЗВЕСТНЫЙ", bg=self.card, fg=STATUS_COLORS["unknown"], font=("Segoe UI", 20, "bold")
        )
        self.category_label_widget.pack(anchor="w", padx=16, pady=(4, 8))
        self.detail_label = tk.Label(
            side, text="", bg=self.card, fg=self.muted, font=("Segoe UI", 10), wraplength=320, justify="left"
        )
        self.detail_label.pack(anchor="w", padx=16, pady=(0, 12))

        ttk.Button(side, text="Добавить как СВОЙ", command=lambda: self.add_current("own")).pack(fill="x", padx=16, pady=3)
        ttk.Button(side, text="Добавить как ЧУЖОЙ", command=lambda: self.add_current("foreign")).pack(fill="x", padx=16, pady=3)

        ttk.Label(side, text="Ручной ввод номера", style="Card.TLabel").pack(anchor="w", padx=16, pady=(16, 4))
        self.manual_var = tk.StringVar()
        ttk.Entry(side, textvariable=self.manual_var).pack(fill="x", padx=16)
        ttk.Button(side, text="Проверить / записать в журнал", command=self.submit_manual).pack(fill="x", padx=16, pady=8)

        self.owner_var = tk.StringVar()
        ttk.Label(side, text="Имя / объект (для нового номера)", style="Card.TLabel").pack(anchor="w", padx=16, pady=(8, 4))
        ttk.Entry(side, textvariable=self.owner_var).pack(fill="x", padx=16, pady=(0, 16))

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.tab_db = ttk.Frame(notebook, padding=8)
        self.tab_log = ttk.Frame(notebook, padding=8)
        self.tab_set = ttk.Frame(notebook, padding=8)
        notebook.add(self.tab_db, text="  База Свой / Чужой  ")
        notebook.add(self.tab_log, text="  Журнал  ")
        notebook.add(self.tab_set, text="  Настройки  ")
        self._build_db_tab()
        self._build_log_tab()
        self._build_settings_tab()
        self._refresh_stats()

    def _build_db_tab(self) -> None:
        bar = ttk.Frame(self.tab_db)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="Поиск:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_vehicles())
        ttk.Entry(bar, textvariable=self.search_var, width=24).pack(side="left", padx=6)
        self.filter_var = tk.StringVar(value="all")
        ttk.Combobox(
            bar,
            textvariable=self.filter_var,
            values=["all", "own", "foreign"],
            state="readonly",
            width=10,
        ).pack(side="left", padx=6)
        self.filter_var.trace_add("write", lambda *_: self.refresh_vehicles())
        ttk.Button(bar, text="+ Добавить", command=self.open_add_dialog).pack(side="right", padx=4)
        ttk.Button(bar, text="Удалить", command=self.delete_selected_vehicle).pack(side="right", padx=4)
        ttk.Button(bar, text="Экспорт CSV", command=self.export_csv).pack(side="right", padx=4)
        ttk.Button(bar, text="Импорт CSV", command=self.import_csv).pack(side="right", padx=4)

        columns = ("id", "plate", "category", "owner", "notes")
        self.tree_vehicles = ttk.Treeview(self.tab_db, columns=columns, show="headings", selectmode="browse")
        headings = {"id": "ID", "plate": "Номер", "category": "Категория", "owner": "Владелец / объект", "notes": "Заметки"}
        widths = {"id": 50, "plate": 140, "category": 110, "owner": 220, "notes": 280}
        for key in columns:
            self.tree_vehicles.heading(key, text=headings[key])
            self.tree_vehicles.column(key, width=widths[key], anchor="w")
        scroll = ttk.Scrollbar(self.tab_db, orient="vertical", command=self.tree_vehicles.yview)
        self.tree_vehicles.configure(yscrollcommand=scroll.set)
        self.tree_vehicles.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _build_log_tab(self) -> None:
        columns = ("id", "time", "plate", "category", "conf", "source")
        self.tree_events = ttk.Treeview(self.tab_log, columns=columns, show="headings", selectmode="browse")
        headings = {
            "id": "ID",
            "time": "Время",
            "plate": "Номер",
            "category": "Статус",
            "conf": "OCR",
            "source": "Источник",
        }
        widths = {"id": 50, "time": 160, "plate": 140, "category": 120, "conf": 70, "source": 220}
        for key in columns:
            self.tree_events.heading(key, text=headings[key])
            self.tree_events.column(key, width=widths[key])
        scroll = ttk.Scrollbar(self.tab_log, orient="vertical", command=self.tree_events.yview)
        self.tree_events.configure(yscrollcommand=scroll.set)
        self.tree_events.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _build_settings_tab(self) -> None:
        grid = ttk.Frame(self.tab_set)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(1, weight=1)

        self.interval_var = tk.StringVar(value=str(self.cfg.get("interval_sec", 0.8)))
        self.window_var = tk.StringVar(value=self.cfg.get("window_title", ""))
        self.rtsp_var = tk.StringVar(value=self.cfg.get("rtsp_url", ""))
        self.http_var = tk.StringVar(value=self.cfg.get("http_url", ""))
        self.file_var = tk.StringVar(value=self.cfg.get("file_path", ""))
        self.shots_dir_var = tk.StringVar(
            value=self.cfg.get("shots_dir", r"C:\Program Files (x86)\Seetong\pi")
        )
        self.crop_l = tk.StringVar(value=str(int(float(self.cfg.get("crop_left", 0.20)) * 100)))
        self.crop_t = tk.StringVar(value=str(int(float(self.cfg.get("crop_top", 0.12)) * 100)))
        self.crop_r = tk.StringVar(value=str(int(float(self.cfg.get("crop_right", 0.01)) * 100)))
        self.crop_b = tk.StringVar(value=str(int(float(self.cfg.get("crop_bottom", 0.12)) * 100)))
        self.skip_top_var = tk.StringVar(value=str(int(float(self.cfg.get("skip_top", 0.28)) * 100)))
        self.dup_var = tk.StringVar(value=str(self.cfg.get("duplicate_sec", 30)))
        self.conf_var = tk.StringVar(value=str(self.cfg.get("min_confidence", 0.35)))
        self.save_all_var = tk.BooleanVar(value=bool(self.cfg.get("save_all_shots")))
        self.unknown_foreign_var = tk.BooleanVar(value=bool(self.cfg.get("unknown_as_foreign")))
        self.beep_var = tk.BooleanVar(value=bool(self.cfg.get("beep_on_foreign", True)))

        rows = [
            ("Интервал скриншотов, сек", self.interval_var),
            ("Окно Seetong (часть заголовка)", self.window_var),
            ("RTSP URL", self.rtsp_var),
            ("HTTP snapshot URL", self.http_var),
            ("Папка снимков Seetong", self.shots_dir_var),
            ("Файл изображения", self.file_var),
            ("Обрезка слева % (дерево устройств)", self.crop_l),
            ("Обрезка сверху % (вкладки Main View)", self.crop_t),
            ("Обрезка справа %", self.crop_r),
            ("Обрезка снизу % (панель PTZ)", self.crop_b),
            ("Отбросить дальнюю дорогу сверху %", self.skip_top_var),
            ("Не повторять один номер, сек", self.dup_var),
            ("Мин. уверенность OCR (0-1)", self.conf_var),
        ]
        for i, (label, var) in enumerate(rows):
            ttk.Label(grid, text=label).grid(row=i, column=0, sticky="w", pady=3, padx=(0, 8))
            if var is self.window_var:
                self.window_combo = ttk.Combobox(grid, textvariable=self.window_var, width=48)
                self.window_combo.grid(row=i, column=1, sticky="ew", pady=3)
            else:
                ttk.Entry(grid, textvariable=var).grid(row=i, column=1, sticky="ew", pady=3)

        ttk.Button(grid, text="Обновить список окон", command=self.refresh_windows).grid(
            row=1, column=2, padx=8, sticky="w"
        )
        ttk.Button(grid, text="Папка снимков…", command=self.pick_shots_dir).grid(row=4, column=2, padx=8, sticky="nw")
        ttk.Button(grid, text="Только Seetong\\pi", command=self.reset_official_shots_dir).grid(
            row=4, column=3, padx=4, sticky="nw"
        )
        ttk.Button(grid, text="Выбрать файл…", command=self.pick_file).grid(row=5, column=2, padx=8, sticky="w")

        checks = ttk.Frame(self.tab_set)
        checks.pack(fill="x", pady=8)
        ttk.Checkbutton(checks, text="Сохранять каждый скриншот", variable=self.save_all_var).pack(anchor="w")
        ttk.Checkbutton(
            checks, text="Неизвестные номера считать ЧУЖИМИ", variable=self.unknown_foreign_var
        ).pack(anchor="w")
        ttk.Checkbutton(checks, text="Звук при ЧУЖОМ", variable=self.beep_var).pack(anchor="w")

        ttk.Label(
            self.tab_set,
            text=(
                "Облачная камера: снимки из папки Seetong (не весь экран и не IP). "
                "На кадре ищется силуэт машины — дорога, небо и надписи HD IPCAM отсекаются. "
                "Номер только типа 1: буква + 3 цифры + 2 буквы и регион 2–3 цифры справа (А 000 АА | 00 RUS)."
            ),
            style="Muted.TLabel",
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(8, 8))

        engine_text = "OCR-движки: не установлены. Для авточтения: pip install rapidocr-onnxruntime"
        try:
            from anpr.recognizer import available_engines

            engines = available_engines()
            if engines:
                engine_text = "OCR-движки: " + ", ".join(engines)
        except Exception:
            pass
        ttk.Label(self.tab_set, text=engine_text, style="Muted.TLabel").pack(anchor="w")
        ttk.Button(self.tab_set, text="Сохранить настройки", command=self.persist_settings).pack(anchor="w", pady=12)
        ttk.Button(
            self.tab_set,
            text="Удалить лишние копии программы",
            command=self.remove_wrong_copies,
        ).pack(anchor="w")

    def persist_settings(self) -> None:
        self.cfg.update(self._settings_from_form())
        save_config(self.cfg)
        messagebox.showinfo("Сохранено", "Настройки записаны в anpr_data/config.json")

    def _settings_from_form(self) -> dict:
        def _float(var, default):
            try:
                return float(str(var.get()).replace(",", "."))
            except ValueError:
                return default

        def _pct(var, default):
            return max(0.0, min(0.65, _float(var, default * 100) / 100.0))

        source_key = SOURCE_VALUES.get(self.source_var.get(), "seetong_folder")
        return {
            "source": source_key,
            "interval_sec": max(0.3, _float(self.interval_var, 0.8)),
            "window_title": self.window_var.get().strip() or "Seetong Lite Client",
            "camera_ip": self.camera_ip_var.get().strip(),
            "camera_user": self.camera_user_var.get().strip() or "admin",
            "camera_password": self.camera_pass_var.get(),
            "device_id": self.device_id_var.get().strip(),
            "rtsp_url": self.rtsp_var.get().strip(),
            "http_url": self.http_var.get().strip(),
            "file_path": self.file_var.get().strip(),
            "shots_dir": sanitize_shots_dir(self.shots_dir_var.get().strip()),
            "crop_left": min(0.45, _pct(self.crop_l, 0.20)),
            "crop_top": min(0.45, _pct(self.crop_t, 0.12)),
            "crop_right": min(0.45, _pct(self.crop_r, 0.01)),
            "crop_bottom": min(0.45, _pct(self.crop_b, 0.12)),
            "skip_top": _pct(self.skip_top_var, 0.28),
            "duplicate_sec": int(_float(self.dup_var, 30)),
            "min_confidence": max(0.0, min(1.0, _float(self.conf_var, 0.35))),
            "save_all_shots": bool(self.save_all_var.get()),
            "unknown_as_foreign": bool(self.unknown_foreign_var.get()),
            "beep_on_foreign": bool(self.beep_var.get()),
        }

    def refresh_windows(self) -> None:
        try:
            from anpr.capture import list_windows

            titles = [item.title for item in list_windows()]
        except Exception:
            titles = []
        self.window_combo["values"] = titles
        if titles and not self.window_var.get():
            from anpr.capture import find_seetong_window

            found = find_seetong_window()
            if found:
                self.window_var.set(found.title)
        if not self.window_var.get():
            self.window_var.set("Seetong Lite Client")

    def open_camera_dialog(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Подключение камеры")
        dlg.geometry("520x560")
        dlg.configure(bg=self.bg)

        ttk.Label(
            dlg,
            text="Камера в той же сети, что и этот компьютер — подключайте по IP или RTSP.\n"
            "Только облако Seetong без IP — снимки из папки клиента.",
            wraplength=480,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(16, 10))

        ttk.Label(dlg, text="IP камеры в локальной сети").pack(anchor="w", padx=20)
        ttk.Entry(dlg, textvariable=self.camera_ip_var, width=44).pack(padx=20, pady=(0, 6))
        ttk.Label(dlg, text="Логин").pack(anchor="w", padx=20)
        ttk.Entry(dlg, textvariable=self.camera_user_var, width=44).pack(padx=20, pady=(0, 6))
        ttk.Label(dlg, text="Пароль").pack(anchor="w", padx=20)
        ttk.Entry(dlg, textvariable=self.camera_pass_var, width=44, show="*").pack(padx=20, pady=(0, 10))

        def use_ip(kind: str) -> None:
            from anpr.camera import build_http_url, build_rtsp_url, connect_camera

            ip = self.camera_ip_var.get().strip()
            user = self.camera_user_var.get().strip() or "admin"
            password = self.camera_pass_var.get()
            if not ip or ip == "192.168.0.123":
                messagebox.showwarning("Нет IP", "Введите IP камеры, например 192.168.1.64")
                return
            self.http_var.set(build_http_url(ip, user, password))
            self.rtsp_var.set(build_rtsp_url(ip, user, password))
            if kind == "auto":
                try:
                    found = connect_camera(ip, user, password)
                except Exception as exc:
                    messagebox.showerror("Камера не открылась", str(exc))
                    return
                self.source_var.set(SOURCE_LABELS.get(found["source"], SOURCE_LABELS["http"]))
                if found.get("http_url"):
                    self.http_var.set(found["http_url"])
                if found.get("rtsp_url"):
                    self.rtsp_var.set(found["rtsp_url"])
            elif kind == "http":
                self.source_var.set(SOURCE_LABELS["http"])
            else:
                self.source_var.set(SOURCE_LABELS["rtsp"])
            self.cfg.update(self._settings_from_form())
            save_config(self.cfg)
            dlg.destroy()
            messagebox.showinfo(
                "Готово",
                "Источник: камера по сети.\nНажмите Старт.\nSeetong на этом компьютере не обязателен.",
            )

        ttk.Button(dlg, text="Подключить по IP (найти HTTP или RTSP)", command=lambda: use_ip("auto")).pack(
            padx=20, pady=4, fill="x"
        )
        ttk.Button(dlg, text="Только снимок HTTP", command=lambda: use_ip("http")).pack(padx=20, pady=2, fill="x")
        ttk.Button(dlg, text="Только поток RTSP", command=lambda: use_ip("rtsp")).pack(padx=20, pady=2, fill="x")

        ttk.Separator(dlg).pack(fill="x", padx=20, pady=14)
        ttk.Label(dlg, text="Облако Seetong (нет локального IP)").pack(anchor="w", padx=20)
        ttk.Label(dlg, text="Папка снимков").pack(anchor="w", padx=20, pady=(6, 0))
        ttk.Entry(dlg, textvariable=self.shots_dir_var, width=44).pack(padx=20, pady=(0, 8))

        def use_cloud() -> None:
            folder = self.shots_dir_var.get().strip() or r"C:\Program Files (x86)\Seetong\pi"
            self.shots_dir_var.set(folder)
            self.source_var.set(SOURCE_LABELS["seetong_folder"])
            self.cfg.update(self._settings_from_form())
            save_config(self.cfg)
            dlg.destroy()
            messagebox.showinfo("Готово", "Источник: папка снимков Seetong.\nСнимок в клиенте, затем Старт.")

        ttk.Button(dlg, text="Использовать снимки Seetong", command=use_cloud).pack(padx=20, pady=6, fill="x")

    def apply_lite_preset(self) -> None:
        self.window_var.set("Seetong Lite Client")
        self.source_var.set(SOURCE_LABELS["seetong_window"])
        self.crop_l.set("20")
        self.crop_t.set("12")
        self.crop_r.set("1")
        self.crop_b.set("12")
        self.skip_top_var.set("28")
        self.conf_var.set("0.35")

    def pick_shots_dir(self) -> None:
        path = filedialog.askdirectory(title="Папка снимков Seetong")
        if path:
            self.shots_dir_var.set(sanitize_shots_dir(path))
            self.source_var.set(SOURCE_LABELS["seetong_folder"])

    def reset_official_shots_dir(self) -> None:
        self.shots_dir_var.set(OFFICIAL_SEETONG_SHOTS_DIR)
        self.cfg["shots_dir"] = OFFICIAL_SEETONG_SHOTS_DIR
        self.source_var.set(SOURCE_LABELS["seetong_folder"])
        save_config(self.cfg)

    def remove_wrong_copies(self) -> None:
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "FIX_AND_CLEAN.ps1")
        if sys.platform != "win32":
            messagebox.showinfo("Копии", "Очистка копий запускается на Windows ПК.")
            return
        if not os.path.isfile(script):
            messagebox.showerror("Файл", "Не найден FIX_AND_CLEAN.ps1 рядом с программой.")
            return
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
            cwd=os.path.dirname(script),
        )
        messagebox.showinfo(
            "Очистка",
            "Старые папки my_search_gpu_bot будут удалены.\n"
            "Программа останется в D:\\AvtonomeraSeetong.\n"
            "Дальше открывайте ярлык Автономера Seetong на рабочем столе.",
        )

    def pick_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Кадр с камеры",
            filetypes=[("Изображения", "*.jpg *.jpeg *.png *.bmp"), ("Все файлы", "*.*")],
        )
        if path:
            self.file_var.set(path)

    def start_capture(self) -> None:
        if self._running:
            return
        self.cfg.update(self._settings_from_form())
        source = self.cfg.get("source")
        if source == "monitor":
            if not messagebox.askyesno(
                "Весь экран",
                "«Весь экран» снимает рабочий стол и читает надписи Seetong, а не номера машин.\n\n"
                "Лучше брать снимки из папки Seetong. Всё равно включить весь экран?",
            ):
                return
        if source in ("http", "rtsp") and "192.168.0.123" in (
            self.cfg.get("http_url", "") + self.cfg.get("rtsp_url", "")
        ):
            if messagebox.askyesno(
                "Нужен IP камеры",
                "Сейчас стоит примерный адрес 192.168.0.123.\nОткрыть окно «Камера по IP»?",
            ):
                self.open_camera_dialog()
                return
        save_config(self.cfg)
        self._running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.run_label.config(text="идёт съёмка…")
        threading.Thread(target=self._loop, daemon=True).start()

    def stop_capture(self) -> None:
        self._running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.run_label.config(text="остановлено")

    def capture_once(self) -> None:
        self.cfg.update(self._settings_from_form())
        threading.Thread(target=lambda: self._tick(force_save=True), daemon=True).start()

    def _loop(self) -> None:
        while self._running:
            self._tick()
            time.sleep(float(self.cfg.get("interval_sec", 0.8)))

    def _tick(self, force_save: bool = False) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            from anpr.capture import crop_roi, grab_frame, save_screenshot
            from anpr.recognizer import recognize_scene

            frame, source_name = grab_frame(
                source=self.cfg.get("source", "seetong_folder"),
                window_title=self.cfg.get("window_title", ""),
                rtsp_url=self.cfg.get("rtsp_url", ""),
                http_url=self.cfg.get("http_url", ""),
                file_path=self.cfg.get("file_path", ""),
                shots_dir=self.cfg.get("shots_dir", r"C:\Program Files (x86)\Seetong\pi"),
            )
            source = self.cfg.get("source", "seetong_folder")
            if source in ("http", "rtsp", "file", "seetong_folder"):
                frame = crop_roi(
                    frame,
                    left=0.0,
                    top=0.02,
                    right=0.0,
                    bottom=0.06,
                    skip_top=self.cfg.get("skip_top", 0),
                )
            else:
                frame = crop_roi(
                    frame,
                    left=self.cfg.get("crop_left", 0),
                    top=self.cfg.get("crop_top", 0),
                    right=self.cfg.get("crop_right", 0),
                    bottom=self.cfg.get("crop_bottom", 0),
                    skip_top=self.cfg.get("skip_top", 0),
                )
            self._last_frame = frame
            self.root.after(0, lambda: self._show_preview(frame))
            shot = ""
            if force_save or self.cfg.get("save_all_shots"):
                shot = save_screenshot(frame, prefix="live")
            t0 = time.perf_counter()
            hits, vehicles, annotated, zoom = recognize_scene(
                frame, min_confidence=float(self.cfg.get("min_confidence", 0.28))
            )
            elapsed = time.perf_counter() - t0
            elapsed_txt = f"{elapsed:.1f} с" if elapsed >= 0.1 else f"{elapsed * 1000:.0f} мс"
            preview = annotated if annotated is not None else frame
            self.root.after(0, lambda img=preview: self._show_preview(img))
            self.root.after(0, lambda z=zoom: self._show_zoom(z))
            car_note = (
                f"найдено авто: {len(vehicles)} · рамка на кадре"
                if vehicles
                else "рамка от номера"
            )
            if not hits:
                self.root.after(
                    0,
                    lambda: self._set_detection(
                        self._last_plate or "—",
                        "unknown" if not self._last_plate else self._last_category,
                        f"Номер не прочитан ({source_name}, {car_note}, {elapsed_txt}). "
                        f"Нужен вид «А 000 АА 00». Можно ввести вручную.",
                        0.0,
                    ),
                )
                return

            logged = 0
            for hit in hits:
                if not plate_is_valid(hit.plate) or is_osd_text(hit.plate) or is_osd_text(hit.raw_text):
                    continue
                info = self.db.classify(hit.plate, unknown_as_foreign=bool(self.cfg.get("unknown_as_foreign")))
                shot_path = shot
                if not shot_path and info["category"] != "own" and logged == 0:
                    shot_path = save_screenshot(preview, prefix=info["category"])
                duplicate = self.db.event_is_duplicate(hit.plate, int(self.cfg.get("duplicate_sec", 30)))
                if not duplicate:
                    self.db.log_event(
                        plate=hit.plate,
                        category=info["category"],
                        confidence=hit.confidence,
                        source=f"{source_name}/{hit.engine}",
                        screenshot_path=shot_path or "",
                    )
                    logged += 1
            if logged:
                self.root.after(0, self.refresh_events)
                self.root.after(0, self._refresh_stats)

            hit = hits[0]
            info = self.db.classify(hit.plate, unknown_as_foreign=bool(self.cfg.get("unknown_as_foreign")))
            owner = info["vehicle"]["owner_name"] if info["vehicle"] else "нет в базе"
            self._last_plate = hit.plate
            self._last_category = info["category"]
            extras = [format_plate(h.plate) for h in hits[1:3] if plate_is_valid(h.plate)]
            extra_txt = f"  ·  ещё: {', '.join(extras)}" if extras else ""
            detail = (
                f"{owner}  ·  {car_note}  ·  уверенность {hit.confidence:.0%}  "
                f"·  {hit.engine or 'ocr'}  ·  {elapsed_txt}  ·  {source_name}{extra_txt}"
            )
            self.root.after(
                0,
                lambda p=hit.plate, c=info["category"], d=detail, s=hit.confidence: self._set_detection(p, c, d, s),
            )
            if info["category"] == "foreign" and self.cfg.get("beep_on_foreign"):
                self.root.after(0, self._beep)
        except Exception as exc:
            message = str(exc)
            self.root.after(0, lambda m=message: self._show_capture_error(m))
        finally:
            self._busy = False

    def _show_capture_error(self, message: str) -> None:
        self._set_detection("—", "unknown", message, 0.0)
        self.preview_label.config(image="", text=message)

    def _show_preview(self, frame) -> None:
        try:
            from PIL import Image, ImageTk
        except ImportError:
            self.preview_label.config(text="Установите Pillow для предпросмотра: pip install Pillow")
            return
        rgb = frame[:, :, ::-1]
        image = Image.fromarray(rgb)
        image.thumbnail((880, 520))
        self._preview_photo = ImageTk.PhotoImage(image)
        self.preview_label.config(image=self._preview_photo, text="")

    def _show_zoom(self, crop) -> None:
        if crop is None or getattr(crop, "size", 0) == 0:
            self.zoom_label.config(image="", text="Табличка не выделена — введите номер вручную")
            self._zoom_photo = None
            return
        try:
            from PIL import Image, ImageTk
        except ImportError:
            self.zoom_label.config(text="Нужен Pillow для увеличения")
            return
        rgb = crop[:, :, ::-1]
        image = Image.fromarray(rgb)
        image.thumbnail((360, 240))
        self._zoom_photo = ImageTk.PhotoImage(image)
        self.zoom_label.config(image=self._zoom_photo, text="")

    def _set_detection(self, plate: str, category: str, detail: str, _confidence: float) -> None:
        if plate and plate != "—":
            body, region = format_plate_parts(plate)
        else:
            body, region = "А 000 АА", "00"
        self.plate_body_label.config(text=body)
        self.plate_region_label.config(text=region)
        self.category_label_widget.config(
            text=category_label(category),
            fg=STATUS_COLORS.get(category, STATUS_COLORS["unknown"]),
        )
        self.detail_label.config(text=detail)
        if plate and plate != "—":
            self.manual_var.set(normalize_plate(plate))

    def _beep(self) -> None:
        try:
            if sys.platform == "win32":
                import winsound

                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            else:
                self.root.bell()
        except Exception:
            self.root.bell()

    def add_current(self, category: str) -> None:
        plate = self.manual_var.get().strip() or self._last_plate
        if not plate:
            messagebox.showwarning("Нет номера", "Сначала распознайте или введите номер.")
            return
        self.db.add_vehicle(plate=plate, category=category, owner_name=self.owner_var.get())
        info = self.db.classify(plate)
        self._last_plate = normalize_plate(plate)
        self._last_category = info["category"]
        self._set_detection(self._last_plate, info["category"], "Записано в базу", 1.0)
        self.refresh_vehicles()
        self._refresh_stats()

    def submit_manual(self) -> None:
        plate = self.manual_var.get().strip()
        if not plate:
            return
        normalized = normalize_plate(plate)
        if not plate_is_valid(normalized):
            if not messagebox.askyesno(
                "Номер необычный",
                f"«{normalized or plate}» не похож на стандартный российский номер. Всё равно записать в журнал?",
            ):
                return
        info = self.db.classify(normalized or plate, unknown_as_foreign=bool(self.cfg.get("unknown_as_foreign")))
        shot = ""
        if self._last_frame is not None:
            from anpr.capture import save_screenshot

            shot = save_screenshot(self._last_frame, prefix="manual")
        self.db.log_event(
            plate=normalized or plate,
            category=info["category"],
            confidence=1.0,
            source="manual",
            screenshot_path=shot,
        )
        self._last_plate = normalized or plate
        self._last_category = info["category"]
        owner = info["vehicle"]["owner_name"] if info["vehicle"] else "нет в базе"
        self._set_detection(self._last_plate, info["category"], owner, 1.0)
        self.refresh_events()
        self._refresh_stats()

    def open_add_dialog(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Добавить автомобиль")
        dlg.geometry("420x320")
        dlg.configure(bg=self.bg)
        plate_e, name_e, cat_e, notes_e = tk.StringVar(), tk.StringVar(), tk.StringVar(value="own"), tk.StringVar()
        for label, var in (
            ("Номер", plate_e),
            ("Владелец / объект", name_e),
            ("Категория (own / foreign)", cat_e),
            ("Заметки", notes_e),
        ):
            ttk.Label(dlg, text=label).pack(anchor="w", padx=20, pady=(12, 2))
            ttk.Entry(dlg, textvariable=var, width=40).pack(padx=20)

        def save() -> None:
            if not plate_e.get().strip():
                messagebox.showwarning("Нет номера", "Введите госномер.")
                return
            self.db.add_vehicle(
                plate=plate_e.get(),
                category=parse_category(cat_e.get()),
                owner_name=name_e.get(),
                notes=notes_e.get(),
            )
            dlg.destroy()
            self.refresh_vehicles()
            self._refresh_stats()

        ttk.Button(dlg, text="Сохранить", command=save).pack(pady=16)

    def delete_selected_vehicle(self) -> None:
        selected = self.tree_vehicles.selection()
        if not selected:
            return
        if not messagebox.askyesno("Удалить", "Удалить выбранный номер из базы?"):
            return
        vehicle_id = self.tree_vehicles.item(selected[0])["values"][0]
        self.db.delete_vehicle(int(vehicle_id))
        self.refresh_vehicles()
        self._refresh_stats()

    def export_csv(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.db.export_vehicles_csv())
        messagebox.showinfo("Экспорт", f"Сохранено: {path}")

    def import_csv(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("Все файлы", "*.*")])
        if not path:
            return
        with open(path, "r", encoding="utf-8-sig") as handle:
            count = self.db.import_vehicles_csv(handle.read())
        self.refresh_vehicles()
        self._refresh_stats()
        messagebox.showinfo("Импорт", f"Загружено записей: {count}")

    def refresh_vehicles(self) -> None:
        for item in self.tree_vehicles.get_children():
            self.tree_vehicles.delete(item)
        category = self.filter_var.get()
        if category == "all":
            category = None
        for row in self.db.get_vehicles(category=category, search=self.search_var.get()):
            self.tree_vehicles.insert(
                "",
                "end",
                values=(
                    row["id"],
                    format_plate(row["plate_normalized"]),
                    category_label(row["category"]),
                    row["owner_name"] or "—",
                    row["notes"] or "",
                ),
            )

    def refresh_events(self) -> None:
        for item in self.tree_events.get_children():
            self.tree_events.delete(item)
        for row in self.db.get_events(limit=250):
            self.tree_events.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["created_at"],
                    format_plate(row["plate_normalized"]),
                    category_label(row["category"]),
                    f"{float(row['confidence'] or 0):.0%}",
                    row["source"] or "",
                ),
            )

    def _refresh_stats(self) -> None:
        stats = self.db.stats()
        self.stats_label.config(
            text=f"Свои: {stats['own']}   Чужие: {stats['foreign']}   Событий: {stats['events']}"
        )

    def on_close(self) -> None:
        self._running = False
        try:
            self.cfg.update(self._settings_from_form())
            save_config(self.cfg)
        except Exception:
            pass
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    AnprApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
