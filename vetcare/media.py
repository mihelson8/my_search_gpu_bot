"""
Media handling helpers: извлечение кадров из коротких видео и проверка лимитов.

Кадры извлекаются через ffmpeg, если он доступен в системе. Все ограничения
подобраны под Telegram Bot API: файлы больше 20 МБ бот скачать не может.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

MAX_VIDEO_SECONDS = 60
MAX_FILE_MB = 20
DEFAULT_FRAME_COUNT = 8
FFMPEG_TIMEOUT_SECONDS = 60


@dataclass
class VideoCheck:
    accepted: bool
    problems: List[str]

    @property
    def message(self) -> str:
        if self.accepted:
            return "Видео принято в обработку."
        return "Видео не подходит: " + "; ".join(self.problems) + "."


def ffmpeg_path() -> Optional[str]:
    return shutil.which("ffmpeg")


def ffprobe_path() -> Optional[str]:
    return shutil.which("ffprobe")


def check_video(duration_seconds: Optional[float], size_bytes: Optional[int]) -> VideoCheck:
    """Проверяет длительность и размер видео до скачивания файла."""
    problems: List[str] = []
    if duration_seconds is not None and duration_seconds > MAX_VIDEO_SECONDS:
        problems.append(
            f"длительность {int(duration_seconds)} секунд, максимум {MAX_VIDEO_SECONDS} секунд"
        )
    if size_bytes is not None and size_bytes > MAX_FILE_MB * 1024 * 1024:
        problems.append(
            f"размер {size_bytes // (1024 * 1024)} МБ, лимит Telegram для ботов {MAX_FILE_MB} МБ"
        )
    return VideoCheck(accepted=not problems, problems=problems)


def probe_duration(path: str) -> Optional[float]:
    """Определяет длительность видео через ffprobe."""
    probe = ffprobe_path()
    if not probe:
        return None
    try:
        result = subprocess.run(
            [
                probe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
            check=False,
        )
        value = result.stdout.strip()
        return float(value) if value else None
    except (subprocess.SubprocessError, ValueError) as exc:
        logger.warning("ffprobe не смог определить длительность: %s", exc)
        return None


def extract_frames(path: str, max_frames: int = DEFAULT_FRAME_COUNT) -> List[bytes]:
    """Извлекает равномерно распределённые кадры видео в виде JPEG-байтов."""
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        logger.warning("ffmpeg не найден, разбор видео недоступен")
        return []

    duration = probe_duration(path)
    if duration and duration > 0:
        fps = max(0.5, min(4.0, max_frames / duration))
    else:
        fps = 2.0

    with tempfile.TemporaryDirectory(prefix="vetcare_frames_") as workdir:
        pattern = os.path.join(workdir, "frame_%03d.jpg")
        command = [
            ffmpeg,
            "-v",
            "error",
            "-i",
            path,
            "-vf",
            f"fps={fps:.3f},scale=640:-2",
            "-frames:v",
            str(max_frames),
            "-q:v",
            "3",
            pattern,
        ]
        try:
            subprocess.run(
                command,
                capture_output=True,
                timeout=FFMPEG_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.SubprocessError as exc:
            logger.warning("ffmpeg не смог извлечь кадры: %s", exc)
            return []

        frames: List[bytes] = []
        for name in sorted(os.listdir(workdir)):
            if not name.endswith(".jpg"):
                continue
            with open(os.path.join(workdir, name), "rb") as handle:
                frames.append(handle.read())
        return frames


def extract_frames_from_bytes(
    data: bytes,
    suffix: str = ".mp4",
    max_frames: int = DEFAULT_FRAME_COUNT,
) -> List[bytes]:
    """Сохраняет видео во временный файл и извлекает из него кадры."""
    with tempfile.NamedTemporaryFile(prefix="vetcare_video_", suffix=suffix, delete=False) as handle:
        handle.write(data)
        temp_path = handle.name
    try:
        return extract_frames(temp_path, max_frames=max_frames)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
