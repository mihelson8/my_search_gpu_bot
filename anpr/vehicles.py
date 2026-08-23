"""Detect car silhouettes so plates are read only on vehicles, not on OSD/road."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple, Union

Box = Tuple[int, int, int, int]


@dataclass
class VehicleSilhouette:
    """Car outline in image coordinates."""

    box: Box
    contour: Optional[object] = None
    score: float = 0.0


VehicleLike = Union[VehicleSilhouette, Box]


def _as_box(item: VehicleLike) -> Box:
    return item.box if isinstance(item, VehicleSilhouette) else item


def _as_contour(item: VehicleLike):
    return item.contour if isinstance(item, VehicleSilhouette) else None


def _iou(a: Box, b: Box) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1, (ax1 - ax0) * (ay1 - ay0))
    area_b = max(1, (bx1 - bx0) * (by1 - by0))
    return inter / float(area_a + area_b - inter)


def _nms(items: List[VehicleSilhouette], iou_thresh: float = 0.45) -> List[VehicleSilhouette]:
    items = sorted(items, key=lambda item: item.score, reverse=True)
    kept: List[VehicleSilhouette] = []
    for item in items:
        if any(_iou(item.box, other.box) >= iou_thresh for other in kept):
            continue
        kept.append(item)
    return kept


def _box_color_stats(image, box: Box):
    import cv2
    import numpy as np

    x0, y0, x1, y1 = box
    crop = image[y0:y1, x0:x1]
    if crop is None or getattr(crop, "size", 0) == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    if crop.ndim == 2:
        crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    hue = hsv[:, :, 0]
    mean_sat = float(np.mean(sat))
    mean_val = float(np.mean(val))
    vivid = (sat > 55) & (val > 45)
    vivid_ratio = float(np.mean(vivid)) if vivid.size else 0.0
    blue = vivid & (hue >= 85) & (hue <= 145)
    yellow = vivid & (hue >= 8) & (hue <= 45)
    green = ((sat > 35) & (val > 35) & (hue >= 35) & (hue <= 95))
    bin_color_ratio = float(np.mean(blue | yellow | green)) if vivid.size else 0.0
    green_ratio = float(np.mean(green)) if green.size else 0.0
    return mean_sat, mean_val, vivid_ratio, bin_color_ratio, green_ratio


def _looks_like_dumpster(image, box: Box) -> bool:
    """True for garbage bins / grass clumps that must not be framed as cars."""
    x0, y0, x1, y1 = box
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    aspect = bw / float(bh)
    h, w = image.shape[:2]
    area_ratio = (bw * bh) / float(max(h * w, 1))
    mean_sat, mean_val, vivid_ratio, bin_color_ratio, green_ratio = _box_color_stats(image, box)

    # Car-sized blobs are never dumpsters — keep red/blue/black/white cars.
    if area_ratio >= 0.055 and bw >= 70 and bh >= 45:
        return False
    # Partial car at frame edge (tall body fragment).
    if bh >= 70 and bw >= 45 and area_ratio >= 0.02:
        return False

    # Colored plastic bins (blue / yellow / green lids) — compact only.
    if area_ratio < 0.055 and bin_color_ratio >= 0.10 and aspect < 2.6:
        return True
    if green_ratio >= 0.22 and area_ratio < 0.08:
        return True
    if area_ratio < 0.05 and vivid_ratio >= 0.18 and mean_sat >= 45 and aspect < 2.8:
        return True
    cx = (x0 + x1) / 2.0
    near_side = cx < w * 0.14 or cx > w * 0.86
    if near_side and area_ratio < 0.06 and vivid_ratio >= 0.10 and 0.55 <= aspect <= 1.7:
        return True
    if area_ratio < 0.08 and mean_sat >= 40 and vivid_ratio >= 0.12 and aspect < 2.2:
        return True
    return False


def _looks_like_camera_osd(image, box: Box) -> bool:
    """True for HDIPCAM / resolution badges that must never be framed as АВТО."""
    h, w = image.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in box]
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    area_ratio = (bw * bh) / float(max(h * w, 1))
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    # Typical OSD corners on Seetong / HDIPCAM overlays.
    in_br = cx >= w * 0.50 and cy >= h * 0.72
    in_bl = cx <= w * 0.45 and cy >= h * 0.88
    in_tl = cx <= w * 0.55 and cy <= h * 0.20
    in_tr = cx >= w * 0.55 and cy <= h * 0.20
    if not (in_br or in_bl or in_tl or in_tr):
        return False
    # Small / medium corner blob = badge, not a parking car.
    if area_ratio <= 0.14:
        return True
    # Wide thin strip of white text (HDIPCAM 2560X1440).
    aspect = bw / float(bh)
    if bh <= h * 0.22 and aspect >= 2.2:
        return True
    return False


def _looks_like_wet_puddle(image, box: Box) -> bool:
    """True for bright wet-asphalt / sky reflections that must not be АВТО."""
    import cv2
    import numpy as np

    if image is None or getattr(image, "size", 0) == 0:
        return False
    h, w = image.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    if bw < 40 or bh < 30:
        return False
    # Parking-row car bodies start higher than puddle sheets.
    if y0 < int(h * 0.48) and bh >= 50:
        return False
    cy = (y0 + y1) / 2.0
    crop = image[y0:y1, x0:x1]
    if crop is None or getattr(crop, "size", 0) == 0:
        return False
    if crop.ndim == 2:
        crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mean_sat = float(np.mean(sat))
    mean_val = float(np.mean(val))
    std = float(np.std(gray))
    bright = float(np.mean(val >= 160))
    very_bright = float(np.mean(val >= 190))
    ch = gray.shape[0]
    upper = gray[0 : max(int(ch * 0.40), 1), :]
    lower = gray[int(ch * 0.55) : ch, :]
    # Structured car body (darker roof/windshield over bumper) is not a puddle.
    if upper.size and lower.size and float(np.mean(upper)) + 18 < float(np.mean(lower)) and std >= 16:
        return False
    # Sky/water mirror: bright, desaturated, low texture, mid/low in frame.
    if cy >= h * 0.50 and mean_sat <= 42 and mean_val >= 150 and bright >= 0.55 and std <= 24:
        return True
    if cy >= h * 0.52 and very_bright >= 0.45 and mean_sat <= 45 and std <= 28:
        return True
    # Tall stick of wet pavement with almost no upper body structure.
    if (
        bh >= int(bw * 1.20)
        and y0 >= int(h * 0.45)
        and mean_sat <= 50
        and bright >= 0.50
        and std <= 26
    ):
        return True
    return False


def _is_non_vehicle(image, box: Box) -> bool:
    return (
        _looks_like_dumpster(image, box)
        or _looks_like_camera_osd(image, box)
        or _looks_like_wet_puddle(image, box)
    )


def clear_osd_zones(mask):
    """Zero camera OSD corners so they never enter the vehicle silhouette mask."""
    if mask is None or getattr(mask, "size", 0) == 0:
        return mask
    h, w = mask.shape[:2]
    # Match recognizer.mask_osd: corners only — do not wipe the bumper zone.
    mask[0 : max(int(h * 0.12), 8), 0 : max(int(w * 0.50), 40)] = 0
    mask[0 : max(int(h * 0.10), 6), int(w * 0.70) : w] = 0
    mask[int(h * 0.88) : h, int(w * 0.55) : w] = 0
    mask[int(h * 0.94) : h, :] = 0
    return mask

def _car_likeness_score(image, box: Box, base: float = 0.0) -> float:
    """Higher = more like a car from a high parking camera."""
    import cv2
    import numpy as np

    x0, y0, x1, y1 = box
    h, w = image.shape[:2]
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    aspect = bw / float(bh)
    area_ratio = (bw * bh) / float(max(h * w, 1))
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    mean_sat, mean_val, vivid_ratio, bin_color_ratio, green_ratio = _box_color_stats(image, box)

    score = base
    # Top-down / front-high cars: allow near-square bodies.
    if 1.15 <= aspect <= 3.4:
        score += 0.26
    elif 0.85 <= aspect < 1.15:
        score += 0.12
    else:
        score -= 0.12
    score += min(area_ratio, 0.32) * 0.70
    if area_ratio < 0.03:
        score -= 0.20
    score += (cy / max(h, 1)) * 0.12
    if w * 0.12 <= cx <= w * 0.88:
        score += 0.08
    else:
        score -= 0.10
    score -= vivid_ratio * 0.55
    score -= bin_color_ratio * 0.90
    score -= green_ratio * 0.80
    # White / silver cars.
    if mean_sat < 45 and mean_val >= 125:
        score += 0.18
    # Black / dark-blue / dark-gray cars.
    elif mean_sat < 55 and mean_val <= 85:
        score += 0.18
    elif mean_sat < 55:
        score += 0.05
    # Wet glare / puddle sheet — only when the box itself starts mid/low.
    if mean_sat < 40 and mean_val >= 155 and y0 >= int(h * 0.50) and cy >= h * 0.58:
        score -= 0.45
    crop = image[y0:y1, x0:x1]
    if crop is not None and getattr(crop, "size", 0) > 0:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        ch = gray.shape[0]
        upper = gray[0 : max(int(ch * 0.45), 1), :]
        lower = gray[int(ch * 0.55) : ch, :]
        if upper.size and lower.size and float(np.mean(upper)) + 8 < float(np.mean(lower)):
            score += 0.10
        std = float(np.std(gray))
        if std > 18:
            score += 0.05
        elif std < 8:
            # Flat shadow / oil stain — not a car body (keep bright silver panels).
            if not (mean_sat < 50 and mean_val >= 130 and y0 < int(h * 0.55)):
                score -= 0.22
        # Uniform bright sheet = puddle, not a painted body (only mid/low boxes).
        if std < 14 and float(np.mean(gray)) >= 160 and mean_sat < 40 and y0 >= int(h * 0.50):
            score -= 0.35
    return score


# High parking cam: blobs wider than this must be *attempted* to split.
_SPLIT_ATTEMPT_W_RATIO = 0.16
# Absolute reject — almost certainly several cars or the whole lot.
_MAX_GROUP_W_RATIO = 0.62
# Keep frame tight to the body; bumper only needs a thin strip for the plate.
_BUMPER_EXPAND_RATIO = 0.20
_MAX_BOX_ASPECT_H_OVER_W = 1.15
# Cars sit above the wet foreground on a typical Seetong parking cam.
_PARKING_MASK_BOTTOM = 0.78
_PARKING_FRAME_BOTTOM = 0.60


def _is_weak_car_candidate(image, box: Box, score: float, best_score: float | None = None) -> bool:
    """Reject tiny shadows/stains; keep real cars in a packed parking row."""
    h, w = image.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in box]
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    area_ratio = (bw * bh) / float(max(h * w, 1))
    aspect = bw / float(bh)
    cy = (y0 + y1) / 2.0
    if bw < 55 or bh < 40:
        return True
    if area_ratio < 0.015:
        return True
    # Puddle / reflection blobs sit too low in the frame.
    if cy > h * 0.70 or (y1 > int(h * 0.82) and y0 > int(h * 0.50)):
        return True
    if _looks_like_wet_puddle(image, box):
        return True
    # Reject whole-frame / multi-car mega-blobs (group must never be one frame).
    if area_ratio > 0.50 or bw > int(w * 0.85):
        return True
    # Wide+flat = parking row glued together.
    if _looks_like_car_group(box, w, min_width=max(48, int(w * 0.055)), frame_h=h):
        return True
    if aspect < 0.65 or aspect > 4.0:
        return True
    if bh > int(bw * 1.40) + 16 and y1 > int(h * 0.75):
        return True
    if score < 0.16:
        return True
    if best_score is not None and best_score > 0:
        if score < max(0.18, best_score * 0.40):
            return True
    return False


def _column_projection(mask, box: Box):
    """Upper-body column mass for a blob (bumper shadows glue cars below)."""
    import cv2
    import numpy as np

    x0, y0, x1, y1 = [int(v) for v in box]
    bw = x1 - x0
    bh = y1 - y0
    if bw < 10 or bh < 10:
        return None, y0, y0
    y_mid = y0 + max(int(bh * 0.62), 20)
    roi = mask[y0:y_mid, x0:x1]
    if roi is None or getattr(roi, "size", 0) == 0:
        return None, y0, y_mid
    col = (roi > 0).sum(axis=0).astype(np.float32)
    if float(col.max()) < 4:
        return None, y0, y_mid
    k = max(5, min(31, (bw // 25) | 1))
    col = cv2.GaussianBlur(col.reshape(1, -1), (k, 1), 0).ravel()
    return col, y0, y_mid


def _spans_from_active(col, min_width: int) -> list:
    thr = max(float(col.max()) * 0.28, 4.0)
    active = col >= thr
    spans: List[tuple] = []
    start = None
    bw = len(col)
    for i, on in enumerate(active):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= min_width:
                spans.append((start, i))
            start = None
    if start is not None and (bw - start) >= min_width:
        spans.append((start, bw))
    return spans


def _valley_cut_spans(col, min_width: int) -> list:
    """Cut a glued row at deep valleys between car-body peaks."""
    import numpy as np

    col = np.asarray(col, dtype=np.float32)
    n = int(col.size)
    if n < min_width * 2:
        return []
    peak_thr = max(float(col.max()) * 0.40, 5.0)
    valley_thr = max(float(col.max()) * 0.55, 1.0)
    peaks = []
    for i in range(2, n - 2):
        if col[i] < peak_thr:
            continue
        if col[i] >= col[i - 1] and col[i] >= col[i + 1]:
            if not peaks or i - peaks[-1] >= int(min_width * 0.75):
                peaks.append(i)
    if len(peaks) < 2:
        return []
    cuts = [0]
    for a, b in zip(peaks, peaks[1:]):
        if b - a < min_width:
            continue
        seg = col[a:b]
        j = int(np.argmin(seg)) + a
        # Require a real dip (not a flat plateau across one car).
        left_h = float(col[a])
        right_h = float(col[b])
        dip = float(col[j])
        if dip <= valley_thr and dip <= 0.72 * min(left_h, right_h):
            cuts.append(j)
    cuts.append(n)
    spans = []
    for i in range(len(cuts) - 1):
        a, b = cuts[i], cuts[i + 1]
        if b - a >= min_width:
            spans.append((a, b))
    return spans if len(spans) >= 2 else []


def _color_transition_spans(image, box: Box, min_width: int) -> list:
    """Split dark|light car pairs by a sharp brightness jump between bodies."""
    import cv2
    import numpy as np

    if image is None or getattr(image, "size", 0) == 0:
        return []
    x0, y0, x1, y1 = [int(v) for v in box]
    bw = x1 - x0
    bh = y1 - y0
    if bw < min_width * 2 or bh < 20:
        return []
    y_hi = y0 + max(int(bh * 0.62), 18)
    crop = image[y0:y_hi, x0:x1]
    if crop is None or getattr(crop, "size", 0) == 0:
        return []
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    col = gray.mean(axis=0).astype(np.float32)
    # Light blur only — strong blur erases the dark|light car boundary.
    k = max(3, min(9, (bw // 40) | 1))
    col = cv2.GaussianBlur(col.reshape(1, -1), (k, 1), 0).ravel()
    grad = np.abs(np.diff(col))
    if grad.size < min_width:
        return []
    # Absolute jump — percentile alone fires on windshield reflections.
    thr = max(14.0, float(np.percentile(grad, 85)))
    cuts = []
    i = min_width
    while i < bw - min_width:
        if grad[i - 1] >= thr and (not cuts or i - cuts[-1] >= min_width):
            lo = max(min_width, i - 6)
            hi = min(bw - min_width, i + 7)
            j = lo + int(np.argmax(grad[lo:hi]))
            cut = j + 1
            # Real dark|light pair: plateaus on each side must differ a lot.
            left = float(col[max(0, cut - min_width) : cut].mean())
            right = float(col[cut : min(bw, cut + min_width)].mean())
            if grad[j] >= thr and abs(left - right) >= 35.0:
                cuts.append(cut)
                i = cut + min_width
                continue
        i += 1
    if not cuts:
        return []
    edges = [0] + cuts + [bw]
    spans = []
    for a, b in zip(edges, edges[1:]):
        if b - a >= min_width:
            spans.append((a, b))
    return spans if len(spans) >= 2 else []


def _geometric_spans(bw: int, min_width: int, frame_w: int) -> list:
    """Last resort: tile a mega-blob into car-width slices (never keep a group box)."""
    target = max(min_width, int(frame_w * 0.10))
    target = min(target, max(min_width, int(bw / 2)))
    n = max(2, int(round(bw / float(target))))
    # Cap slice count so tiny shreds are not emitted.
    n = min(n, max(2, bw // min_width))
    if n < 2:
        return []
    step = bw / float(n)
    spans = []
    for i in range(n):
        a = int(round(i * step))
        b = int(round((i + 1) * step))
        if b - a >= min_width:
            spans.append((a, b))
    return spans if len(spans) >= 2 else []


def _boxes_from_spans(mask, box: Box, spans, y_mid: int) -> List[Box]:
    x0, y0, x1, y1 = [int(v) for v in box]
    bh = y1 - y0
    boxes: List[Box] = []
    for a, b in spans:
        xa = max(0, x0 + int(a) - 2)
        xb = min(mask.shape[1], x0 + int(b) + 2)
        tight = _tighten_box_to_mask(mask, (xa, y0, xb, min(y1, y_mid + int(bh * 0.10))))
        tw = max(1, tight[2] - tight[0])
        th = max(1, tight[3] - tight[1])
        max_h = max(int(tw * _MAX_BOX_ASPECT_H_OVER_W), 48)
        if th > max_h:
            tight = (tight[0], tight[1], tight[2], tight[1] + max_h)
        boxes.append(tight)
    return boxes


def _looks_like_car_group(box: Box, frame_w: int, col=None, min_width: int = 55, frame_h: int | None = None) -> bool:
    """True when a blob is almost certainly several cars glued together."""
    x0, y0, x1, y1 = [int(v) for v in box]
    bw = max(1, x1 - x0)
    bh = max(1, y1 - y0)
    # separate_row / frame clamp shorten height — restore for geometry checks.
    bh_eff = max(bh, int(bh * 1.25) + 10, int(bw * 0.48))
    if frame_h:
        bh_eff = min(bh_eff, max(1, frame_h - y0))
    aspect_eff = bw / float(bh_eff)
    # Close-up single car: fills much of a small/medium frame.
    if frame_h and bw >= int(frame_w * 0.40) and bh_eff >= int(frame_h * 0.22) and aspect_eff < 2.6:
        return False
    if frame_h and bh_eff >= int(frame_h * 0.32) and bw <= int(frame_w * 0.72) and aspect_eff < 2.5:
        return False
    # Still wider than ~2.3 car-heights after restoring body height → several cars.
    if bw >= int(frame_w * 0.22) and aspect_eff >= 2.30:
        return True
    if bw >= int(frame_w * 0.34) and aspect_eff >= 2.05:
        return True
    if col is not None and len(col) >= min_width * 2:
        act = _spans_from_active(col, min_width=min_width)
        if len(act) >= 2:
            return True
    return False


def _column_split_boxes(
    mask, box: Box, min_width: int = 55, frame_w: int | None = None, image=None
) -> List[Box]:
    """Split a wide blob (parking row glued by shadows) into per-car boxes."""
    x0, y0, x1, y1 = [int(v) for v in box]
    bw = x1 - x0
    bh = y1 - y0
    if frame_w is None:
        frame_w = mask.shape[1]
    frame_h = mask.shape[0]
    if bw < min_width * 2 or bh < 20:
        return [box]
    col, _y0, y_mid = _column_projection(mask, box)
    if col is None:
        return [box]

    # True gaps in the mask are safe only when they separate solid bodies.
    spans = _spans_from_active(col, min_width=min_width)
    is_group = _looks_like_car_group(
        box, frame_w, col=col, min_width=min_width, frame_h=frame_h
    )
    if len(spans) >= 2:
        covered = sum(max(0, b - a) for a, b in spans)
        # Hollow single car (windshield hole) covers little of the blob width.
        if covered < int(bw * 0.55) and not is_group:
            spans = []
    # Dark|light neighbours: cut on a sharp brightness jump even without a mask gap.
    if len(spans) < 2:
        color_spans = _color_transition_spans(image, box, min_width=min_width)
        if len(color_spans) >= 2:
            spans = color_spans
            is_group = True
    # Peak/valley/geometric cuts only when the blob looks like several cars —
    # otherwise a single body (windshield dip) gets shredded.
    if len(spans) < 2 and is_group:
        spans = _valley_cut_spans(col, min_width=min_width)
        if len(spans) < 2:
            spans = _peak_spans(col, min_width=min_width)
        if len(spans) < 2:
            spans = _geometric_spans(bw, min_width=min_width, frame_w=frame_w)
    if len(spans) < 2:
        return [box]
    return _boxes_from_spans(mask, box, spans, y_mid)


def _force_split_to_cars(
    mask, box: Box, min_width: int, frame_w: int, depth: int = 0, image=None
) -> List[Box]:
    """Recursively split group blobs; keep a single close-up car intact."""
    x0, y0, x1, y1 = [int(v) for v in box]
    bw = max(1, x1 - x0)
    bh = max(1, y1 - y0)
    frame_h = mask.shape[0]
    soft_max = max(min_width + 8, int(frame_w * _SPLIT_ATTEMPT_W_RATIO))
    col, _y0, y_mid = _column_projection(mask, box)
    is_group = _looks_like_car_group(
        box, frame_w, col=col, min_width=min_width, frame_h=frame_h
    )
    if not is_group and image is not None and bw > soft_max:
        if len(_color_transition_spans(image, box, min_width=min_width)) >= 2:
            is_group = True
    if depth >= 5:
        return [] if is_group else [box]
    if bw <= soft_max and not is_group:
        return [box]
    subs = _column_split_boxes(mask, box, min_width=min_width, frame_w=frame_w, image=image)
    if len(subs) < 2:
        if not is_group:
            return [box]  # one wide car — do not tile by width alone
        spans = _geometric_spans(bw, min_width=min_width, frame_w=frame_w)
        if len(spans) < 2:
            return []  # drop unsplittable group rather than frame several cars as one
        if col is None:
            y_mid = y0 + max(int(bh * 0.58), 20)
        subs = _boxes_from_spans(mask, box, spans, y_mid)
    out: List[Box] = []
    for sub in subs:
        sw = max(1, sub[2] - sub[0])
        if sw <= soft_max and not _looks_like_car_group(
            sub, frame_w, min_width=min_width, frame_h=frame_h
        ):
            out.append(sub)
        else:
            out.extend(
                _force_split_to_cars(mask, sub, min_width, frame_w, depth + 1, image=image)
            )
    return out


def _peak_spans(col, min_width: int = 55) -> list:
    """Fallback span finder using peaks of a column projection."""
    import numpy as np

    col = np.asarray(col, dtype=np.float32)
    if col.size < min_width * 2:
        return []
    thr = max(float(col.max()) * 0.35, 5.0)
    peaks = []
    for i in range(2, len(col) - 2):
        if col[i] >= thr and col[i] >= col[i - 1] and col[i] >= col[i + 1]:
            if not peaks or i - peaks[-1] >= int(min_width * 0.85):
                peaks.append(i)
    if len(peaks) < 2:
        return []
    spans = []
    # Midpoints between peaks define car boundaries better than fixed half-width.
    edges = [0]
    for a, b in zip(peaks, peaks[1:]):
        edges.append((a + b) // 2)
    edges.append(len(col))
    for i in range(len(edges) - 1):
        a, b = edges[i], edges[i + 1]
        if b - a >= min_width:
            spans.append((a, b))
    return spans if len(spans) >= 2 else []


def _tighten_box_to_mask(mask, box: Box) -> Box:
    """Shrink a box to the actual mask mass (drop empty shadow padding)."""
    import numpy as np

    h, w = mask.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    roi = mask[y0:y1, x0:x1]
    if roi is None or getattr(roi, "size", 0) == 0 or int(roi.max()) == 0:
        return (x0, y0, x1, y1)
    rows = np.any(roi > 0, axis=1)
    cols = np.any(roi > 0, axis=0)
    if not rows.any() or not cols.any():
        return (x0, y0, x1, y1)
    ry = np.where(rows)[0]
    cx = np.where(cols)[0]
    return (x0 + int(cx[0]), y0 + int(ry[0]), x0 + int(cx[-1]) + 1, y0 + int(ry[-1]) + 1)


def _include_bumper_plate(image, box: Box, max_extra: int) -> Box:
    """Grow the bottom slightly for a Type-1 plate — never chase wet-asphalt glare."""
    import cv2
    import numpy as np

    if image is None or getattr(image, "size", 0) == 0 or max_extra <= 0:
        return box
    h, w = image.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, x1 = max(0, x0), min(w, x1)
    bw = max(1, x1 - x0)
    if bw < 20:
        return box
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    limit = min(h, y1 + max_extra, int(h * _PARKING_MASK_BOTTOM) + 8)
    best = y1
    miss = 0
    for y in range(y1, limit):
        row = gray[y, x0:x1]
        bright = float((row >= 195).mean())
        dark = float((row <= 70).mean())
        # Full-width mirror / puddle glare — stop immediately.
        if bright >= 0.78:
            on = (row >= 195).astype(np.uint8)
            # Count longest bright run; puddles span almost the whole box.
            longest = 0
            run = 0
            for v in on:
                if v:
                    run += 1
                    longest = max(longest, run)
                else:
                    run = 0
            if longest >= int(0.78 * bw):
                break
        plate_like = False
        if 0.10 <= bright <= 0.85:
            # Plate is a compact bright run, not a puddle sheet.
            on = (row >= 195).astype(np.uint8)
            runs = []
            start = None
            for i, v in enumerate(on):
                if v and start is None:
                    start = i
                elif not v and start is not None:
                    runs.append(i - start)
                    start = None
            if start is not None:
                runs.append(len(on) - start)
            longest = max(runs) if runs else 0
            if 0.10 * bw <= longest <= 0.85 * bw:
                plate_like = True
        bumper_like = dark >= 0.45 and bright < 0.40
        if plate_like or bumper_like:
            best = y + 1
            miss = 0
        else:
            miss += 1
            if miss >= 3 and y > y1 + 4:
                break
    return (x0, y0, x1, best)


def _fit_box_to_car_body(mask, box: Box, full_mask=None, image=None) -> Box:
    """Shrink a detection to the dense car body; keep a thin bumper/plate strip."""
    src = full_mask if full_mask is not None else mask
    if src is None or getattr(src, "size", 0) == 0:
        return box
    h, w = src.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 - x0 < 20 or y1 - y0 < 20:
        return (x0, y0, x1, y1)

    x0, y0, x1, y1 = _tighten_dense_xy(src, (x0, y0, x1, y1), row_thr=0.14, col_thr=0.12)
    bw = max(1, x1 - x0)
    body_h = max(1, y1 - y0)
    bump = max(8, int(body_h * _BUMPER_EXPAND_RATIO))
    y1 = min(h, y1 + bump)
    box = _include_bumper_plate(image, (x0, y0, x1, y1), max_extra=max(16, int(body_h * 0.40)))
    x0, y0, x1, y1 = box
    max_h = max(int(bw * _MAX_BOX_ASPECT_H_OVER_W), 48)
    if (y1 - y0) > max_h:
        y1 = y0 + max_h
    # Clamp out of the wet foreground for high parking-row cameras.
    if y0 < int(h * 0.40) and (x1 - x0) < int(w * 0.55):
        y1 = min(y1, int(h * _PARKING_FRAME_BOTTOM))
    if y1 - y0 < 40:
        y1 = min(h, y0 + 40)
    return (x0, y0, x1, y1)


def _tighten_dense_xy(mask, box: Box, row_thr: float = 0.12, col_thr: float = 0.10) -> Box:
    """Keep only rows/cols with enough mask mass (drop sparse shadow)."""
    import numpy as np

    h, w = mask.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    roi = mask[y0:y1, x0:x1] > 0
    if roi.size == 0 or not roi.any():
        return (x0, y0, x1, y1)
    row_frac = roi.mean(axis=1)
    col_frac = roi.mean(axis=0)
    r_thr = max(row_thr, float(row_frac.max()) * 0.30)
    c_thr = max(col_thr, float(col_frac.max()) * 0.24)
    rows = np.where(row_frac >= r_thr)[0]
    cols = np.where(col_frac >= c_thr)[0]
    if rows.size == 0 or cols.size == 0:
        return _tighten_box_to_mask(mask, (x0, y0, x1, y1))
    return (
        x0 + int(cols[0]),
        y0 + int(rows[0]),
        x0 + int(cols[-1]) + 1,
        y0 + int(rows[-1]) + 1,
    )


def _separate_row_mask(mask):
    """Clear wet foreground; break thin bridges between adjacent cars."""
    import cv2

    if mask is None or getattr(mask, "size", 0) == 0:
        return mask
    out = mask.copy()
    h, w = out.shape[:2]
    # Hard cut: deep foreground puddle reflections are not car bodies.
    out[int(h * _PARKING_MASK_BOTTOM) : h, :] = 0
    k_bridge = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 17))
    return cv2.morphologyEx(out, cv2.MORPH_OPEN, k_bridge, iterations=1)


def _silhouettes_from_mask(
    mask, image_shape, min_ratio: float, max_ratio: float, image=None
) -> List[VehicleSilhouette]:
    import cv2
    import numpy as np

    h, w = image_shape[:2]
    frame_area = float(h * w)
    work = _separate_row_mask(mask)
    contours, _ = cv2.findContours(work, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found: List[VehicleSilhouette] = []

    def _add_box(box: Box, contour=None) -> None:
        # Fit to dense body on the full tone mask (keeps bumper, drops puddles).
        box = _fit_box_to_car_body(work, box, full_mask=mask, image=image)
        x0, y0, x1, y1 = box
        bw, bh = max(1, x1 - x0), max(1, y1 - y0)
        if bw < 55 or bh < 40:
            return
        aspect = bw / float(bh)
        cy = (y0 + y1) / 2.0
        # Puddle-only / reflection frames (center deep in the wet foreground).
        if cy > h * 0.70 and y0 > int(h * 0.48):
            return
        if bh > int(bw * 1.35) + 12 and y1 > int(h * 0.72):
            return
        # Never accept a multi-car group as one detection (width alone is OK for close-ups).
        if _looks_like_car_group((x0, y0, x1, y1), w, min_width=max(48, int(w * 0.055)), frame_h=h):
            return
        if bw > int(w * 0.82):
            return
        ratio = (bw * bh) / frame_area
        if ratio < min_ratio or ratio > min(max_ratio, 0.42):
            return
        # High-angle front view can look nearly square / slightly tall.
        if not (0.70 <= aspect <= 4.0):
            return
        if image is not None and _is_non_vehicle(image, box):
            return
        score = ratio + ((y0 + y1) / 2.0 / max(h, 1)) * 0.08
        if image is not None:
            score = _car_likeness_score(image, box, base=score)
        if score < 0.14:
            return
        if image is not None and _looks_like_camera_osd(image, box):
            return
        found.append(VehicleSilhouette(box=box, contour=contour, score=score))

    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        if cw < 55 or ch < 40:
            continue
        # Contours that live mostly in the wet foreground are reflections.
        if (y + ch / 2.0) > h * 0.70 and y > int(h * 0.50):
            continue
        area = cw * ch
        ratio = area / frame_area
        pad_x, pad_y = int(cw * 0.02), int(ch * 0.02)
        box = (
            max(0, x - pad_x),
            max(0, y - pad_y),
            min(w, x + cw + pad_x),
            min(h, y + ch + pad_y),
        )
        # Any blob that may be several cars must be split before framing.
        min_w = max(44, int(w * 0.05))
        need_split = (
            cw > int(w * _SPLIT_ATTEMPT_W_RATIO)
            or (cw >= max(120, int(w * 0.22)) and cw >= int(ch * 1.45))
            or (ratio > max_ratio and cw > int(ch * 1.8))
            or _looks_like_car_group(box, w, min_width=min_w, frame_h=h)
        )
        if need_split:
            subs = _force_split_to_cars(
                work, box, min_width=min_w, frame_w=w, image=image
            )
            if len(subs) >= 2:
                for sub in subs:
                    _add_box(sub, contour=None)
                continue
            # Unsplittable multi-car blob — never emit as one АВТО.
            if _looks_like_car_group(box, w, min_width=min_w, frame_h=h):
                continue
        if ratio < min_ratio or ratio > max_ratio:
            continue
        if cw > int(w * 0.82):
            continue
        hull = cv2.contourArea(cv2.convexHull(contour)) or 1.0
        solidity = (cv2.contourArea(contour) or 0.0) / hull
        if solidity < 0.22:
            continue
        cy = y + ch / 2.0
        if cy < h * 0.18:
            continue
        _add_box(box, contour=contour)
    return found


def find_vehicle_silhouettes(image, max_cars: int = 6) -> List[VehicleSilhouette]:
    """Find car shapes in a parking row (light and dark) and frame real cars."""
    if image is None or getattr(image, "size", 0) == 0:
        return []
    found: List[VehicleSilhouette] = []
    dark = light = None
    try:
        dark, light = _car_tone_masks(image)
        found.extend(
            _silhouettes_from_mask(dark, image.shape, min_ratio=0.012, max_ratio=0.55, image=image)
        )
        found.extend(
            _silhouettes_from_mask(light, image.shape, min_ratio=0.012, max_ratio=0.55, image=image)
        )
    except Exception:
        pass
    found = [item for item in found if not _is_non_vehicle(image, item.box)]
    if not found:
        # Edge fallback only when tonal masks are almost empty (not a full parking row).
        try:
            import numpy as np

            fg = 0.0
            if dark is not None and light is not None:
                fg = float(((dark > 0) | (light > 0)).mean())
            if fg < 0.04:
                edges = _edge_car_mask(image)
                found.extend(
                    _silhouettes_from_mask(
                        edges, image.shape, min_ratio=0.020, max_ratio=0.45, image=image
                    )
                )
        except Exception:
            pass
        found = [item for item in found if not _is_non_vehicle(image, item.box)]
    if not found:
        return []
    kept = _nms(found, iou_thresh=0.38)
    kept.sort(key=lambda item: item.score, reverse=True)
    best = kept[0].score
    strong = [
        item
        for item in kept
        if not _is_weak_car_candidate(image, item.box, item.score, best_score=best)
    ]
    if not strong and kept:
        if not _is_weak_car_candidate(image, kept[0].box, kept[0].score, best_score=None):
            strong = [kept[0]]
    # Parking rows need more than 4 frames; still cap runaway detections.
    limit = max(1, min(int(max_cars), 8))
    return strong[:limit]


def _foreground_mask(image):
    """Deprecated single mask — kept for tests; prefer dark/light split masks."""
    dark, light = _car_tone_masks(image)
    import cv2

    return cv2.bitwise_or(dark, light)


def _car_tone_masks(image):
    """Return (dark_body_mask, light_body_mask) ignoring wet asphalt grain."""
    import cv2
    import numpy as np

    h, w = image.shape[:2]
    target_w = 420
    scale = target_w / float(max(w, 1))
    small_w = max(int(w * scale), 100)
    small_h = max(int(h * scale), 70)
    small = cv2.resize(image, (small_w, small_h), interpolation=cv2.INTER_AREA)
    if small.ndim == 2:
        small = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    # Median blur removes wet-lot speckles better than Gaussian.
    soft = cv2.medianBlur(gray, 21)
    sh, sw = soft.shape[:2]

    # Asphalt = dominant tone in the parking band (ignore bright sky/OSD).
    parking = soft[int(sh * 0.22) : sh, :]
    hist = np.bincount(parking.ravel(), minlength=256).astype(np.float64)
    # Soften histogram so a large dark car does not steal the mode alone.
    hist = np.convolve(hist, np.ones(9) / 9.0, mode="same")
    bg = float(int(np.argmax(hist)))
    # Fallback: side gutters if mode looks empty.
    sides = np.concatenate(
        [
            soft[int(sh * 0.30) : int(sh * 0.90), 0 : max(sw // 12, 3)].ravel(),
            soft[int(sh * 0.30) : int(sh * 0.90), max(sw - sw // 12, 0) : sw].ravel(),
        ]
    )
    if sides.size:
        side_bg = float(np.median(sides))
        if abs(side_bg - bg) < 35:
            bg = side_bg
    bg_std = float(np.std(sides)) if sides.size else 10.0
    # Noisy lots need a larger gap so texture is not a "car".
    dark_gap = max(18, int(14 + bg_std * 0.55))
    light_gap = max(20, int(16 + bg_std * 0.55))

    darker = np.clip(int(round(bg)) - soft.astype(np.int16), 0, 255).astype(np.uint8)
    brighter = np.clip(soft.astype(np.int16) - int(round(bg)), 0, 255).astype(np.uint8)
    _, mask_dark = cv2.threshold(darker, dark_gap, 255, cv2.THRESH_BINARY)
    _, mask_light = cv2.threshold(brighter, light_gap, 255, cv2.THRESH_BINARY)

    pale_lo = max(int(bg + light_gap), 125)
    pale = cv2.inRange(hsv, (0, 0, pale_lo), (180, 80, 255))
    dark_hi = max(int(bg - dark_gap), 65)
    dark_body = cv2.inRange(hsv, (0, 0, 0), (180, 110, dark_hi))

    dark = cv2.bitwise_or(mask_dark, dark_body)
    light = cv2.bitwise_or(mask_light, pale)

    # Remove only small vivid dumpster components from both masks.
    vivid = cv2.inRange(hsv, (8, 75, 65), (40, 255, 255))
    vivid = cv2.bitwise_or(vivid, cv2.inRange(hsv, (95, 75, 65), (135, 255, 255)))
    vivid = cv2.bitwise_or(vivid, cv2.inRange(hsv, (40, 60, 50), (85, 255, 255)))
    vivid_n, _lbl, vivid_stats, _ = cv2.connectedComponentsWithStats(vivid, connectivity=8)
    for i in range(1, vivid_n):
        area = int(vivid_stats[i, cv2.CC_STAT_AREA])
        if area >= 0.04 * sh * sw:
            continue
        x = int(vivid_stats[i, cv2.CC_STAT_LEFT])
        y = int(vivid_stats[i, cv2.CC_STAT_TOP])
        ww = int(vivid_stats[i, cv2.CC_STAT_WIDTH])
        hh = int(vivid_stats[i, cv2.CC_STAT_HEIGHT])
        patch = vivid[y : y + hh, x : x + ww] > 0
        dark[y : y + hh, x : x + ww][patch] = 0
        light[y : y + hh, x : x + ww][patch] = 0

    clear_osd_zones(dark)
    clear_osd_zones(light)
    # Kill wet-asphalt specular glare in the foreground (reflections ≠ cars).
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    yy = np.arange(sh, dtype=np.int32)[:, None]
    wet = (sat < 35) & (val > 180) & (yy >= int(sh * 0.64))
    dark[wet] = 0
    light[wet] = 0
    # Hard parking-band cut on the small masks before upscale.
    dark[int(sh * _PARKING_MASK_BOTTOM) :, :] = 0
    light[int(sh * _PARKING_MASK_BOTTOM) :, :] = 0
    # Mild close — large kernels glue a packed parking row into one blob.
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, k_close, iterations=1)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, k_open, iterations=1)
    light = cv2.morphologyEx(light, cv2.MORPH_CLOSE, k_close, iterations=1)
    light = cv2.morphologyEx(light, cv2.MORPH_OPEN, k_open, iterations=1)

    dark = cv2.resize(dark, (w, h), interpolation=cv2.INTER_NEAREST)
    light = cv2.resize(light, (w, h), interpolation=cv2.INTER_NEAREST)
    dark[int(h * _PARKING_MASK_BOTTOM) :, :] = 0
    light[int(h * _PARKING_MASK_BOTTOM) :, :] = 0
    return clear_osd_zones(dark), clear_osd_zones(light)


def _edge_car_mask(image):
    """Fallback outline mask when asphalt texture hides tonal car blobs."""
    import cv2

    h, w = image.shape[:2]
    target_w = 420
    scale = target_w / float(max(w, 1))
    small = cv2.resize(
        image,
        (max(int(w * scale), 100), max(int(h * scale), 70)),
        interpolation=cv2.INTER_AREA,
    )
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
    blur = cv2.medianBlur(gray, 7)
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=2)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    filled = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=3)
    clear_osd_zones(filled)
    return cv2.resize(filled, (w, h), interpolation=cv2.INTER_NEAREST)


def find_vehicle_rois(image, max_cars: int = 6) -> List[Box]:
    """Return bounding boxes (x0,y0,x1,y1) of car silhouettes."""
    return [item.box for item in find_vehicle_silhouettes(image, max_cars=max_cars)]


def crop_box(image, box: Box):
    x0, y0, x1, y1 = box
    return image[y0:y1, x0:x1]


def bumper_box(box: Box) -> Box:
    """Lower part of the car silhouette — where the Type-1 plate sits."""
    x0, y0, x1, y1 = box
    h = max(1, y1 - y0)
    return (x0, y0 + int(h * 0.32), x1, y1)


def vehicle_box_from_plate(plate_box: Box, image_shape, expand: float = 3.2) -> Box:
    """Guess a car frame around a found plate when silhouette detection failed."""
    h, w = image_shape[:2]
    x0, y0, x1, y1 = [int(v) for v in plate_box]
    pw = max(8, x1 - x0)
    ph = max(6, y1 - y0)
    bx0 = max(0, int(x0 - pw * expand))
    by0 = max(0, int(y0 - ph * (expand + 0.8)))
    bx1 = min(w, int(x1 + pw * expand))
    by1 = min(h, int(y1 + ph * 1.4))
    if bx1 - bx0 < 40 or by1 - by0 < 30:
        return (max(0, x0 - 40), max(0, y0 - 80), min(w, x1 + 40), min(h, y1 + 40))
    return (bx0, by0, bx1, by1)


def downscale_for_anpr(image, max_w: int = 1280):
    """Shrink huge RTSP frames so silhouette + OCR finish much faster."""
    import cv2

    if image is None or getattr(image, "size", 0) == 0:
        return image
    h, w = image.shape[:2]
    if w <= max_w:
        return image
    scale = max_w / float(w)
    return cv2.resize(image, (max_w, max(int(h * scale), 1)), interpolation=cv2.INTER_AREA)


def brighten_crop(crop, min_mean: float = 78.0):
    """Lift dark RTSP / night crops so white Type-1 digits stay readable."""
    import cv2
    import numpy as np

    if crop is None or getattr(crop, "size", 0) == 0:
        return crop
    mean = float(np.mean(crop))
    if mean >= min_mean:
        return crop
    out = crop.copy()
    # Stronger CLAHE at night (mean often < 40 on dark cars).
    clip = 4.5 if mean < 55 else 3.2
    if out.ndim == 2:
        clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
        return clahe.apply(out)
    lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
    l_ch = clahe.apply(l_ch)
    merged = cv2.merge([l_ch, a_ch, b_ch])
    out = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
    mean2 = float(np.mean(out))
    if mean2 < min_mean:
        gain = min(min_mean / max(mean2, 1.0), 2.4 if mean < 45 else 1.85)
        out = np.clip(out.astype(np.float32) * gain, 0, 255).astype(np.uint8)
    return out


def zoom_box(image, box: Box, min_w: int = 520, min_h: int = 140, pad: float = 0.28):
    """Crop around a plate/car box and enlarge it so the Type-1 number is readable."""
    import cv2

    if image is None or getattr(image, "size", 0) == 0 or not box:
        return image
    h, w = image.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in box]
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    pad_x = int(bw * pad) + 6
    pad_y = int(bh * pad) + 8
    x0 = max(0, x0 - pad_x)
    y0 = max(0, y0 - pad_y)
    x1 = min(w, x1 + pad_x)
    y1 = min(h, y1 + pad_y)
    crop = image[y0:y1, x0:x1]
    if crop is None or getattr(crop, "size", 0) == 0:
        return image
    crop = brighten_crop(crop)
    ch, cw = crop.shape[:2]
    scale = max(min_w / float(max(cw, 1)), min_h / float(max(ch, 1)), 3.2)
    scale = min(scale, 16.0)
    return cv2.resize(
        crop,
        (max(int(cw * scale), min_w), max(int(ch * scale), min_h)),
        interpolation=cv2.INTER_CUBIC,
    )


def crop_to_vehicles(image, vehicles: Iterable[VehicleLike], pad_ratio: float = 0.10):
    """Cut the frame down to the union of car silhouettes."""
    vehicles = list(vehicles)
    if not vehicles or image is None or getattr(image, "size", 0) == 0:
        return image
    h, w = image.shape[:2]
    boxes = [_as_box(item) for item in vehicles]
    x0 = min(box[0] for box in boxes)
    y0 = min(box[1] for box in boxes)
    x1 = max(box[2] for box in boxes)
    y1 = max(box[3] for box in boxes)
    pad_x = int((x1 - x0) * pad_ratio) + 8
    pad_y = int((y1 - y0) * pad_ratio) + 8
    x0 = max(0, x0 - pad_x)
    y0 = max(0, y0 - pad_y)
    x1 = min(w, x1 + pad_x)
    y1 = min(h, y1 + pad_y)
    if x1 - x0 < 20 or y1 - y0 < 20:
        return image
    return image[y0:y1, x0:x1]


def silhouette_mask(image_shape, vehicles: Sequence[VehicleLike], dilate: int = 11):
    """Binary mask: 255 on the car outline, 0 everywhere else."""
    import cv2
    import numpy as np

    h, w = image_shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    for item in vehicles:
        x0, y0, x1, y1 = _as_box(item)
        # Always fill the detection box (includes bumper expand below the contour).
        mask[max(0, y0) : max(0, y1), max(0, x0) : max(0, x1)] = 255
        contour = _as_contour(item)
        if contour is not None and len(contour):
            cv2.drawContours(mask, [contour], -1, 255, thickness=-1)
    if dilate > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate, dilate))
        mask = cv2.dilate(mask, kernel, iterations=1)
    return mask


def apply_silhouette_mask(image, vehicles: Sequence[VehicleLike]):
    """Keep only car pixels; cut the lot, sky and OSD to black."""
    import numpy as np

    if image is None or getattr(image, "size", 0) == 0:
        return image
    if not vehicles:
        return np.zeros_like(image)
    mask = silhouette_mask(image.shape, vehicles)
    out = image.copy()
    out[mask == 0] = 0
    return out


def cut_away_background(image, vehicles: Sequence[VehicleLike]):
    """Black out everything outside the silhouette, then crop to the cars."""
    import numpy as np

    if image is None or getattr(image, "size", 0) == 0:
        return image
    if not vehicles:
        return np.zeros_like(image)
    masked = apply_silhouette_mask(image, vehicles)
    return crop_to_vehicles(masked, vehicles)


# Bright azure frame like the operator reference: tight rectangle around the whole car.
CAR_FRAME_BGR = (255, 175, 35)


def draw_corner_frame(vis, box: Box, color=CAR_FRAME_BGR, thickness: int = 2, corner: int = 28) -> None:
    """Draw a tight rectangle around the car (reference-style blue frame)."""
    import cv2

    x0, y0, x1, y1 = [int(v) for v in box]
    if x1 - x0 < 12 or y1 - y0 < 12:
        return
    cv2.rectangle(vis, (x0, y0), (x1, y1), color, thickness)


def draw_vehicle_shape(vis, item: VehicleLike, label: str = "АВТО") -> None:
    """Draw a tight blue rectangle around the whole car (light or dark body)."""
    import cv2

    x0, y0, x1, y1 = _as_box(item)
    color = CAR_FRAME_BGR
    # Full solid rectangle — matches the operator reference frame.
    cv2.rectangle(vis, (x0, y0), (x1, y1), color, 2)
    text = label or "АВТО"
    text_y = max(22, y0 - 8)
    cv2.rectangle(vis, (x0, text_y - 18), (x0 + 8 + 12 * len(text), text_y + 4), (40, 30, 10), -1)
    cv2.putText(vis, text, (x0 + 4, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (220, 240, 255), 2)


def draw_type1_plate(vis, box: Box, plate: str = "") -> None:
    """Draw the ГОСТ Type-1 layout: body | region, matching «А 000 АА | 00»."""
    import cv2

    from anpr.plates import format_plate_parts

    x0, y0, x1, y1 = box
    if x1 - x0 < 8 or y1 - y0 < 6:
        return
    split = x0 + int((x1 - x0) * 0.78)
    cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 210, 255), 2)
    cv2.line(vis, (split, y0 + 1), (split, y1 - 1), (0, 210, 255), 1)
    body, region = format_plate_parts(plate) if plate else ("", "")
    label = f"{body} | {region}" if body and body != "—" else plate
    if label:
        cv2.putText(vis, label, (x0, max(18, y0 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 2)


def annotate_scene(image, vehicles: Sequence[VehicleLike], plates: list) -> object:
    """Keep the parking view, highlight car shape + frame the moment a car is detected."""
    import cv2
    import numpy as np

    vis = image.copy()
    # Drop OSD / dumpster false cars before dimming — otherwise the lot goes black.
    real_vehicles = []
    for item in vehicles:
        box = _as_box(item)
        if _is_non_vehicle(image, box):
            continue
        real_vehicles.append(item)
    if real_vehicles:
        # Keep the lot bright; the blue rectangle is the only highlight.
        for index, item in enumerate(real_vehicles):
            title = "АВТО" if index == 0 else f"АВТО {index + 1}"
            draw_vehicle_shape(vis, item, label=title)
    for hit in plates:
        box = getattr(hit, "bbox", None)
        if not box:
            continue
        draw_type1_plate(vis, box, getattr(hit, "plate", ""))
    return vis


def annotate_zoom(image, box: Box, vehicles: Sequence[VehicleLike] = (), plates: list = ()) -> object:
    """Close-up focused on the plate so the Type-1 number fills the side panel."""
    import cv2
    import numpy as np

    from anpr.plates import format_plate_parts

    # Never use a dimmed/annotated preview here — black lot pixels wipe the crop.
    if image is None or getattr(image, "size", 0) == 0:
        return None

    focus = box
    pad = 0.35
    min_w, min_h = 720, 360
    plate_focus = False
    for hit in plates:
        plate_box = getattr(hit, "bbox", None)
        if plate_box:
            focus = plate_box
            # Tight around the plate so digits dominate the panel (not the whole car).
            pad = 1.15
            min_w, min_h = 1100, 480
            plate_focus = True
            break

    if not focus:
        return None

    crop = zoom_box(image, focus, min_w=min_w, min_h=min_h, pad=pad)
    if crop is None or getattr(crop, "size", 0) == 0:
        return None
    crop = brighten_crop(crop, min_mean=100.0)
    # Guard: if crop is still nearly black, fall back to a wider bumper slice.
    if float(np.mean(crop)) < 40.0 and box and box != focus:
        crop = zoom_box(image, box, min_w=900, min_h=400, pad=0.45)
        if crop is None or getattr(crop, "size", 0) == 0:
            return None
        crop = brighten_crop(crop, min_mean=100.0)
        plate_focus = False

    h, w = crop.shape[:2]
    draw_corner_frame(crop, (8, 8, w - 8, h - 8), color=CAR_FRAME_BGR, thickness=3)
    title = "НОМЕР КРУПНО" if plate_focus else "АВТО"
    cv2.putText(crop, title, (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.85, CAR_FRAME_BGR, 2)
    for hit in plates:
        plate = getattr(hit, "plate", "") or ""
        if not plate:
            continue
        body, region = format_plate_parts(plate)
        label = f"{body} | {region}" if body and body != "—" else plate
        cv2.rectangle(crop, (0, h - 72), (w, h), (10, 10, 10), -1)
        cv2.putText(crop, label, (16, h - 22), cv2.FONT_HERSHEY_SIMPLEX, 1.35, (0, 220, 255), 3)
        break
    return crop
