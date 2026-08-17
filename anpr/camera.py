"""Direct camera URLs for Seetong / Topsee devices (HTTP snapshot and RTSP)."""

from __future__ import annotations

from typing import Dict, List, Optional
from urllib.parse import quote

SNAPSHOT_PATHS = (
    "/snapshot.cgi",
    "/cgi-bin/snapshot.cgi",
    "/webcapture.jpg?command=snap&channel=1",
    "/tmpfs/auto.jpg",
)

RTSP_PATHS = (
    "/mpeg4",
    "/mpeg4cif",
    "/stream1",
    "/h264/ch1/main/av_stream",
    "/user={user}&password={password}&channel=1&stream=0.sdp",
)


def build_http_url(ip: str, user: str = "admin", password: str = "123456", path: str = "/snapshot.cgi") -> str:
    host = (ip or "").strip().replace("http://", "").replace("https://", "").split("/")[0]
    if not host:
        raise ValueError("Пустой IP камеры")
    user_q = quote(user or "admin", safe="")
    pass_q = quote(password or "", safe="")
    if not path.startswith("/"):
        path = "/" + path
    return f"http://{user_q}:{pass_q}@{host}{path}"


def build_rtsp_url(ip: str, user: str = "admin", password: str = "123456", path: str = "/mpeg4") -> str:
    host = (ip or "").strip().replace("rtsp://", "").split("/")[0]
    if not host:
        raise ValueError("Пустой IP камеры")
    if ":" not in host:
        host = f"{host}:554"
    user_q = quote(user or "admin", safe="")
    pass_q = quote(password or "", safe="")
    filled = path.format(user=user_q, password=pass_q)
    if not filled.startswith("/"):
        filled = "/" + filled
    return f"rtsp://{user_q}:{pass_q}@{host}{filled}"


def probe_http_snapshot(ip: str, user: str = "admin", password: str = "123456") -> Optional[str]:
    from anpr.capture import grab_http_snapshot

    errors: List[str] = []
    for path in SNAPSHOT_PATHS:
        url = build_http_url(ip, user, password, path)
        try:
            frame = grab_http_snapshot(url)
            if frame is not None and getattr(frame, "size", 0) > 0:
                return url
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    return None


def probe_rtsp(ip: str, user: str = "admin", password: str = "123456") -> Optional[str]:
    from anpr.capture import grab_rtsp

    for path in RTSP_PATHS:
        url = build_rtsp_url(ip, user, password, path)
        try:
            frame = grab_rtsp(url)
            if frame is not None and getattr(frame, "size", 0) > 0:
                return url
        except Exception:
            continue
    return None


def connect_camera(ip: str, user: str = "admin", password: str = "123456") -> Dict[str, str]:
    """Try HTTP snapshot first (more reliable for ANPR), then RTSP."""
    http_url = probe_http_snapshot(ip, user, password)
    if http_url:
        return {"source": "http", "http_url": http_url, "rtsp_url": build_rtsp_url(ip, user, password)}
    rtsp_url = probe_rtsp(ip, user, password)
    if rtsp_url:
        return {"source": "rtsp", "rtsp_url": rtsp_url, "http_url": build_http_url(ip, user, password)}
    raise RuntimeError(
        "Камера по IP не открылась. Проверьте, что компьютер в той же сети, "
        "IP верный (в Seetong: устройство → свойства), логин admin, пароль 123456."
    )
