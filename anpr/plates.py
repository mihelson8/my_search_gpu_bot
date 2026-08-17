"""Russian license-plate normalization and validation.

Standard passenger plates (type 1): letter + 3 digits + 2 letters + 2–3 digit region.
Allowed letters are the 12 Cyrillic characters that look like Latin:
А В Е К М Н О Р С Т У Х
"""

from __future__ import annotations

import re
from typing import List, Optional

CYR_LETTERS = "АВЕКМНОРСТУХ"
LATIN_TO_CYR = {
    "A": "А",
    "B": "В",
    "E": "Е",
    "K": "К",
    "M": "М",
    "H": "Н",
    "O": "О",
    "P": "Р",
    "C": "С",
    "T": "Т",
    "Y": "У",
    "X": "Х",
}
CYR_TO_LATIN = {v: k for k, v in LATIN_TO_CYR.items()}

# OCR often confuses these depending on whether a slot must be a letter or a digit.
LETTER_SLOT_FIX = {
    "0": "О",
    "O": "О",
    "8": "В",
    "6": "Б",  # will fail validation if left as Б
    "3": "З",
}
DIGIT_SLOT_FIX = {
    "О": "0",
    "O": "0",
    "D": "0",
    "Q": "0",
    "I": "1",
    "І": "1",
    "L": "1",
    "Z": "2",
    "З": "3",
    "S": "5",
    "Б": "6",
    "G": "6",
    "Т": "7",
    "T": "7",
    "В": "8",
    "B": "8",
    "Ч": "4",
}

# Type 1 (ГОСТ): letter + 3 digits + 2 letters + region 2–3 digits. Layout: «А 000 АА | 00 RUS».
PLATE_RE = re.compile(rf"^[{CYR_LETTERS}]\d{{3}}[{CYR_LETTERS}]{{2}}\d{{2,3}}$")
TYPE1_BODY_RE = re.compile(rf"^[{CYR_LETTERS}]\d{{3}}[{CYR_LETTERS}]{{2}}$")
TYPE1_REGION_RE = re.compile(r"^\d{2,3}$")
RUS_SUFFIX_RE = re.compile(r"(RUS|РУС)$", re.IGNORECASE)
NON_PLATE_CHARS = re.compile(r"[^A-ZА-ЯЁ0-9]+", re.IGNORECASE)


def _to_cyr_letter(ch: str) -> str:
    ch = ch.upper()
    if ch in LATIN_TO_CYR:
        return LATIN_TO_CYR[ch]
    return ch


def compact_alnum(text: str) -> str:
    """Keep only letters and digits, map Latin lookalikes to Cyrillic letters."""
    if not text:
        return ""
    chars = []
    for ch in text.upper().replace("Ё", "Е"):
        if ch in LATIN_TO_CYR:
            chars.append(LATIN_TO_CYR[ch])
        elif ch.isalnum():
            chars.append(ch)
    return "".join(chars)


def _apply_letter_digit_slots(compact: str, letter_slots: set[int]) -> str:
    out = []
    for i, ch in enumerate(compact):
        ch = ch.upper()
        if i in letter_slots:
            ch = LETTER_SLOT_FIX.get(ch, ch)
            ch = _to_cyr_letter(ch)
        else:
            ch = DIGIT_SLOT_FIX.get(ch, ch)
            if not ch.isdigit():
                ch = DIGIT_SLOT_FIX.get(_to_cyr_letter(ch), ch)
        out.append(ch)
    return "".join(out)


def apply_slot_rules(compact: str) -> str:
    """Force letter/digit slots for 8–9 character Russian plates."""
    if len(compact) not in (8, 9):
        return "".join(_to_cyr_letter(ch) for ch in compact)
    return _apply_letter_digit_slots(compact, {0, 4, 5})


def apply_body_slot_rules(compact: str) -> str:
    """Force L DDD LL for the left half of a Type-1 plate (without region)."""
    if len(compact) != 6:
        return "".join(_to_cyr_letter(ch) for ch in compact)
    return _apply_letter_digit_slots(compact, {0, 4, 5})


def normalize_plate(text: str) -> str:
    """Return a compact normalized plate string (may still be invalid)."""
    compact = compact_alnum(text)
    return apply_slot_rules(compact)


def plate_is_valid(plate: str) -> bool:
    if not plate or not PLATE_RE.match(plate):
        return False
    latin = "".join(CYR_TO_LATIN.get(ch, ch) for ch in plate)
    junk = ("IPCAM", "HDIP", "CAMERA", "SEETONG", "MAINVIEW")
    return not any(token in latin.upper() for token in junk)


def format_plate(plate: str) -> str:
    """Type-1 grouping as on the plate: «А 000 АА 00». Invalid text is not shown."""
    p = normalize_plate(plate)
    if not plate_is_valid(p):
        return "—"
    body = f"{p[0]} {p[1:4]} {p[4:6]}"
    return f"{body} {p[6:]}"


def type1_body(text: str) -> str:
    """Return the 6-character left part (А000АА) or empty."""
    compact = apply_body_slot_rules(compact_alnum(text))
    return compact if TYPE1_BODY_RE.match(compact) else ""


def type1_region(text: str) -> str:
    """Return a 2–3 digit region from a fragment like «00» or «00 RUS»."""
    if not text or is_osd_text(text):
        return ""
    compact = compact_alnum(text)
    latin = _latin_compact(compact)
    stripped = RUS_SUFFIX_RE.sub("", latin).strip()
    if TYPE1_REGION_RE.match(stripped) and not _window_is_overlay_junk(stripped):
        return stripped
    return ""


def combine_type1_parts(texts: List[str]) -> List[str]:
    """Join OCR boxes: left «А 000 АА» + right «00 RUS» → А000АА00."""
    bodies: List[str] = []
    regions: List[str] = []
    found: List[str] = []
    seen = set()
    for text in texts:
        if not text or is_osd_text(text):
            continue
        body = type1_body(text)
        if body and body not in bodies:
            bodies.append(body)
        region = type1_region(text)
        # A 6-character body also contains three digits — do not treat those as region.
        if region and not body and region not in regions:
            regions.append(region)
        for plate in extract_plates(text):
            if plate not in seen:
                seen.add(plate)
                found.append(plate)
    for body in bodies:
        for region in regions:
            plate = body + region
            if plate_is_valid(plate) and plate not in seen:
                seen.add(plate)
                found.append(plate)
    return found


def _latin_compact(text: str) -> str:
    return "".join(CYR_TO_LATIN.get(ch, ch) for ch in text).upper()


def _window_is_overlay_junk(chunk: str) -> bool:
    latin = _latin_compact(chunk)
    markers = (
        "IPCAM",
        "HDIP",
        "CAMERA",
        "2880",
        "1620",
        "SEETONG",
        "MAINVIEW",
        "X162",
        "880X",
        "0X16",
    )
    return any(marker in latin for marker in markers)


def is_osd_text(text: str) -> bool:
    """True for camera overlays like HD IPCAM 2880X1620."""
    if not text:
        return False
    return _window_is_overlay_junk(compact_alnum(text))


def extract_plates(raw_text: str) -> List[str]:
    """Find all valid Russian plates inside noisy OCR text."""
    if not raw_text:
        return []

    found = []
    seen = set()

    compact = compact_alnum(raw_text)
    for size in (9, 8):
        if len(compact) < size:
            continue
        for i in range(0, len(compact) - size + 1):
            chunk = compact[i : i + size]
            if _window_is_overlay_junk(chunk):
                continue
            candidate = apply_slot_rules(chunk)
            if plate_is_valid(candidate) and candidate not in seen:
                seen.add(candidate)
                found.append(candidate)

    whole = normalize_plate(raw_text)
    if plate_is_valid(whole) and not _window_is_overlay_junk(compact_alnum(raw_text)) and whole not in seen:
        found.insert(0, whole)

    return found


def best_plate(raw_text: str) -> Optional[str]:
    plates = extract_plates(raw_text)
    return plates[0] if plates else None


def category_label(category: str) -> str:
    return {
        "own": "СВОЙ",
        "foreign": "ЧУЖОЙ",
        "unknown": "НЕИЗВЕСТНЫЙ",
    }.get(category, category)


def parse_category(value: str) -> str:
    raw = (value or "").strip().lower()
    mapping = {
        "own": "own",
        "свой": "own",
        "svoi": "own",
        "свои": "own",
        "white": "own",
        "whitelist": "own",
        "foreign": "foreign",
        "чужой": "foreign",
        "чужие": "foreign",
        "black": "foreign",
        "blacklist": "foreign",
        "unknown": "unknown",
        "неизвестный": "unknown",
    }
    return mapping.get(raw, "unknown")
