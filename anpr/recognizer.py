"""Plate-region detection and OCR backends (optional heavy deps)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from anpr.plates import combine_type1_parts, extract_plates, is_osd_text, plate_is_valid


@dataclass
class PlateHit:
    plate: str
    confidence: float
    raw_text: str
    bbox: Optional[Tuple[int, int, int, int]] = None
    engine: str = ""


def _plate_is_meaningful(plate: str) -> bool:
    """Reject syntactically valid OCR placeholders such as А000АА00."""
    if not plate_is_valid(plate):
        return False
    compact = "".join(ch for ch in str(plate) if ch.isalnum())
    if len(compact) not in (8, 9):
        return False
    serial = compact[1:4]
    region = compact[6:]
    return serial != "000" and any(ch != "0" for ch in region)


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


def _upscale_for_ocr(crop, max_side: int = 560):
    """Enlarge small plate crops for OCR, but never create a huge image."""
    import cv2
    import numpy as np

    if crop is None or getattr(crop, "size", 0) == 0:
        return crop
    h, w = crop.shape[:2]
    mean0 = float(np.mean(crop))
    tiny = h < 24 or w < 100
    # Night / dark bumper: stretch more so white Type-1 digits reach OCR size.
    target_h = 160 if tiny else 104
    target_w = 420 if tiny else 300
    scale_h = max(target_h / max(h, 1), 2.8 if mean0 < 60 else 2.2)
    scale_w = max(target_w / max(w, 1), 2.5 if mean0 < 60 else 2.0)
    out = cv2.resize(
        crop,
        (max(int(w * scale_w), target_w), max(int(h * scale_h), target_h)),
        interpolation=cv2.INTER_CUBIC,
    )
    oh, ow = out.shape[:2]
    side_cap = max(max_side, 720 if tiny else max_side)
    if max(oh, ow) > side_cap:
        scale = side_cap / float(max(oh, ow))
        out = cv2.resize(
            out,
            (max(int(ow * scale), 120), max(int(oh * scale), 48)),
            interpolation=cv2.INTER_AREA,
        )
    gray = _to_gray(out)
    clip = 4.2 if mean0 < 60 else 2.8
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    if tiny:
        soft = cv2.GaussianBlur(gray, (0, 0), 1.2)
        gray = cv2.addWeighted(gray, 1.9, soft, -0.9, 0)
    else:
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
    # Night: optional invert if plate is still the brightest blob (white on dark bumper).
    if mean0 < 55 and float(np.mean(gray)) < 90:
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    if out.ndim == 2:
        return gray
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def plate_focus_band(image):
    """Upper parking row where this high camera sees parked cars and plates."""
    h, w = image.shape[:2]
    y0 = int(h * 0.10)
    y1 = int(h * 0.62)
    x0 = int(w * 0.02)
    x1 = int(w * 0.98)
    if y1 - y0 < 40 or x1 - x0 < 60:
        return (0, 0, w, h), image
    return (x0, y0, x1, y1), image[y0:y1, x0:x1]


def mask_osd(image):
    """Black out corner camera overlays (HDIPCAM / resolution), keep plates intact."""
    if image is None or getattr(image, "size", 0) == 0:
        return image
    out = image.copy()
    h, w = out.shape[:2]
    # Top-left timestamp / brand.
    out[0 : max(int(h * 0.10), 12), 0 : max(int(w * 0.45), 40)] = 0
    # Bottom-right resolution badge only — do NOT wipe the bumper/plate zone.
    out[int(h * 0.90) : h, int(w * 0.55) : w] = 0
    out[int(h * 0.94) : h, :] = 0
    return out


def parking_band(image):
    """Keep the upper parked-car row; exclude the large puddle below it."""
    h, w = image.shape[:2]
    y0 = int(h * 0.08)
    y1 = int(h * 0.64)
    x0 = int(w * 0.02)
    x1 = int(w * 0.98)
    if y1 - y0 < 40 or x1 - x0 < 40:
        return (0, 0, w, h), image
    return (x0, y0, x1, y1), image[y0:y1, x0:x1]


def _plate_candidates_from_mask(image, mask, min_aspect: float, max_aspect: float, target_aspect: float):
    import cv2
    import numpy as np

    h, w = image.shape[:2]
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    scored = []
    for contour in contours:
        (cx, cy), (rw, rh), angle = cv2.minAreaRect(contour)
        if rw < rh:
            rw, rh = rh, rw
            angle += 90.0
        if rh < 6 or rw < 22:
            continue
        aspect = rw / float(max(rh, 1.0))
        if not (min_aspect <= aspect <= max_aspect):
            continue
        area = rw * rh
        if area < 150 or area > 0.50 * w * h:
            continue

        # Expand in the plate's own coordinate system, then rectify it. OCR now
        # sees a horizontal Type-1 plate even when the car is viewed obliquely.
        expanded = ((cx, cy), (rw * 1.18, rh * 1.65), angle)
        points = cv2.boxPoints(expanded).astype(np.float32)
        sums = points.sum(axis=1)
        diffs = np.diff(points, axis=1).reshape(-1)
        ordered = np.array(
            [
                points[np.argmin(sums)],
                points[np.argmin(diffs)],
                points[np.argmax(sums)],
                points[np.argmax(diffs)],
            ],
            dtype=np.float32,
        )
        out_w = max(32, int(round(rw * 1.18)))
        out_h = max(12, int(round(rh * 1.65)))
        target = np.array(
            [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
            dtype=np.float32,
        )
        matrix = cv2.getPerspectiveTransform(ordered, target)
        crop = cv2.warpPerspective(
            image,
            matrix,
            (out_w, out_h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        x, y, cw, ch = cv2.boundingRect(points.astype(np.int32))
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(w, x + cw), min(h, y + ch)
        if x1 <= x0 or y1 <= y0:
            continue
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


def _search_views(image, max_views: int = 3):
    """Parking band plus a few tiles — skip distant road and OSD corners."""
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
            if len(views) >= max_views:
                return views
    return views


def _iter_search_views(image, origin=(0, 0), inside_vehicle: bool = False):
    """Yield ((vx, vy), view) windows. Origin is the crop offset in the full frame."""
    ox, oy = origin
    if image is None or getattr(image, "size", 0) == 0:
        return
    if inside_vehicle:
        h, w = image.shape[:2]
        # Bumper strip first — smaller crop → much faster OCR on live RTSP.
        y0 = int(h * 0.40)
        if h - y0 >= 36 and w >= 60:
            yield (ox, oy + y0), image[y0:h, :]
            return
        yield (ox, oy), image
        return
    for box, view in _search_views(image, max_views=2):
        x0, y0, _x1, _y1 = box
        yield (ox + x0, oy + y0), view


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


def _rapidocr_installed() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401

        return True
    except ImportError:
        return False


def _run_ocr(image, allow_tesseract: bool = False) -> Tuple[str, List[Tuple[str, float]]]:
    """Run the fastest OCR engine. Live path uses RapidOCR only (budget-limited)."""
    if int(_OCR_BUDGET.get("n", 0)) >= int(_OCR_BUDGET.get("max", 2)):
        return "", []
    _OCR_BUDGET["n"] = int(_OCR_BUDGET.get("n", 0)) + 1

    try:
        hits = _ocr_rapidocr(image)
        if hits:
            return "rapidocr", hits
    except Exception:
        pass

    # Tesseract is slow on CPU — use only when RapidOCR is not installed.
    if allow_tesseract or not _rapidocr_installed():
        try:
            hits = _ocr_tesseract(image)
            if hits:
                return "tesseract", hits
        except Exception:
            pass
    return "", []


_FAST_FRAME = {"n": 0}
_OCR_BUDGET = {"n": 0, "max": 2}


def _collect_plate_regions(image, origin=(0, 0), inside_vehicle: bool = False, max_regions: int = 3):
    ox, oy = origin
    region_map = []
    seen_boxes = set()
    try:
        for (vx, vy), view in _iter_search_views(image, origin, inside_vehicle):
            for (x0, y0, x1, y1), crop in find_plate_regions(view, max_candidates=max_regions):
                box = (x0 + vx, y0 + vy, x1 + vx, y1 + vy)
                key = (box[0] // 20, box[1] // 20, box[2] // 20, box[3] // 20)
                if key in seen_boxes:
                    continue
                seen_boxes.add(key)
                # Keep the exact box for drawing, but OCR a larger bumper context.
                vw, vh = view.shape[1], view.shape[0]
                pw, ph = max(1, x1 - x0), max(1, y1 - y0)
                ex, ey = max(4, int(pw * 0.32)), max(4, int(ph * 0.90))
                ax0, ay0 = max(0, x0 - ex), max(0, y0 - ey)
                ax1, ay1 = min(vw, x1 + ex), min(vh, y1 + ey)
                expanded = view[ay0:ay1, ax0:ax1]
                if expanded is not None and getattr(expanded, "size", 0) > 0:
                    eh, ew = expanded.shape[:2]
                    ch, cw = crop.shape[:2]
                    expanded_aspect = ew / float(max(eh, 1))
                    rectified_aspect = cw / float(max(ch, 1))
                    # Keep the perspective-corrected candidate when the
                    # axis-aligned bumper context would make it too square.
                    if not (rectified_aspect >= 2.5 and expanded_aspect < 2.2):
                        crop = expanded
                region_map.append((box, crop))
                if len(region_map) >= max_regions:
                    return region_map
    except Exception:
        pass
    if not region_map and inside_vehicle:
        h, w = image.shape[:2]
        # Prefer bumper strip over the whole car — OCR is much faster.
        y0 = int(h * 0.40)
        if h - y0 >= 36:
            region_map = [((ox, oy + y0, ox + w, oy + h), image[y0:h, :])]
        else:
            region_map = [((ox, oy, ox + w, oy + h), image)]
    return region_map


def _ocr_regions(region_map, min_confidence: float) -> List[PlateHit]:
    import cv2

    hits: List[PlateHit] = []
    seen = set()
    for bbox, crop in region_map[:3]:
        try:
            prepared = _upscale_for_ocr(crop, max_side=760)
        except Exception:
            prepared = crop
        views = [prepared]
        try:
            gray = _to_gray(prepared)
            # High-contrast second attempt recovers tiny dark glyphs on white.
            binary = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                31,
                7,
            )
            views.append(binary)
        except Exception:
            pass
        for view in views:
            engine, raw_hits = _run_ocr(view)
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
            for plate in combine_type1_parts(texts) or extract_plates(raw_joined):
                if not _plate_is_meaningful(plate) or plate in seen:
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
                # One good plate from this crop is enough — stop early.
                break
            if hits:
                break
        if hits:
            break
    hits.sort(key=lambda item: item.confidence, reverse=True)
    return hits


def _hits_from_ocr_texts(
    texts_scores,
    engine: str,
    bbox,
    min_confidence: float,
) -> List[PlateHit]:
    texts = []
    best = 0.0
    for text, score in texts_scores:
        if score < min_confidence or is_osd_text(text):
            continue
        texts.append(text)
        best = max(best, float(score))
    if not texts:
        return []
    raw_joined = " ".join(texts)
    out: List[PlateHit] = []
    for plate in combine_type1_parts(texts) or extract_plates(raw_joined):
        if not _plate_is_meaningful(plate) or is_osd_text(plate):
            continue
        out.append(
            PlateHit(
                plate=plate,
                confidence=best,
                raw_text=raw_joined,
                bbox=bbox,
                engine=engine or "ocr",
            )
        )
    return out


def _ocr_crop_direct(crop, origin_box, min_confidence: float) -> List[PlateHit]:
    """OCR a crop without plate-region detection (high-camera fallback)."""
    if crop is None or getattr(crop, "size", 0) == 0:
        return []
    try:
        from anpr.vehicles import brighten_crop

        crop = brighten_crop(crop, min_mean=95.0)
    except Exception:
        pass
    try:
        prepared = _upscale_for_ocr(crop, max_side=520)
    except Exception:
        prepared = crop
    engine, raw_hits = _run_ocr(prepared)
    if not raw_hits:
        return []
    x0, y0, x1, y1 = origin_box
    # Prefer a plate-sized box in the lower half of the crop.
    ch = max(1, y1 - y0)
    cw = max(1, x1 - x0)
    bbox = (
        x0 + int(cw * 0.22),
        y0 + int(ch * 0.55),
        x0 + int(cw * 0.78),
        y0 + int(ch * 0.88),
    )
    return _hits_from_ocr_texts(raw_hits, engine, bbox, min_confidence)


def _bind_hits_to_plate_regions(hits: List[PlateHit], region_map, image_shape) -> List[PlateHit]:
    """Replace a broad direct-OCR bbox with the nearest exact plate-region bbox."""
    if not hits or not region_map:
        return hits
    h, w = image_shape[:2]
    frame_area = float(max(h * w, 1))
    boxes = [item[0] for item in region_map if item and item[0]]
    if not boxes:
        return hits
    for hit in hits:
        old = hit.bbox
        broad = old is None
        if old:
            ow, oh = max(1, old[2] - old[0]), max(1, old[3] - old[1])
            aspect = ow / float(oh)
            broad = (
                ow * oh > frame_area * 0.045
                or ow > w * 0.24
                or not (2.0 <= aspect <= 9.0)
            )
        if not broad:
            continue
        if old:
            cx, cy = (old[0] + old[2]) / 2.0, (old[1] + old[3]) / 2.0
        else:
            cx, cy = w / 2.0, h * 0.35
        hit.bbox = min(
            boxes,
            key=lambda box: (
                ((box[0] + box[2]) / 2.0 - cx) ** 2
                + ((box[1] + box[3]) / 2.0 - cy) ** 2
            ),
        )
    return hits


def _tighten_silhouettes_to_recognized_plates(silhouettes, hits, image_shape):
    """Trim a glued car/bin silhouette horizontally around its recognized plate."""
    from anpr.vehicles import VehicleSilhouette, vehicle_box_from_plate

    result = list(silhouettes)
    for hit in hits:
        if not hit.bbox:
            continue
        px0, py0, px1, py1 = hit.bbox
        pcx, pcy = (px0 + px1) / 2.0, (py0 + py1) / 2.0
        matches = []
        for index, item in enumerate(result):
            x0, y0, x1, y1 = item.box
            if x0 <= pcx <= x1 and y0 <= pcy <= y1:
                bw = max(1, x1 - x0)
                distance = abs(pcx - (x0 + x1) / 2.0) / bw
                matches.append((distance, index, bw))

        tight = vehicle_box_from_plate(hit.bbox, image_shape, expand=1.30)
        if matches:
            _distance, index, old_w = min(matches)
            old = result[index]
            tx0, _ty0, tx1, _ty1 = tight
            tight_w = max(1, tx1 - tx0)
            # Preserve an already-good silhouette, but replace a car+bin group.
            if old_w > tight_w * 1.28:
                _ox0, oy0, _ox1, oy1 = old.box
                result[index] = VehicleSilhouette(
                    box=(tx0, oy0, tx1, oy1),
                    contour=None,
                    score=max(float(old.score), 0.95),
                )
        else:
            result.append(VehicleSilhouette(box=tight, contour=None, score=1.0))
    return result


def _credible_plate_region(item, image_shape) -> bool:
    """Require white/neutral plate texture; reject blue bins and paving edges."""
    import cv2
    import numpy as np

    if not item or not item[0]:
        return False
    box, crop = item
    h, w = image_shape[:2]
    x0, y0, x1, y1 = box
    pw, ph = max(1, x1 - x0), max(1, y1 - y0)
    aspect = pw / float(ph)
    crop_aspect = 0.0
    if crop is not None and getattr(crop, "size", 0) > 0:
        crop_aspect = crop.shape[1] / float(max(crop.shape[0], 1))
    if not (2.0 <= aspect <= 9.0 or 2.0 <= crop_aspect <= 9.0):
        return False
    if pw < max(18, int(w * 0.018)) or pw > int(w * 0.22):
        return False
    if not (int(h * 0.10) <= (y0 + y1) / 2.0 <= int(h * 0.64)):
        return False
    if crop is None or getattr(crop, "size", 0) == 0:
        return False
    if crop.ndim == 2:
        gray = crop
        sat = np.zeros_like(gray)
    else:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        sat = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[:, :, 1]
    # A Type-1 plate has neutral/light substrate plus dark character texture.
    neutral = float(np.mean(sat <= 85))
    bright = float(np.mean(gray >= 145))
    texture = float(np.std(gray))
    return neutral >= 0.48 and bright >= 0.08 and texture >= 11.0


def recognize_scene(image, min_confidence: float = 0.35):
    """Detect cars, read Type-1 plates, draw frames; works even if silhouette is weak."""
    import numpy as np

    from anpr.vehicles import (
        annotate_scene,
        annotate_zoom,
        brighten_crop,
        bumper_box,
        crop_box,
        downscale_for_anpr,
        find_vehicle_silhouettes,
        _is_non_vehicle,
    )

    if image is None or getattr(image, "size", 0) == 0:
        return [], [], image, None

    night = False
    try:
        night = float(np.mean(image)) < 70.0
    except Exception:
        night = False

    try:
        # Night: keep a bit more resolution so white plates stay readable.
        # Distant Type-1 plates are only a few pixels high at 640 px. Keep enough
        # detail for characters; plate-region OCR still limits the expensive crops.
        work = downscale_for_anpr(image, max_w=1280)
    except Exception:
        work = image

    # One RapidOCR call per tick; night gets a second bumper/focus attempt.
    _OCR_BUDGET["n"] = 0
    _OCR_BUDGET["max"] = 2 if night else 1
    _FAST_FRAME["n"] = int(_FAST_FRAME.get("n", 0)) + 1

    silhouettes = []
    try:
        silhouettes = find_vehicle_silhouettes(work, max_cars=4)
        silhouettes = [item for item in silhouettes if not _is_non_vehicle(work, item.box)]
    except Exception:
        silhouettes = []

    hits: List[PlateHit] = []
    global_regions = []
    try:
        # Always search the actual upper parking row.  This is independent of
        # silhouette detection, so a missed car frame cannot also hide its plate.
        global_regions = _collect_plate_regions(
            work, origin=(0, 0), inside_vehicle=False, max_regions=6
        )
        h, w = work.shape[:2]
        global_regions = [
            item for item in global_regions if _credible_plate_region(item, work.shape)
        ]
        if silhouettes:
            near_cars = []
            for item in global_regions:
                box = item[0]
                cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
                for car in silhouettes:
                    bx0, by0, bx1, by1 = car.box
                    pad_x = max(8, int((bx1 - bx0) * 0.18))
                    pad_y = max(8, int((by1 - by0) * 0.22))
                    if (
                        bx0 - pad_x <= cx <= bx1 + pad_x
                        and by0 - pad_y <= cy <= by1 + pad_y
                    ):
                        near_cars.append(item)
                        break
            if near_cars:
                global_regions = near_cars
            # OCR the candidate nearest a car's lower center first.
            def _plate_position_score(item):
                box = item[0]
                cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
                scores = []
                for car in silhouettes:
                    bx0, by0, bx1, by1 = car.box
                    bw, bh = max(1, bx1 - bx0), max(1, by1 - by0)
                    tx, ty = (bx0 + bx1) / 2.0, by0 + bh * 0.72
                    scores.append(abs(cx - tx) / bw + abs(cy - ty) / bh)
                return min(scores) if scores else 99.0

            global_regions.sort(key=_plate_position_score)
    except Exception:
        global_regions = []

    def _has_good_plate(items: List[PlateHit]) -> bool:
        return any(_plate_is_meaningful(h.plate) and not is_osd_text(h.plate) for h in items)

    # Fast path: brighten bumper (night), find white plate band, then OCR.
    if silhouettes:
        item = silhouettes[0]
        roi = bumper_box(item.box)
        crop = crop_box(work, roi)
        if crop is not None and getattr(crop, "size", 0) > 0:
            try:
                crop = brighten_crop(crop, min_mean=100.0)
            except Exception:
                pass
            regions = _collect_plate_regions(
                crop, origin=(roi[0], roi[1]), inside_vehicle=True, max_regions=1
            )
            if regions:
                hits.extend(_ocr_regions(regions, min_confidence=max(0.10, min_confidence - 0.12)))
            if not _has_good_plate(hits):
                hits.extend(
                    _ocr_crop_direct(crop, roi, min_confidence=max(0.10, min_confidence - 0.12))
                )

    if not _has_good_plate(hits) and global_regions:
        _OCR_BUDGET["max"] = max(int(_OCR_BUDGET.get("max", 1)), 3)
        hits.extend(
            _ocr_regions(global_regions[:3], min_confidence=max(0.08, min_confidence - 0.16))
        )

    if not _has_good_plate(hits):
        _OCR_BUDGET["max"] = max(int(_OCR_BUDGET.get("max", 1)), 3)
        try:
            (fx0, fy0, fx1, fy1), focus = plate_focus_band(work)
            try:
                focus = brighten_crop(focus, min_mean=95.0)
            except Exception:
                pass
            fh, fw = focus.shape[:2]
            # Parked plates are in the upper-row body/bumper strip, not the puddle.
            mid = focus[int(fh * 0.18) : int(fh * 0.90), :]
            if mid is not None and getattr(mid, "size", 0) > 0:
                my0 = fy0 + int(fh * 0.18)
                mx0 = fx0
                hits.extend(
                    _ocr_crop_direct(
                        mid,
                        (mx0, my0, mx0 + mid.shape[1], my0 + mid.shape[0]),
                        min_confidence=max(0.08, min_confidence - 0.14),
                    )
                )
        except Exception:
            pass

    hits = _bind_hits_to_plate_regions(hits, global_regions, work.shape)

    unique: List[PlateHit] = []
    seen = set()
    for hit in hits:
        if hit.plate in seen:
            continue
        if (
            not _plate_is_meaningful(hit.plate)
            or is_osd_text(hit.plate)
            or is_osd_text(hit.raw_text)
        ):
            continue
        seen.add(hit.plate)
        unique.append(hit)
    unique.sort(key=lambda item: item.confidence, reverse=True)
    unique = unique[:1]

    # Bright plate-like rectangles do not create cars until OCR confirms them.
    # A confirmed plate can add a missing car or trim a car glued to nearby bins.
    if unique:
        silhouettes = _tighten_silhouettes_to_recognized_plates(
            silhouettes, unique, work.shape
        )

    silhouettes = [item for item in silhouettes if not _is_non_vehicle(work, item.box)]
    vehicles = [item.box for item in silhouettes]

    try:
        # Yellow is reserved for an actually recognized plate.
        annotated = annotate_scene(work, silhouettes, unique, plate_candidates=())
    except Exception:
        annotated = work

    zoom = None
    try:
        if unique and unique[0].bbox:
            zoom = annotate_zoom(work, unique[0].bbox, silhouettes, unique[:1])
        elif silhouettes:
            # No plate yet — still show bright bumper close-up, not a black car body.
            zoom = annotate_zoom(work, bumper_box(silhouettes[0].box), silhouettes, [])
    except Exception:
        zoom = None

    return unique, vehicles, annotated, zoom


def recognize_image(image, min_confidence: float = 0.35) -> List[PlateHit]:
    hits, _vehicles, _vis, _zoom = recognize_scene(image, min_confidence=min_confidence)
    return hits
