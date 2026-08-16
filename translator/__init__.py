"""
Technical Terms Translator Package (ZH - EN - RU).
"""

from translator.models import (
    Language,
    TechTerm,
    CategoryInfo,
    SearchResult,
    TranslationOutput,
    ExampleUsage,
)
from translator.pinyin_helper import (
    detect_language,
    get_pinyin,
    normalize_pinyin,
    is_chinese_text,
    is_cyrillic_text,
)
from translator.engine import (
    TerminologyEngine,
    OnlineTranslationFallback,
    TechTranslator,
)

__all__ = [
    "Language",
    "TechTerm",
    "CategoryInfo",
    "SearchResult",
    "TranslationOutput",
    "ExampleUsage",
    "detect_language",
    "get_pinyin",
    "normalize_pinyin",
    "is_chinese_text",
    "is_cyrillic_text",
    "TerminologyEngine",
    "OnlineTranslationFallback",
    "TechTranslator",
]
