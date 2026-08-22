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
        return 0.0, 0.0, 0.0, 0.0
    if crop.ndim == 2:
        crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    hue = hsv[:, :, 0]
    mean_sat = float(np.mean(sat))
    mean_val = float(np.mean(val))
    vivid = (sat > 70) & (val > 60)
    vivid_ratio = float(np.mean(vivid)) if vivid.size else 0.0
    blue = vivid & (hue >= 90) & (hue <= 140)
    yellow = vivid & (hue >= 10) & (hue <= 45)
    bin_color_ratio = float(np.mean(blue | yellow)) if vivid.size else 0.0
    return mean_sat, mean_val, vivid_ratio, bin_color_ratio


def _looks_like_dumpster(image, box: Box) -> bool:
    """True for colored garbage bins that must not be framed as cars."""
    x0, y0, x1, y1 = box
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    aspect = bw / float(bh)
    mean_sat, _mean_val, vivid_ratio, bin_color_ratio = _box_color_stats(image, box)
    if bin_color_ratio >= 0.12 and aspect < 2.2:
        return True
    if vivid_ratio >= 0.22 and mean_sat >= 55 and aspect < 2.4:
        return True
    h, w = image.shape[:2]
    cx = (x0 + x1) / 2.0
    near_side = cx < w * 0.18 or cx > w * 0.82
    if near_side and vivid_ratio >= 0.10 and 0.55 <= aspect <= 1.55:
        return True
    return False


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
    mean_sat, _mean_val, vivid_ratio, bin_color_ratio = _box_color_stats(image, box)

    score = base
    if 1.25 <= aspect <= 3.6:
        score += 0.18
    elif 0.9 <= aspect < 1.25:
        score += 0.02
    else:
        score -= 0.08
    score += min(area_ratio, 0.35) * 0.5
    score += (cy / max(h, 1)) * 0.12
    if w * 0.22 <= cx <= w * 0.78:
        score += 0.08
    score -= vivid_ratio * 0.45
    score -= bin_color_ratio * 0.70
    if mean_sat < 45:
        score += 0.06
    crop = image[y0:y1, x0:x1]
    if crop is not None and getattr(crop, "size", 0) > 0:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        ch = gray.shape[0]
        upper = gray[0 : max(int(ch * 0.45), 1), :]
        lower = gray[int(ch * 0.55) : ch, :]
        if upper.size and lower.size and float(np.mean(upper)) + 8 < float(np.mean(lower)):
            score += 0.10
        if float(np.std(gray)) > 18:
            score += 0.04
    return score


def _silhouettes_from_mask(
    mask, image_shape, min_ratio: float, max_ratio: float, image=None
) -> List[VehicleSilhouette]:
    import cv2

    h, w = image_shape[:2]
    frame_area = float(h * w)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found: List[VehicleSilhouette] = []
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        if cw < 36 or ch < 22:
            continue
        area = cw * ch
        ratio = area / frame_area
        if ratio < min_ratio or ratio > max_ratio:
            continue
        aspect = cw / float(ch)
        # Dumpsters are often near-square; cars from high cam are wider.
        if not (0.70 <= aspect <= 4.2):
            continue
        hull = cv2.contourArea(cv2.convexHull(contour)) or 1.0
        solidity = (cv2.contourArea(contour) or 0.0) / hull
        if solidity < 0.22:
            continue
        cy = y + ch / 2.0
        if cy < h * 0.18:
            continue
        pad_x, pad_y = int(cw * 0.08), int(ch * 0.10)
        box = (
            max(0, x - pad_x),
            max(0, y - pad_y),
            min(w, x + cw + pad_x),
            min(h, y + ch + pad_y),
        )
        if image is not None and _looks_like_dumpster(image, box):
            continue
        score = ratio + (cy / h) * 0.08 + min(solidity, 1.0) * 0.04
        if image is not None:
            score = _car_likeness_score(image, box, base=score)
        if score < 0.02:
            continue
        found.append(VehicleSilhouette(box=box, contour=contour, score=score))
    return found


def _foreground_mask(image):
    """Pixels that differ from the parking-lot background (asphalt)."""
    import cv2
    import numpy as np

    h, w = image.shape[:2]
    target_w = 360
    scale = target_w / float(max(w, 1))
    small_w = max(int(w * scale), 80)
    small_h = max(int(h * scale), 60)
    small = cv2.resize(image, (small_w, small_h), interpolation=cv2.INTER_AREA)
    if small.ndim == 2:
        small = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 0)

    bg = float(np.median(gray))
    # Light lots + white cars: lower difference threshold so pale SUVs still stand out.
    diff = cv2.absdiff(gray, np.full_like(gray, int(np.clip(bg, 0, 255))))
    diff_cut = 14 if bg >= 110 else 22
    _, mask_diff = cv2.threshold(diff, diff_cut, 255, cv2.THRESH_BINARY)

    _sat, val = hsv[:, :, 1], hsv[:, :, 2]
    # Do NOT treat vivid plastic dumpsters as car foreground.
    white_cut = max(int(bg + 6), 105)
    dark_cut = min(int(bg - 14), 95)
    _, mask_white = cv2.threshold(val, white_cut, 255, cv2.THRESH_BINARY)
    _, mask_dark = cv2.threshold(val, max(dark_cut, 1), 255, cv2.THRESH_BINARY_INV)

    # Local contrast helps white body on pale asphalt.
    local = cv2.GaussianBlur(gray, (31, 31), 0)
    local_diff = cv2.absdiff(gray, local)
    _, mask_local = cv2.threshold(local_diff, 8 if bg < 110 else 12, 255, cv2.THRESH_BINARY)

    # Pale SUV on light lot: low saturation + high value blob.
    pale = cv2.inRange(hsv, (0, 0, max(white_cut - 10, 100)), (180, 55, 255))
    mild_color = cv2.inRange(hsv, (0, 20, 25), (180, 90, 220))

    if bg >= 110:
        # Bright courtyard: global absdiff floods the whole lot — prefer local shape.
        _, strong_diff = cv2.threshold(diff, max(diff_cut + 10, 24), 255, cv2.THRESH_BINARY)
        mask = cv2.bitwise_or(mask_local, mask_dark)
        mask = cv2.bitwise_or(mask, strong_diff)
        mask = cv2.bitwise_or(mask, cv2.bitwise_and(pale, mask_local))
        mask = cv2.bitwise_or(mask, mild_color)
    else:
        mask = cv2.bitwise_or(mask_diff, mask_white)
        mask = cv2.bitwise_or(mask, mask_dark)
        mask = cv2.bitwise_or(mask, mask_local)
        mask = cv2.bitwise_or(mask, pale)
        mask = cv2.bitwise_or(mask, mild_color)
    # Cut vivid blue/yellow dumpster plastic out of the mask.
    vivid_bins = cv2.inRange(hsv, (10, 80, 70), (45, 255, 255))
    vivid_bins = cv2.bitwise_or(vivid_bins, cv2.inRange(hsv, (90, 80, 70), (140, 255, 255)))
    # Greenish bins too.
    vivid_bins = cv2.bitwise_or(vivid_bins, cv2.inRange(hsv, (40, 70, 60), (95, 255, 255)))
    mask[vivid_bins > 0] = 0

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
    return cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)


def _edge_mask(image):
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    blur = cv2.GaussianBlur(gray, (9, 9), 0)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
    closed = cv2.morphologyEx(blur, cv2.MORPH_CLOSE, kernel, iterations=2)
    edges = cv2.Canny(closed, 40, 120)
    edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)), iterations=2)
    return cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)


def find_vehicle_silhouettes(image, max_cars: int = 6) -> List[VehicleSilhouette]:
    """Return car outlines (contour + box) from a high parking-lot camera."""
    if image is None or getattr(image, "size", 0) == 0:
        return []
    found: List[VehicleSilhouette] = []
    try:
        fg = _foreground_mask(image)
        found.extend(
            _silhouettes_from_mask(fg, image.shape, min_ratio=0.006, max_ratio=0.50, image=image)
        )
    except Exception:
        pass
    try:
        edges = _edge_mask(image)
        found.extend(
            _silhouettes_from_mask(edges, image.shape, min_ratio=0.008, max_ratio=0.45, image=image)
        )
    except Exception:
        pass
    # Final dumpster pass (edge masks can still pick bins).
    found = [item for item in found if not _looks_like_dumpster(image, item.box)]
    if not found:
        return []
    kept = _nms(found, iou_thresh=0.42)
    kept.sort(key=lambda item: item.score, reverse=True)
    # Prefer one clear car over many weak boxes (bins, plate strips).
    if len(kept) >= 2 and kept[0].score >= kept[1].score * 1.35:
        kept = kept[:1]
    return kept[:max_cars]


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
    ch, cw = crop.shape[:2]
    scale = max(min_w / float(max(cw, 1)), min_h / float(max(ch, 1)), 3.2)
    scale = min(scale, 14.0)
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
        contour = _as_contour(item)
        if contour is not None and len(contour):
            cv2.drawContours(mask, [contour], -1, 255, thickness=-1)
        else:
            x0, y0, x1, y1 = _as_box(item)
            mask[y0:y1, x0:x1] = 255
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


def draw_corner_frame(vis, box: Box, color=(40, 220, 90), thickness: int = 3, corner: int = 28) -> None:
    """Draw an L-corner bounding frame around the detected car."""
    import cv2

    x0, y0, x1, y1 = [int(v) for v in box]
    if x1 - x0 < 12 or y1 - y0 < 12:
        return
    length = max(12, min(corner, (x1 - x0) // 3, (y1 - y0) // 3))
    # top-left
    cv2.line(vis, (x0, y0), (x0 + length, y0), color, thickness)
    cv2.line(vis, (x0, y0), (x0, y0 + length), color, thickness)
    # top-right
    cv2.line(vis, (x1, y0), (x1 - length, y0), color, thickness)
    cv2.line(vis, (x1, y0), (x1, y0 + length), color, thickness)
    # bottom-left
    cv2.line(vis, (x0, y1), (x0 + length, y1), color, thickness)
    cv2.line(vis, (x0, y1), (x0, y1 - length), color, thickness)
    # bottom-right
    cv2.line(vis, (x1, y1), (x1 - length, y1), color, thickness)
    cv2.line(vis, (x1, y1), (x1, y1 - length), color, thickness)
    cv2.rectangle(vis, (x0, y0), (x1, y1), color, 1)


def draw_vehicle_shape(vis, item: VehicleLike, label: str = "АВТО") -> None:
    """Draw car silhouette contour + detection frame at the moment the car is found."""
    import cv2

    contour = _as_contour(item)
    x0, y0, x1, y1 = _as_box(item)
    color = (40, 220, 90)
    if contour is not None and len(contour):
        cv2.drawContours(vis, [contour], -1, color, 2)
        # Soft fill so the shape of the car is obvious without hiding the plate.
        overlay = vis.copy()
        cv2.drawContours(overlay, [contour], -1, (30, 140, 60), thickness=-1)
        cv2.addWeighted(overlay, 0.18, vis, 0.82, 0, vis)
        cv2.drawContours(vis, [contour], -1, color, 2)
    draw_corner_frame(vis, (x0, y0, x1, y1), color=color, thickness=3)
    text = label or "АВТО"
    text_y = max(22, y0 - 8)
    cv2.rectangle(vis, (x0, text_y - 18), (x0 + 8 + 12 * len(text), text_y + 4), (16, 60, 28), -1)
    cv2.putText(vis, text, (x0 + 4, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (220, 255, 220), 2)


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
    if vehicles:
        mask = silhouette_mask(vis.shape, vehicles, dilate=15)
        # Dim the lot so the car shape stands out, but keep context.
        dim = (vis.astype(np.float32) * 0.35).astype(vis.dtype)
        vis = np.where(mask[:, :, None] > 0, vis, dim)
        for index, item in enumerate(vehicles):
            title = "АВТО" if index == 0 else f"АВТО {index + 1}"
            draw_vehicle_shape(vis, item, label=title)
    for hit in plates:
        box = getattr(hit, "bbox", None)
        if not box:
            continue
        draw_type1_plate(vis, box, getattr(hit, "plate", ""))
    return vis


def annotate_zoom(image, box: Box, vehicles: Sequence[VehicleLike] = (), plates: list = ()) -> object:
    """Close-up of the detected car/plate with frame and number text."""
    import cv2

    from anpr.plates import format_plate_parts

    pad = 0.45 if plates else 0.18
    crop = zoom_box(image, box, min_w=720, min_h=400, pad=pad)
    if crop is None or getattr(crop, "size", 0) == 0:
        return None
    h, w = crop.shape[:2]
    draw_corner_frame(crop, (8, 8, w - 8, h - 8), color=(40, 220, 90), thickness=3, corner=36)
    cv2.putText(crop, "АВТО", (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 220, 90), 2)
    for hit in plates:
        plate = getattr(hit, "plate", "") or ""
        if not plate:
            continue
        body, region = format_plate_parts(plate)
        label = f"{body} | {region}" if body and body != "—" else plate
        # Dark bar so the number is always readable on the zoom panel.
        cv2.rectangle(crop, (0, h - 52), (w, h), (10, 10, 10), -1)
        cv2.putText(crop, label, (16, h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 220, 255), 2)
        break
    return crop
