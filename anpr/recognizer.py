"""Plate-region detection and OCR backends (optional heavy deps)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from anpr.plates import combine_type1_parts, is_osd_text, plate_is_valid


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


def _plate_candidates_from_mask(image, mask, min_aspect: float, max_aspect: float, target_aspect: float):
    import cv2

    h, w = image.shape[:2]
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    scored = []
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        if ch < 7 or cw < 24:
            continue
        aspect = cw / float(ch)
        if not (min_aspect <= aspect <= max_aspect):
            continue
        area = cw * ch
        if area < 150 or area > 0.50 * w * h:
            continue
        pad_x, pad_y = int(cw * 0.10), int(ch * 0.24)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_y)
        x1 = min(w, x + cw + pad_x)
        y1 = min(h, y + ch + pad_y)
        crop = image[y0:y1, x0:x1]
        closeness = abs(aspect - target_aspect)
        vertical_bonus = (y0 + y1) / (2.0 * max(h, 1))
        scored.append((closeness - vertical_bonus * 0.4, -area, (x0, y0, x1, y1), crop))
    return scored


def find_plate_regions(image, max_candidates: int = 8) -> List[Tuple[Tuple[int, int, int, int], object]]:
    """Return boxes that look like Type-1 plates: «А 000 АА | 00», aspect ~4.6."""
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
    scored = _plate_candidates_from_mask(image, closed, 1.8, 8.5, 4.64)

    # White Type-1 plate: light rectangle with a region box on the right.
    # High cameras flatten the plate, so aspect can look wider than 4.6.
    mean = float(np.mean(gray))
    _, light = cv2.threshold(gray, max(int(mean + 20), 135), 255, cv2.THRESH_BINARY)
    light_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5))
    light_closed = cv2.morphologyEx(light, cv2.MORPH_CLOSE, light_kernel, iterations=2)
    scored.extend(_plate_candidates_from_mask(image, light_closed, 2.8, 8.5, 4.64))

    scored.sort(key=lambda item: (item[0], item[1]))
    seen = set()
    out = []
    for _close, _area, box, crop in scored:
        key = (box[0] // 12, box[1] // 12, box[2] // 12, box[3] // 12)
        if key in seen:
            continue
        seen.add(key)
        out.append((box, crop))
        if len(out) >= max_candidates:
            break
    return out


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


def _iter_search_views(image, origin=(0, 0), inside_vehicle: bool = False):
    ox, oy = origin
    if inside_vehicle:
        h, w = image.shape[:2]
        yield (ox, oy), image
        y0 = int(h * 0.30)
        if h - y0 >= 16:
            yield (ox, oy + y0), image[y0:h, :]
        return
    for (x0, y0, _x1, _y1), view in _search_views(image):
        yield (ox + x0, oy + y0), view


def _collect_plate_regions(image, origin=(0, 0), inside_vehicle: bool = False):
    ox, oy = origin
    region_map = []
    seen_boxes = set()
    try:
        for (vx, vy), view in _iter_search_views(image, origin, inside_vehicle):
            for (x0, y0, x1, y1), crop in find_plate_regions(view):
                box = (x0 + vx, y0 + vy, x1 + vx, y1 + vy)
                key = (box[0] // 20, box[1] // 20, box[2] // 20, box[3] // 20)
                if key in seen_boxes:
                    continue
                seen_boxes.add(key)
                region_map.append((box, crop))
                if len(region_map) >= 6:
                    return region_map
    except Exception:
        return region_map
    if not region_map and inside_vehicle:
        h, w = image.shape[:2]
        region_map = [((ox, oy, ox + w, oy + h), image)]
    return region_map


def _ocr_regions(region_map, min_confidence: float) -> List[PlateHit]:
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
        texts = []
        best_score = 0.0
        for raw_text, score in raw_hits:
            if score < min_confidence or is_osd_text(raw_text):
                continue
            texts.append(raw_text)
            best_score = max(best_score, float(score))
        if not texts:
            continue
        raw_joined = " ".join(texts)
        for plate in combine_type1_parts(texts):
            if not plate_is_valid(plate) or plate in seen:
                continue
            seen.add(plate)
            hits.append(
                PlateHit(
                    plate=plate,
                    confidence=best_score,
                    raw_text=raw_joined,
                    bbox=bbox,
                    engine=engine,
                )
            )
    hits.sort(key=lambda item: item.confidence, reverse=True)
    return hits


def recognize_scene(image, min_confidence: float = 0.35):
    """Detect the car silhouette, cut away the rest, read Type-1 plates on the car."""
    from anpr.vehicles import (
        annotate_scene,
        annotate_zoom,
        apply_silhouette_mask,
        bumper_box,
        crop_box,
        find_vehicle_silhouettes,
        zoom_box,
    )

    if image is None or getattr(image, "size", 0) == 0:
        return [], [], image, None

    work = image
    try:
        work = mask_osd(image)
    except Exception:
        work = image

    silhouettes = []
    try:
        silhouettes = find_vehicle_silhouettes(work)
    except Exception:
        silhouettes = []
    vehicles = [item.box for item in silhouettes]

    hits: List[PlateHit] = []
    plate_regions = []
    if silhouettes:
        masked = apply_silhouette_mask(work, silhouettes)
        for item in silhouettes:
            for roi in (bumper_box(item.box), item.box):
                crop = crop_box(masked, roi)
                if crop is None or getattr(crop, "size", 0) == 0:
                    continue
                regions = _collect_plate_regions(crop, origin=(roi[0], roi[1]), inside_vehicle=True)
                plate_regions.extend(regions)
                hits.extend(_ocr_regions(regions, min_confidence))
    else:
        plate_regions = _collect_plate_regions(work, origin=(0, 0), inside_vehicle=False)
        hits = _ocr_regions(plate_regions, min_confidence)

    unique = []
    seen = set()
    for hit in hits:
        if hit.plate in seen:
            continue
        seen.add(hit.plate)
        unique.append(hit)
    unique.sort(key=lambda item: item.confidence, reverse=True)

    zoom_src = None
    if unique and unique[0].bbox:
        zoom_src = unique[0].bbox
    elif plate_regions:
        zoom_src = plate_regions[0][0]

    # Main preview always keeps the live frame with car shape + detection frame.
    try:
        annotated = annotate_scene(image, silhouettes, unique)
    except Exception:
        annotated = image

    zoom = None
    try:
        if unique and unique[0].bbox and silhouettes:
            plate_box = unique[0].bbox
            owner_car = silhouettes[0].box
            for item in silhouettes:
                car_box = item.box
                if car_box[0] <= plate_box[0] <= car_box[2] or car_box[0] <= plate_box[2] <= car_box[2]:
                    owner_car = car_box
                    break
            zoom = annotate_zoom(image, owner_car, silhouettes, unique)
        elif silhouettes:
            zoom = annotate_zoom(image, silhouettes[0].box, silhouettes, unique)
        elif zoom_src:
            zoom = zoom_box(image, zoom_src)
    except Exception:
        zoom = None

    return unique, vehicles, annotated, zoom


def recognize_image(image, min_confidence: float = 0.35) -> List[PlateHit]:
    hits, _vehicles, _vis, _zoom = recognize_scene(image, min_confidence=min_confidence)
    return hits
