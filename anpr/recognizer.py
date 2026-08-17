"""Plate-region detection and OCR backends (optional heavy deps)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from anpr.plates import extract_plates, is_osd_text, plate_is_valid


@dataclass
class PlateHit:
    plate: str
    confidence: float
    raw_text: str
    bbox: Optional[Tuple[int, int, int, int]] = None
    engine: str = ""


def available_engines() -> List[str]:
    engines = []
    try:
        import cv2  # noqa: F401

        engines.append("opencv-detect")
    except ImportError:
        pass
    try:
        import rapidocr_onnxruntime  # noqa: F401

        engines.append("rapidocr")
    except ImportError:
        pass
    try:
        import easyocr  # noqa: F401

        engines.append("easyocr")
    except ImportError:
        pass
    try:
        import pytesseract  # noqa: F401

        engines.append("tesseract")
    except ImportError:
        pass
    return engines


def _to_gray(image):
    import cv2

    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def preprocess_plate_crop(crop):
    import cv2
    import numpy as np

    gray = _to_gray(crop)
    h, w = gray.shape[:2]
    target_h = 72
    # High-mounted cameras flatten plates; stretch height more than width.
    scale_h = max(target_h / max(h, 1), 2.4)
    scale_w = max(220 / max(w, 1), 2.0)
    gray = cv2.resize(
        gray,
        (max(int(w * scale_w), 180), max(int(h * scale_h), target_h)),
        interpolation=cv2.INTER_CUBIC,
    )
    gray = cv2.bilateralFilter(gray, 7, 50, 50)
    mean = float(np.mean(gray))
    if mean < 110:
        gray = cv2.bitwise_not(gray)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9
    )
    return thresh


def _upscale_for_ocr(crop):
    import cv2

    h, w = crop.shape[:2]
    # High-angle plates are small and flattened; always enlarge for OCR.
    scale_h = max(96 / max(h, 1), 3.5)
    scale_w = max(280 / max(w, 1), 3.0)
    out = cv2.resize(
        crop,
        (max(int(w * scale_w), 240), max(int(h * scale_h), 96)),
        interpolation=cv2.INTER_CUBIC,
    )
    gray = _to_gray(out)
    clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    if out.ndim == 2:
        return gray
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def mask_osd(image):
    """Black out timestamp and HD IPCAM 2880x1620 overlay before OCR."""
    if image is None or getattr(image, "size", 0) == 0:
        return image
    out = image.copy()
    h, w = out.shape[:2]
    out[0 : max(int(h * 0.10), 12), 0 : max(int(w * 0.50), 40)] = 0
    out[int(h * 0.86) : h, int(w * 0.45) : w] = 0
    out[int(h * 0.90) : h, :] = 0
    return out


def parking_band(image):
    """Keep the lower parking area where plates are large enough to read."""
    h, w = image.shape[:2]
    y0 = int(h * 0.30)
    y1 = int(h * 0.90)
    x0 = int(w * 0.04)
    x1 = int(w * 0.96)
    if y1 - y0 < 40 or x1 - x0 < 40:
        return (0, 0, w, h), image
    return (x0, y0, x1, y1), image[y0:y1, x0:x1]


def find_plate_regions(image, max_candidates: int = 8) -> List[Tuple[Tuple[int, int, int, int], object]]:
    """Return (x0,y0,x1,y1) boxes and BGR crops that look like license plates."""
    import cv2
    import numpy as np

    gray = _to_gray(image)
    h, w = gray.shape[:2]
    gray = cv2.bilateralFilter(gray, 11, 17, 17)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 4))
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    grad = cv2.Sobel(blackhat, cv2.CV_32F, 1, 0, ksize=-1)
    grad = np.abs(grad)
    grad = cv2.normalize(grad, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    grad = cv2.GaussianBlur(grad, (5, 5), 0)
    _, thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    closed = cv2.dilate(closed, None, iterations=1)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    scored = []
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        if ch < 8 or cw < 28:
            continue
        aspect = cw / float(ch)
        if not (1.8 <= aspect <= 7.5):
            continue
        area = cw * ch
        if area < 220 or area > 0.45 * w * h:
            continue
        pad_x, pad_y = int(cw * 0.10), int(ch * 0.22)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_y)
        x1 = min(w, x + cw + pad_x)
        y1 = min(h, y + ch + pad_y)
        crop = image[y0:y1, x0:x1]
        closeness = abs(aspect - 4.6)
        # Prefer plates in the lower part of a high-angle parking view.
        vertical_bonus = (y0 + y1) / (2.0 * max(h, 1))
        scored.append((closeness - vertical_bonus * 0.4, -area, (x0, y0, x1, y1), crop))

    scored.sort(key=lambda item: (item[0], item[1]))
    return [(box, crop) for _, _, box, crop in scored[:max_candidates]]


def _search_views(image):
    """Parking band plus tiles — skip the distant road and OSD corners."""
    h, w = image.shape[:2]
    (x0, y0, x1, y1), band = parking_band(image)
    views = [((x0, y0, x1, y1), band)]
    bh, bw = band.shape[:2]
    tile_h = max(bh // 2, 90)
    tile_w = max(bw // 2, 140)
    step_y = max(tile_h // 2, 50)
    step_x = max(tile_w // 2, 70)
    for y in range(0, max(bh - 50, 1), step_y):
        for x in range(0, max(bw - 50, 1), step_x):
            yy = min(bh, y + tile_h)
            xx = min(bw, x + tile_w)
            if yy - y < 60 or xx - x < 90:
                continue
            views.append(((x0 + x, y0 + y, x0 + xx, y0 + yy), band[y:yy, x:xx]))
            if len(views) >= 7:
                return views
    return views


class _OcrCache:
    rapidocr = None
    easyocr = None


def _ocr_rapidocr(image) -> List[Tuple[str, float]]:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return []
    if _OcrCache.rapidocr is None:
        _OcrCache.rapidocr = RapidOCR()
    result, _ = _OcrCache.rapidocr(image)
    hits = []
    if not result:
        return hits
    for item in result:
        # item: [box, text, score]
        if len(item) < 3:
            continue
        text = str(item[1])
        try:
            score = float(item[2])
        except (TypeError, ValueError):
            score = 0.5
        hits.append((text, score))
    return hits


def _ocr_easyocr(image) -> List[Tuple[str, float]]:
    try:
        import easyocr
    except ImportError:
        return []
    if _OcrCache.easyocr is None:
        _OcrCache.easyocr = easyocr.Reader(["en", "ru"], gpu=False, verbose=False)
    rgb = image[:, :, ::-1] if image.ndim == 3 else image
    allowlist = "ABEKMHOPCTYXАВЕКМНОРСТУХ0123456789"
    results = _OcrCache.easyocr.readtext(rgb, allowlist=allowlist)
    hits = []
    for _box, text, score in results:
        hits.append((str(text), float(score)))
    return hits


def _ocr_tesseract(image) -> List[Tuple[str, float]]:
    try:
        import pytesseract
        import cv2
    except ImportError:
        return []
    prepared = preprocess_plate_crop(image)
    config = (
        "--psm 7 -c tessedit_char_whitelist="
        "ABEKMHOPCTYXАВЕКМНОРСТУХ0123456789"
    )
    text = pytesseract.image_to_string(prepared, config=config) or ""
    if not text.strip():
        text = pytesseract.image_to_string(image, config="--psm 6") or ""
    return [(text, 0.55 if text.strip() else 0.0)]


def _run_ocr(image) -> Tuple[str, List[Tuple[str, float]]]:
    for name, fn in (
        ("rapidocr", _ocr_rapidocr),
        ("easyocr", _ocr_easyocr),
        ("tesseract", _ocr_tesseract),
    ):
        try:
            hits = fn(image)
        except Exception:
            continue
        if hits:
            return name, hits
    return "", []


def recognize_image(image, min_confidence: float = 0.35) -> List[PlateHit]:
    """Detect plates on a BGR numpy image. Works without OCR (empty list)."""
    if image is None or getattr(image, "size", 0) == 0:
        return []

    try:
        image = mask_osd(image)
    except Exception:
        pass

    region_map = []
    seen_boxes = set()
    try:
        for offset, view in _search_views(image):
            ox, oy, _, _ = offset
            for (x0, y0, x1, y1), crop in find_plate_regions(view):
                box = (x0 + ox, y0 + oy, x1 + ox, y1 + oy)
                key = (box[0] // 20, box[1] // 20, box[2] // 20, box[3] // 20)
                if key in seen_boxes:
                    continue
                seen_boxes.add(key)
                region_map.append((box, crop))
                if len(region_map) >= 8:
                    break
            if len(region_map) >= 8:
                break
    except Exception:
        region_map = []
    if not region_map:
        _off, band = parking_band(image)
        region_map = [(_off, band)]

    hits: List[PlateHit] = []
    seen = set()
    for bbox, crop in region_map:
        try:
            crop = _upscale_for_ocr(crop)
        except Exception:
            pass
        engine, raw_hits = _run_ocr(crop)
        if not raw_hits:
            continue
        for raw_text, score in raw_hits:
            if score < min_confidence:
                continue
            if is_osd_text(raw_text):
                continue
            plates = extract_plates(raw_text)
            if not plates:
                continue
            for plate in plates:
                if not plate_is_valid(plate) or plate in seen:
                    continue
                seen.add(plate)
                hits.append(
                    PlateHit(
                        plate=plate,
                        confidence=float(score),
                        raw_text=raw_text,
                        bbox=bbox,
                        engine=engine,
                    )
                )
    hits.sort(key=lambda item: item.confidence, reverse=True)
    return hits
