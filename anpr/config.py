"""Persistent settings for the ANPR desktop app."""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from anpr.database import DATA_DIR

DEFAULT_CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

DEFAULTS: Dict[str, Any] = {
    "source": "http",
    "interval_sec": 1.5,
    "window_title": "Seetong Lite Client",
    "camera_ip": "192.168.0.123",
    "camera_user": "admin",
    "camera_password": "123456",
    "rtsp_url": "rtsp://admin:123456@192.168.0.123:554/mpeg4",
    "http_url": "http://admin:123456@192.168.0.123/snapshot.cgi",
    "file_path": "",
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
    return data


def save_config(data: Dict[str, Any], path: str = DEFAULT_CONFIG_PATH) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    merged = dict(DEFAULTS)
    merged.update(data)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(merged, handle, ensure_ascii=False, indent=2)
