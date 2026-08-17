"""
Data models for Technical Terms Translator (Chinese - English - Russian).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class Language(str, Enum):
    EN = "en"
    RU = "ru"
    ZH = "zh"
    BUA = "bua"
    AUTO = "auto"

    @property
    def display_name_ru(self) -> str:
        names = {
            Language.EN: "Английский (English)",
            Language.RU: "Русский (Russian)",
            Language.ZH: "Китайский (中文)",
            Language.BUA: "Бурятский (Буряад хэлэн)",
            Language.AUTO: "Автоопределение",
        }
        return names.get(self, self.value)

    @property
    def display_name_en(self) -> str:
        names = {
            Language.EN: "English",
            Language.RU: "Russian",
            Language.ZH: "Chinese",
            Language.BUA: "Buryat",
            Language.AUTO: "Auto-detect",
        }
        return names.get(self, self.value)

    @property
    def display_name_zh(self) -> str:
        names = {
            Language.EN: "英语",
            Language.RU: "俄语",
            Language.ZH: "中文",
            Language.BUA: "布里亚特语",
            Language.AUTO: "自动检测",
        }
        return names.get(self, self.value)

    @property
    def flag(self) -> str:
        flags = {
            Language.EN: "🇺🇸",
            Language.RU: "🇷🇺",
            Language.ZH: "🇨🇳",
            Language.BUA: "🔵",
            Language.AUTO: "🌐",
        }
        return flags.get(self, "🌐")


@dataclass
class ExampleUsage:
    en: str
    ru: str
    zh: str
    pinyin: Optional[str] = None
    bua: Optional[str] = None


@dataclass
class TechTerm:
    id: str
    category: str
    en: str
    ru: str
    zh: str
    pinyin: str
    definition_ru: str
    definition_en: str
    definition_zh: str
    bua: Optional[str] = None
    definition_bua: Optional[str] = None
    zh_trad: Optional[str] = None
    examples: List[ExampleUsage] = field(default_factory=list)
    synonyms_en: List[str] = field(default_factory=list)
    synonyms_ru: List[str] = field(default_factory=list)
    synonyms_zh: List[str] = field(default_factory=list)
    synonyms_bua: List[str] = field(default_factory=list)
    related_terms: List[str] = field(default_factory=list)

    def get_term_in_lang(self, lang: Language) -> str:
        if lang == Language.EN:
            return self.en
        elif lang == Language.RU:
            return self.ru
        elif lang == Language.ZH:
            return self.zh
        elif lang == Language.BUA and self.bua:
            return self.bua
        return self.en

    def get_definition_in_lang(self, lang: Language) -> str:
        if lang == Language.RU:
            return self.definition_ru
        elif lang == Language.ZH:
            return self.definition_zh
        elif lang == Language.BUA and self.definition_bua:
            return self.definition_bua
        return self.definition_en

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "en": self.en,
            "ru": self.ru,
            "zh": self.zh,
            "bua": self.bua,
            "definition_bua": self.definition_bua,
            "zh_trad": self.zh_trad,
            "pinyin": self.pinyin,
            "definition_ru": self.definition_ru,
            "definition_en": self.definition_en,
            "definition_zh": self.definition_zh,
            "examples": [
                {"en": e.en, "ru": e.ru, "zh": e.zh, "pinyin": e.pinyin, "bua": e.bua}
                for e in self.examples
            ],
            "synonyms_en": self.synonyms_en,
            "synonyms_ru": self.synonyms_ru,
            "synonyms_zh": self.synonyms_zh,
            "synonyms_bua": self.synonyms_bua,
            "related_terms": self.related_terms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TechTerm":
        examples = [
            ExampleUsage(
                en=ex.get("en", ""),
                ru=ex.get("ru", ""),
                zh=ex.get("zh", ""),
                pinyin=ex.get("pinyin"),
                bua=ex.get("bua"),
            )
            for ex in data.get("examples", [])
        ]
        return cls(
            id=data["id"],
            category=data["category"],
            en=data["en"],
            ru=data["ru"],
            zh=data["zh"],
            bua=data.get("bua"),
            definition_bua=data.get("definition_bua"),
            pinyin=data.get("pinyin", ""),
            definition_ru=data.get("definition_ru", ""),
            definition_en=data.get("definition_en", ""),
            definition_zh=data.get("definition_zh", ""),
            zh_trad=data.get("zh_trad"),
            examples=examples,
            synonyms_en=data.get("synonyms_en", []),
            synonyms_ru=data.get("synonyms_ru", []),
            synonyms_zh=data.get("synonyms_zh", []),
            synonyms_bua=data.get("synonyms_bua", []),
            related_terms=data.get("related_terms", []),
        )


@dataclass
class CategoryInfo:
    id: str
    icon: str
    name_ru: str
    name_en: str
    name_zh: str
    description_ru: str = ""
    description_en: str = ""
    description_zh: str = ""


@dataclass
class SearchResult:
    term: TechTerm
    score: float
    matched_field: str
    matched_text: str


@dataclass
class OnlineTranslation:
    source_lang: Language
    target_lang: Language
    source_text: str
    translated_text: str
    pinyin: Optional[str] = None
    provider: str = "online"


@dataclass
class TranslationOutput:
    query: str
    detected_lang: Language
    direct_match: Optional[TechTerm] = None
    search_results: List[SearchResult] = field(default_factory=list)
    online_translations: Dict[str, str] = field(default_factory=dict)
    pinyin: Optional[str] = None
