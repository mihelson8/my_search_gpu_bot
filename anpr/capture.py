"""Video / screenshot capture from Seetong window, RTSP, HTTP snapshot, or file."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from anpr.database import DATA_DIR

SHOTS_DIR = os.path.join(DATA_DIR, "shots")

SEETONG_KEYWORDS = (
    "seetong lite",
    "lite client",
    "seetong",
    "see tong",
    "sitong",
    "ситонг",
    "си тон",
    "topsee",
    "tpsee",
    "nvr client",
    "cms client",
)


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    def matches_seetong(self) -> bool:
        title = self.title.lower()
        return any(key in title for key in SEETONG_KEYWORDS)

    def is_lite_client(self) -> bool:
        title = self.title.lower()
        return "lite client" in title or "seetong lite" in title


def _require_numpy():
    try:
        import numpy as np  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Для захвата кадра нужен пакет numpy. Установите: pip install -r requirements-anpr.txt"
        ) from exc
    return np


def crop_roi(
    image,
    left: float = 0.0,
    top: float = 0.0,
    right: float = 0.0,
    bottom: float = 0.0,
    skip_top: float = 0.0,
):
    """Crop UI margins, then optionally drop the distant top of a high-angle camera view."""
    if image is None or getattr(image, "size", 0) == 0:
        return image
    h, w = image.shape[:2]
    x0 = int(max(0.0, min(0.45, float(left))) * w)
    y0 = int(max(0.0, min(0.45, float(top))) * h)
    x1 = w - int(max(0.0, min(0.45, float(right))) * w)
    y1 = h - int(max(0.0, min(0.45, float(bottom))) * h)
    if x1 - x0 < 20 or y1 - y0 < 20:
        return image
    cropped = image[y0:y1, x0:x1]
    skip = max(0.0, min(0.65, float(skip_top or 0)))
    if skip <= 0:
        return cropped
    ch = cropped.shape[0]
    y_skip = int(skip * ch)
    if ch - y_skip < 40:
        return cropped
    return cropped[y_skip:, :]


def list_windows() -> List[WindowInfo]:
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

    results: List[WindowInfo] = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = (buf.value or "").strip()
        if not title:
            return True
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        info = WindowInfo(
            hwnd=int(hwnd),
            title=title,
            left=int(rect.left),
            top=int(rect.top),
            right=int(rect.right),
            bottom=int(rect.bottom),
        )
        if info.width >= 240 and info.height >= 180:
            results.append(info)
        return True

    user32.EnumWindows(EnumWindowsProc(_callback), 0)
    results.sort(
        key=lambda item: (
            not item.is_lite_client(),
            not item.matches_seetong(),
            item.title.lower(),
        )
    )
    return results


def find_seetong_window(preferred_title: str = "") -> Optional[WindowInfo]:
    windows = list_windows()
    if preferred_title:
        needle = preferred_title.lower().strip()
        for item in windows:
            if needle in item.title.lower():
                return item
    for item in windows:
        if item.is_lite_client():
            return item
    for item in windows:
        if item.matches_seetong():
            return item
    return None


def _grab_mss_region(left: int, top: int, width: int, height: int):
    np = _require_numpy()
    try:
        import mss  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Для скриншота окна нужен пакет mss. Установите: pip install -r requirements-anpr.txt"
        ) from exc

    with mss.mss() as sct:
        raw = sct.grab({"left": left, "top": top, "width": width, "height": height})
    frame = np.frombuffer(raw.rgb, dtype=np.uint8).reshape(raw.height, raw.width, 3)
    # mss.rgb is RGB; convert to BGR for OpenCV.
    return frame[:, :, ::-1].copy()


def _grab_printwindow(hwnd: int, width: int, height: int):
    """Capture a window even if another window covers part of it (Windows)."""
    if sys.platform != "win32" or width <= 0 or height <= 0:
        return None
    np = _require_numpy()
    import ctypes
    from ctypes import wintypes

    PW_RENDERFULLCONTENT = 2
    SRCCOPY = 0x00CC0020
    DIB_RGB_COLORS = 0
    BI_RGB = 0

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    hwnd_dc = user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        return None
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
    old = gdi32.SelectObject(mem_dc, bmp)
    ok = False
    try:
        if user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT):
            ok = True
        elif gdi32.BitBlt(mem_dc, 0, 0, width, height, hwnd_dc, 0, 0, SRCCOPY):
            ok = True
    except Exception:
        ok = False
    if not ok:
        gdi32.SelectObject(mem_dc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)
        return None

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bmp, 0, height, buffer, ctypes.byref(bmi), DIB_RGB_COLORS)
    gdi32.SelectObject(mem_dc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)
    bgra = np.frombuffer(buffer, dtype=np.uint8).reshape(height, width, 4)
    return bgra[:, :, :3].copy()


def missing_capture_packages():
    missing = []
    for label, module in (("numpy", "numpy"), ("Pillow", "PIL"), ("mss", "mss")):
        try:
            __import__(module)
        except ImportError:
            missing.append(label)
    return missing


def _is_mostly_black(frame, threshold: float = 16.0) -> bool:
    try:
        return float(frame.mean()) < threshold
    except Exception:
        return True


def grab_window(info: WindowInfo):
    """Prefer a real screen screenshot: Seetong video is often black via PrintWindow."""
    mss_frame = None
    pw_frame = None
    try:
        mss_frame = _grab_mss_region(info.left, info.top, info.width, info.height)
    except Exception:
        mss_frame = None
    try:
        pw_frame = _grab_printwindow(info.hwnd, info.width, info.height)
    except Exception:
        pw_frame = None

    if mss_frame is not None and getattr(mss_frame, "size", 0) > 0 and not _is_mostly_black(mss_frame):
        return mss_frame
    if pw_frame is not None and getattr(pw_frame, "size", 0) > 0 and not _is_mostly_black(pw_frame):
        return pw_frame
    if mss_frame is not None and getattr(mss_frame, "size", 0) > 0:
        return mss_frame
    if pw_frame is not None and getattr(pw_frame, "size", 0) > 0:
        return pw_frame
    raise RuntimeError(
        "Не удалось снять окно Seetong. Поставьте пакеты: python -m pip install -r requirements-anpr.txt "
        "и сдвиньте окно автономеров, чтобы картинка камеры была видна."
    )


def grab_monitor(monitor_index: int = 1):
    np = _require_numpy()
    try:
        import mss  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Для скриншота экрана нужен пакет mss. Установите: pip install -r requirements-anpr.txt"
        ) from exc
    with mss.mss() as sct:
        monitors = sct.monitors
        index = min(max(1, monitor_index), len(monitors) - 1)
        raw = sct.grab(monitors[index])
    frame = np.frombuffer(raw.rgb, dtype=np.uint8).reshape(raw.height, raw.width, 3)
    return frame[:, :, ::-1].copy()


def grab_rtsp(url: str):
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Для RTSP нужен opencv-python. Установите: pip install -r requirements-anpr.txt"
        ) from exc
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        raise RuntimeError(f"Не удалось открыть RTSP: {url}")
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError("RTSP открыт, но кадр не получен")
    return frame


def grab_http_snapshot(url: str):
    np = _require_numpy()
    try:
        import urllib.parse
        import urllib.request
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Для HTTP-снимка нужен opencv-python. Установите: pip install -r requirements-anpr.txt"
        ) from exc
    request = urllib.request.Request(url, headers={"User-Agent": "anpr-seetong/1.0"})
    parsed = urllib.parse.urlparse(url)
    opener = urllib.request.build_opener()
    if parsed.username is not None:
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        password_mgr.add_password(
            None,
            f"{parsed.scheme}://{host}{port}/",
            urllib.parse.unquote(parsed.username),
            urllib.parse.unquote(parsed.password or ""),
        )
        opener = urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(password_mgr))
    with opener.open(request, timeout=8) as response:
        data = response.read()
    array = np.frombuffer(data, dtype=np.uint8)
    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError(f"Не удалось декодировать снимок: {url}")
    return frame


def newest_image_path(folder: str) -> str:
    import glob

    if not folder or not os.path.isdir(folder):
        raise RuntimeError(f"Нет папки снимков Seetong: {folder}")
    files = []
    for pattern in ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.JPG", "*.PNG"):
        files.extend(glob.glob(os.path.join(folder, pattern)))
        files.extend(glob.glob(os.path.join(folder, "*", pattern)))
    files = [path for path in files if os.path.isfile(path)]
    if not files:
        raise RuntimeError(
            f"В папке нет снимков: {folder}\n"
            "Откройте Main View в Seetong и нажмите кнопку снимка (фотоаппарат)."
        )
    return max(files, key=os.path.getmtime)


def grab_newest_in_folder(folder: str):
    path = newest_image_path(folder)
    return grab_file(path), os.path.basename(path)


def grab_file(path: str):
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Для чтения файла нужен opencv-python. Установите: pip install -r requirements-anpr.txt"
        ) from exc
    frame = cv2.imread(path)
    if frame is None:
        raise RuntimeError(f"Не удалось прочитать файл: {path}")
    return frame


def grab_frame(
    source: str,
    window_title: str = "",
    rtsp_url: str = "",
    http_url: str = "",
    file_path: str = "",
    shots_dir: str = "",
):
    source = (source or "seetong_window").strip().lower()
    if source == "seetong_window":
        info = find_seetong_window(window_title)
        if info is None:
            if shots_dir:
                try:
                    return grab_newest_in_folder(shots_dir)
                except Exception:
                    pass
            raise RuntimeError(
                "Окно Seetong не найдено. Откройте клиент с картинкой камеры "
                "или в источнике выберите «Папка снимков Seetong» / «Камера / IP»."
            )
        frame = grab_window(info)
        if _is_mostly_black(frame) and shots_dir:
            try:
                return grab_newest_in_folder(shots_dir)
            except Exception:
                pass
        if _is_mostly_black(frame):
            raise RuntimeError(
                "Окно Seetong чёрное (видео через видеокарту). "
                "Источник: «Папка снимков Seetong» — сделайте снимок в клиенте. "
                "Или кнопка «Камера / IP», если камера в локальной сети."
            )
        return frame, info.title
    if source == "monitor":
        return grab_monitor(), "monitor"
    if source == "rtsp":
        return grab_rtsp(rtsp_url), "rtsp"
    if source == "http":
        return grab_http_snapshot(http_url), "http"
    if source in ("seetong_folder", "shots"):
        return grab_newest_in_folder(shots_dir or file_path)
    if source == "file":
        return grab_file(file_path), os.path.basename(file_path)
    raise RuntimeError(f"Неизвестный источник: {source}")


def save_screenshot(frame, prefix: str = "shot") -> str:
    os.makedirs(SHOTS_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = os.path.join(SHOTS_DIR, f"{prefix}_{stamp}.jpg")
    try:
        import cv2  # type: ignore

        cv2.imwrite(path, frame)
        return path
    except Exception:
        from PIL import Image  # type: ignore

        rgb = frame[:, :, ::-1]
        Image.fromarray(rgb).save(path, quality=90)
        return path
