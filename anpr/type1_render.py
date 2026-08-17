"""Draw a ГОСТ Type-1 plate: «А 000 АА | 00 RUS» plus flag."""

from __future__ import annotations

from anpr.plates import CYR_TO_LATIN, format_plate_parts, normalize_plate, plate_is_valid


def render_type1_plate(plate: str, scale: int = 3):
    """Return a BGR image of a Type-1 plate (white, black text, region box, RUS, flag)."""
    import cv2
    import numpy as np

    compact = normalize_plate(plate)
    if not plate_is_valid(compact):
        raise ValueError(f"not a Type-1 plate: {plate}")
    body, region = format_plate_parts(compact)
    latin_body = "".join(CYR_TO_LATIN.get(ch, ch) for ch in body)
    latin_region = region

    # Real plate ~520×112 mm → keep that aspect.
    w, h = 520 * scale // 3, 112 * scale // 3
    img = np.full((h, w, 3), 245, dtype=np.uint8)
    cv2.rectangle(img, (1, 1), (w - 2, h - 2), (15, 15, 15), 3)
    split = int(w * 0.78)
    cv2.line(img, (split, 8), (split, h - 8), (15, 15, 15), 2)

    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, latin_body, (18, int(h * 0.68)), font, 0.9 * scale / 3, (10, 10, 10), 2, cv2.LINE_AA)
    cv2.putText(
        img,
        latin_region,
        (split + 10, int(h * 0.48)),
        font,
        0.7 * scale / 3,
        (10, 10, 10),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(img, "RUS", (split + 10, int(h * 0.82)), font, 0.35 * scale / 3, (10, 10, 10), 1, cv2.LINE_AA)
    flag_x, flag_y = split + int(w * 0.12), int(h * 0.62)
    fw, fh = max(18, w // 16), max(12, h // 7)
    stripes = ((255, 255, 255), (166, 57, 0), (30, 43, 213))  # BGR: white, blue, red
    for i, color in enumerate(stripes):
        y0 = flag_y + i * (fh // 3)
        cv2.rectangle(img, (flag_x, y0), (flag_x + fw, y0 + fh // 3), color, -1)
    cv2.rectangle(img, (flag_x, flag_y), (flag_x + fw, flag_y + fh), (15, 15, 15), 1)
    return img


def scene_with_car_and_plate(plate: str):
    """Parking-lot frame: asphalt, one car silhouette, Type-1 plate on the bumper."""
    import numpy as np

    frame = np.full((360, 480, 3), 95, dtype=np.uint8)
    frame[0:50, :] = 190  # sky / OSD
    frame[150:310, 90:390] = (40, 42, 48)  # car body
    frame[165:215, 130:350] = (72, 74, 80)  # windshield
    plate_img = render_type1_plate(plate, scale=2)
    ph, pw = plate_img.shape[:2]
    x0, y0 = 160, 255
    x1, y1 = min(480, x0 + pw), min(360, y0 + ph)
    frame[y0:y1, x0:x1] = plate_img[: y1 - y0, : x1 - x0]
    return frame
