"""Plate-region detection and OCR backends (optional heavy deps)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from anpr.plates import extract_plates, normalize_plate, plate_is_valid


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
    if h >= 64 and w >= 180:
        return crop
    scale_h = max(64 / max(h, 1), 2.8)
    scale_w = max(200 / max(w, 1), 2.2)
    return cv2.resize(
        crop,
        (max(int(w * scale_w), 180), max(int(h * scale_h), 64)),
        interpolation=cv2.INTER_CUBIC,
    )


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
    """Full frame plus lower parking zone tiles for a high-mounted camera."""
    h, w = image.shape[:2]
    views = [((0, 0, w, h), image)]
    y_mid = int(h * 0.28)
    if h - y_mid >= 60:
        views.append(((0, y_mid, w, h), image[y_mid:, :]))
    tile_h = max(h // 2, 80)
    tile_w = max(w // 2, 120)
    step_y = max(tile_h // 2, 40)
    step_x = max(tile_w // 2, 60)
    for y in range(int(h * 0.25), max(h - 40, 1), step_y):
        for x in range(0, max(w - 40, 1), step_x):
            y1 = min(h, y + tile_h)
            x1 = min(w, x + tile_w)
            if y1 - y < 50 or x1 - x < 80:
                continue
            views.append(((x, y, x1, y1), image[y:y1, x:x1]))
            if len(views) >= 8:
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
        h, w = image.shape[:2]
        region_map = [((0, 0, w, h), image)]

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
        region_found = False
        for raw_text, score in raw_hits:
            if score < min_confidence:
                continue
            plates = extract_plates(raw_text)
            if not plates:
                normalized = normalize_plate(raw_text)
                if plate_is_valid(normalized):
                    plates = [normalized]
            for plate in plates:
                if plate in seen:
                    continue
                seen.add(plate)
                region_found = True
                hits.append(
                    PlateHit(
                        plate=plate,
                        confidence=float(score),
                        raw_text=raw_text,
                        bbox=bbox,
                        engine=engine,
                    )
                )
        if not region_found:
            joined = " ".join(text for text, _ in raw_hits)
            compact = normalize_plate(joined)
            if len(compact) in (8, 9) and compact not in seen:
                seen.add(compact)
                hits.append(
                    PlateHit(
                        plate=compact,
                        confidence=max(score for _, score in raw_hits),
                        raw_text=joined,
                        bbox=bbox,
                        engine=engine,
                    )
                )
    hits.sort(key=lambda item: item.confidence, reverse=True)
    return hits
