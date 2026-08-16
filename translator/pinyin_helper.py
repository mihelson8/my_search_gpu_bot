"""
Pinyin and Language utilities for Chinese - English - Russian text processing.
"""

import re
import unicodedata
from typing import Optional
from translator.models import Language

try:
    import pypinyin
    from pypinyin import Style
    HAS_PYPINYIN = True
except ImportError:
    HAS_PYPINYIN = False


# Regex patterns for script detection
RE_CHINESE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
RE_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
RE_LATIN = re.compile(r"[a-zA-Z]")


def detect_language(text: str) -> Language:
    """
    Detect whether the input text is primarily Chinese, Russian, or English.
    """
    if not text or not text.strip():
        return Language.EN

    clean_text = text.strip()
    zh_count = len(RE_CHINESE.findall(clean_text))
    ru_count = len(RE_CYRILLIC.findall(clean_text))
    en_count = len(RE_LATIN.findall(clean_text))

    if zh_count > 0 and zh_count >= ru_count and zh_count >= en_count:
        return Language.ZH
    if ru_count > 0 and ru_count >= en_count:
        return Language.RU
    if en_count > 0:
        return Language.EN

    return Language.EN


def get_pinyin(text: str, tone_marks: bool = True) -> str:
    """
    Convert Chinese characters to Pinyin string with tone marks or plain letters.
    """
    if not text or not HAS_PYPINYIN:
        return ""

    if not RE_CHINESE.search(text):
        return ""

    try:
        if tone_marks:
            pinyin_list = pypinyin.pinyin(text, style=Style.TONE)
            return " ".join([p[0] for p in pinyin_list])
        else:
            pinyin_list = pypinyin.lazy_pinyin(text)
            return " ".join(pinyin_list)
    except Exception:
        return ""


def normalize_pinyin(text: str) -> str:
    """
    Normalize pinyin by removing tone marks, spaces, and punctuation for fuzzy search.
    e.g. "shēndù xuéxí" -> "shenduxuexi"
    """
    if not text:
        return ""

    # Normalize unicode to separate base characters and combining marks
    decomposed = unicodedata.normalize("NFD", text.lower())
    # Strip combining diacritical marks (tones)
    without_tones = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    # Replace ü with v or u
    normalized = without_tones.replace("ü", "u").replace("v", "u")
    # Remove non-alphanumeric characters
    cleaned = re.sub(r"[^a-z0-9]", "", normalized)
    return cleaned


def is_chinese_text(text: str) -> bool:
    """Check if the text contains Chinese characters."""
    return bool(RE_CHINESE.search(text))


def is_cyrillic_text(text: str) -> bool:
    """Check if the text contains Cyrillic characters."""
    return bool(RE_CYRILLIC.search(text))
