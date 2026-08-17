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


def _silhouettes_from_mask(mask, image_shape, min_ratio: float, max_ratio: float) -> List[VehicleSilhouette]:
    import cv2

    h, w = image_shape[:2]
    frame_area = float(h * w)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found: List[VehicleSilhouette] = []
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        if cw < 36 or ch < 24:
            continue
        area = cw * ch
        ratio = area / frame_area
        if ratio < min_ratio or ratio > max_ratio:
            continue
        aspect = cw / float(ch)
        if not (0.55 <= aspect <= 4.2):
            continue
        hull = cv2.contourArea(cv2.convexHull(contour)) or 1.0
        solidity = (cv2.contourArea(contour) or 0.0) / hull
        if solidity < 0.28:
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
        score = ratio + (cy / h) * 0.08 + min(solidity, 1.0) * 0.04
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
    diff = cv2.absdiff(gray, np.full_like(gray, int(np.clip(bg, 0, 255))))
    _, mask_diff = cv2.threshold(diff, 26, 255, cv2.THRESH_BINARY)

    sat, val = hsv[:, :, 1], hsv[:, :, 2]
    _, mask_sat = cv2.threshold(sat, 42, 255, cv2.THRESH_BINARY)
    white_cut = max(int(bg + 32), 145)
    dark_cut = min(int(bg - 28), 78)
    _, mask_white = cv2.threshold(val, white_cut, 255, cv2.THRESH_BINARY)
    _, mask_dark = cv2.threshold(val, max(dark_cut, 1), 255, cv2.THRESH_BINARY_INV)

    mask = cv2.bitwise_or(mask_diff, mask_sat)
    mask = cv2.bitwise_or(mask, mask_white)
    mask = cv2.bitwise_or(mask, mask_dark)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
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
        found.extend(_silhouettes_from_mask(fg, image.shape, min_ratio=0.008, max_ratio=0.50))
    except Exception:
        pass
    try:
        edges = _edge_mask(image)
        found.extend(_silhouettes_from_mask(edges, image.shape, min_ratio=0.010, max_ratio=0.45))
    except Exception:
        pass
    if not found:
        return []
    kept = _nms(found, iou_thresh=0.42)
    kept.sort(key=lambda item: (item.box[2] - item.box[0]) * (item.box[3] - item.box[1]), reverse=True)
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


def draw_type1_plate(vis, box: Box, plate: str = "") -> None:
    """Draw the ГОСТ Type-1 layout: body | region, matching «А 000 АА | 00»."""
    import cv2

    from anpr.plates import format_plate_parts

    x0, y0, x1, y1 = box
    if x1 - x0 < 8 or y1 - y0 < 6:
        return
    split = x0 + int((x1 - x0) * 0.78)
    cv2.rectangle(vis, (x0, y0), (x1, y1), (10, 10, 10), 2)
    cv2.line(vis, (split, y0 + 1), (split, y1 - 1), (10, 10, 10), 1)
    body, region = format_plate_parts(plate) if plate else ("", "")
    label = f"{body} | {region}" if body and body != "—" else plate
    if label:
        cv2.putText(vis, label, (x0, max(18, y0 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 2)


def annotate_scene(image, vehicles: Sequence[VehicleLike], plates: list) -> object:
    """Keep the car silhouette, cut the rest, outline AUTO and the Type-1 plate."""
    import cv2

    vis = image.copy()
    if vehicles:
        mask = silhouette_mask(vis.shape, vehicles)
        vis[mask == 0] = 0
        for item in vehicles:
            contour = _as_contour(item)
            x0, y0, x1, y1 = _as_box(item)
            if contour is not None and len(contour):
                cv2.drawContours(vis, [contour], -1, (40, 200, 80), 2)
            else:
                cv2.rectangle(vis, (x0, y0), (x1, y1), (40, 200, 80), 2)
            cv2.putText(vis, "AUTO", (x0, max(18, y0 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (40, 200, 80), 2)
    else:
        vis[:] = 0
    for hit in plates:
        box = getattr(hit, "bbox", None)
        if not box:
            continue
        draw_type1_plate(vis, box, getattr(hit, "plate", ""))
    return vis
