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
    if h < 40:
        scale = 48.0 / max(h, 1)
        gray = cv2.resize(gray, (max(int(w * scale), 80), 48), interpolation=cv2.INTER_CUBIC)
    gray = cv2.bilateralFilter(gray, 7, 50, 50)
    mean = float(np.mean(gray))
    if mean < 110:
        gray = cv2.bitwise_not(gray)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9
    )
    return thresh


def find_plate_regions(image, max_candidates: int = 5) -> List[Tuple[Tuple[int, int, int, int], object]]:
    """Return (x0,y0,x1,y1) boxes and BGR crops that look like license plates."""
    import cv2
    import numpy as np

    gray = _to_gray(image)
    h, w = gray.shape[:2]
    gray = cv2.bilateralFilter(gray, 11, 17, 17)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5))
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
        if ch < 14 or cw < 50:
            continue
        aspect = cw / float(ch)
        if not (2.0 <= aspect <= 7.2):
            continue
        area = cw * ch
        if area < 900 or area > 0.45 * w * h:
            continue
        pad_x, pad_y = int(cw * 0.08), int(ch * 0.18)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_y)
        x1 = min(w, x + cw + pad_x)
        y1 = min(h, y + ch + pad_y)
        crop = image[y0:y1, x0:x1]
        closeness = abs(aspect - 4.6)
        scored.append((closeness, area, (x0, y0, x1, y1), crop))

    scored.sort(key=lambda item: (item[0], -item[1]))
    return [(box, crop) for _, _, box, crop in scored[:max_candidates]]


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

    regions = []
    try:
        regions = find_plate_regions(image)
    except Exception:
        regions = []
    if not regions:
        h, w = image.shape[:2]
        regions = [((0, 0, w, h), image)]

    hits: List[PlateHit] = []
    seen = set()
    for bbox, crop in regions:
        engine, raw_hits = _run_ocr(crop)
        if not raw_hits:
            continue
        for raw_text, score in raw_hits:
            if score < min_confidence:
                continue
            for plate in extract_plates(raw_text) or ([normalize_plate(raw_text)] if plate_is_valid(normalize_plate(raw_text)) else []):
                if plate in seen:
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
        # If OCR returned text but regex failed, still keep the compact string
        # only when it looks close (8–9 chars).
        if not hits:
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
