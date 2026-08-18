"""Persistent settings for the ANPR desktop app."""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from anpr.database import DATA_DIR

DEFAULT_CONFIG_PATH = os.path.join(DATA_DIR, "config.json")


def side_window_geometry(
    screen_w: int,
    screen_h: int,
    win_w: int = 980,
    win_h: int = 720,
    margin: int = 16,
) -> str:
    """Place the ANPR window on the right so Seetong stays visible on the left."""
    screen_w = max(int(screen_w), 800)
    screen_h = max(int(screen_h), 600)
    win_w = min(int(win_w), max(720, screen_w - margin * 2))
    win_h = min(int(win_h), max(520, screen_h - margin * 2))
    x = max(margin, screen_w - win_w - margin)
    y = max(margin, min(margin * 4, screen_h - win_h - margin))
    return f"{win_w}x{win_h}+{x}+{y}"


OFFICIAL_SEETONG_SHOTS_DIR = r"C:\Program Files (x86)\Seetong\pi"
_LEFTOVER_PATH_MARKERS = (
    "my_search_gpu_bot",
    "winrar",
    "temp\\rar",
    "appdata\\local\\temp",
)


def official_seetong_shots_dir() -> str:
    return OFFICIAL_SEETONG_SHOTS_DIR


def is_leftover_extract_path(folder: str) -> bool:
    """ZIP extracts and old copies — not the Seetong screenshot folder."""
    lowered = (folder or "").replace("/", "\\").lower()
    return any(marker in lowered for marker in _LEFTOVER_PATH_MARKERS)


def sanitize_shots_dir(folder: str = "") -> str:
    """Keep only the real Seetong screenshot folder, drop leftover copies."""
    raw = os.path.normpath((folder or "").strip()) if (folder or "").strip() else ""
    if not raw or is_leftover_extract_path(raw):
        return OFFICIAL_SEETONG_SHOTS_DIR
    return raw


DEFAULTS: Dict[str, Any] = {
    "source": "seetong_folder",
    "interval_sec": 2.0,
    "window_title": "Seetong Lite Client",
    "camera_ip": "192.168.0.123",
    "camera_user": "admin",
    "camera_password": "123456",
    "rtsp_url": "rtsp://admin:123456@192.168.0.123:554/mpeg4",
    "http_url": "http://admin:123456@192.168.0.123/snapshot.cgi",
    "file_path": "",
    "device_id": "35918051",
    "shots_dir": OFFICIAL_SEETONG_SHOTS_DIR,
    "crop_left": 0.20,
    "crop_top": 0.12,
    "crop_right": 0.01,
    "crop_bottom": 0.12,
    "skip_top": 0.28,
    "duplicate_sec": 30,
    "min_confidence": 0.35,
    "save_all_shots": False,
    "unknown_as_foreign": False,
    "beep_on_foreign": True,
}


def load_config(path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    data = dict(DEFAULTS)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if isinstance(stored, dict):
                data.update(stored)
        except (OSError, json.JSONDecodeError):
            pass
    data["shots_dir"] = sanitize_shots_dir(str(data.get("shots_dir") or ""))
    return data


def save_config(data: Dict[str, Any], path: str = DEFAULT_CONFIG_PATH) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    merged = dict(DEFAULTS)
    merged.update(data)
    merged["shots_dir"] = sanitize_shots_dir(str(merged.get("shots_dir") or ""))
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(merged, handle, ensure_ascii=False, indent=2)
