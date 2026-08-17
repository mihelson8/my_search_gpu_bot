"""
Core Dictionary and Translation Engine for Chinese, English, and Russian technical terminology.
"""

import os
import json
import difflib
import logging
import asyncio
from typing import List, Optional, Dict, Tuple

import httpx
from translator.models import (
    TechTerm,
    CategoryInfo,
    SearchResult,
    Language,
    TranslationOutput,
)
from translator.pinyin_helper import (
    detect_language,
    get_pinyin,
    normalize_pinyin,
    is_chinese_text,
)

logger = logging.getLogger(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(CURRENT_DIR, "data")
TERMS_FILE = os.path.join(DATA_DIR, "terms.json")
CATEGORIES_FILE = os.path.join(DATA_DIR, "categories.json")


class TerminologyEngine:
    """
    Main dictionary search and translation engine for technical terms across Chinese, English, and Russian.
    """

    def __init__(self, terms_file: str = TERMS_FILE, categories_file: str = CATEGORIES_FILE):
        self.terms_file = terms_file
        self.categories_file = categories_file
        self.terms: List[TechTerm] = []
        self.categories: Dict[str, CategoryInfo] = {}
        self.term_index: Dict[str, TechTerm] = {}
        self.load_data()

    def load_data(self):
        """Load categories and terms from JSON files."""
        # Load categories
        if os.path.exists(self.categories_file):
            try:
                with open(self.categories_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        cat = CategoryInfo(
                            id=item["id"],
                            icon=item.get("icon", "📁"),
                            name_ru=item.get("name_ru", ""),
                            name_en=item.get("name_en", ""),
                            name_zh=item.get("name_zh", ""),
                            description_ru=item.get("description_ru", ""),
                            description_en=item.get("description_en", ""),
                            description_zh=item.get("description_zh", ""),
                        )
                        self.categories[cat.id] = cat
            except Exception as e:
                logger.error(f"Failed to load categories: {e}")

        # Load terms
        if os.path.exists(self.terms_file):
            try:
                with open(self.terms_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        term = TechTerm.from_dict(item)
                        # Auto-compute pinyin if missing
                        if not term.pinyin and term.zh:
                            term.pinyin = get_pinyin(term.zh)
                        self.terms.append(term)
                        self.term_index[term.id] = term
            except Exception as e:
                logger.error(f"Failed to load terms: {e}")

    def get_all_categories(self) -> List[CategoryInfo]:
        """Return all available categories."""
        return list(self.categories.values())

    def get_category_by_id(self, category_id: str) -> Optional[CategoryInfo]:
        """Get category info by id."""
        return self.categories.get(category_id)

    def get_terms_by_category(self, category_id: str) -> List[TechTerm]:
        """Get all terms within a specific category."""
        return [t for t in self.terms if t.category == category_id]

    def get_term_by_id(self, term_id: str) -> Optional[TechTerm]:
        """Get a single term by unique ID."""
        return self.term_index.get(term_id)

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
        min_score: float = 0.4,
    ) -> List[SearchResult]:
        """
        Comprehensive search across all 3 languages (English, Chinese, Russian),
        synonyms, pinyin, and definitions.
        """
        if not query or not query.strip():
            return []

        clean_query = query.strip()
        query_lower = clean_query.lower()
        norm_query_pinyin = normalize_pinyin(clean_query)

        results: List[SearchResult] = []

        candidate_terms = self.terms
        if category:
            candidate_terms = [t for t in candidate_terms if t.category == category]

        for term in candidate_terms:
            best_score = 0.0
            best_field = ""
            best_match_text = ""

            # Check direct exact match
            if query_lower == term.en.lower():
                score = 1.0
                if score > best_score:
                    best_score, best_field, best_match_text = score, "en_exact", term.en
            elif clean_query == term.zh or (term.zh_trad and clean_query == term.zh_trad):
                score = 1.0
                if score > best_score:
                    best_score, best_field, best_match_text = score, "zh_exact", term.zh
            elif query_lower == term.ru.lower():
                score = 1.0
                if score > best_score:
                    best_score, best_field, best_match_text = score, "ru_exact", term.ru

            # Check Pinyin exact or prefix match
            norm_term_pinyin = normalize_pinyin(term.pinyin)
            if norm_query_pinyin and (norm_query_pinyin == norm_term_pinyin):
                score = 0.98
                if score > best_score:
                    best_score, best_field, best_match_text = score, "pinyin_exact", term.pinyin
            elif norm_query_pinyin and norm_query_pinyin in norm_term_pinyin:
                score = 0.85
                if score > best_score:
                    best_score, best_field, best_match_text = score, "pinyin_substr", term.pinyin

            # Check Substring matches in EN, ZH, RU
            if query_lower in term.en.lower():
                score = 0.90 if term.en.lower().startswith(query_lower) else 0.80
                if score > best_score:
                    best_score, best_field, best_match_text = score, "en_substring", term.en

            if clean_query in term.zh:
                score = 0.90 if term.zh.startswith(clean_query) else 0.80
                if score > best_score:
                    best_score, best_field, best_match_text = score, "zh_substring", term.zh

            if query_lower in term.ru.lower():
                score = 0.90 if term.ru.lower().startswith(query_lower) else 0.80
                if score > best_score:
                    best_score, best_field, best_match_text = score, "ru_substring", term.ru

            # Check Synonyms
            for syn in term.synonyms_en:
                if query_lower == syn.lower():
                    score = 0.95
                elif query_lower in syn.lower():
                    score = 0.75
                else:
                    continue
                if score > best_score:
                    best_score, best_field, best_match_text = score, "synonym_en", syn

            for syn in term.synonyms_zh:
                if clean_query == syn:
                    score = 0.95
                elif clean_query in syn:
                    score = 0.75
                else:
                    continue
                if score > best_score:
                    best_score, best_field, best_match_text = score, "synonym_zh", syn

            for syn in term.synonyms_ru:
                if query_lower == syn.lower():
                    score = 0.95
                elif query_lower in syn.lower():
                    score = 0.75
                else:
                    continue
                if score > best_score:
                    best_score, best_field, best_match_text = score, "synonym_ru", syn

            # Check fuzzy similarity
            if best_score < 0.8:
                sim_en = difflib.SequenceMatcher(None, query_lower, term.en.lower()).ratio()
                sim_ru = difflib.SequenceMatcher(None, query_lower, term.ru.lower()).ratio()
                sim_zh = difflib.SequenceMatcher(None, clean_query, term.zh).ratio()

                if sim_en > 0.6 and sim_en > best_score:
                    best_score, best_field, best_match_text = sim_en, "fuzzy_en", term.en
                if sim_ru > 0.6 and sim_ru > best_score:
                    best_score, best_field, best_match_text = sim_ru, "fuzzy_ru", term.ru
                if sim_zh > 0.6 and sim_zh > best_score:
                    best_score, best_field, best_match_text = sim_zh, "fuzzy_zh", term.zh

            # Check Definitions for keywords
            if best_score < 0.6:
                if query_lower in term.definition_en.lower():
                    best_score, best_field, best_match_text = 0.50, "def_en", term.definition_en[:50] + "..."
                elif query_lower in term.definition_ru.lower():
                    best_score, best_field, best_match_text = 0.50, "def_ru", term.definition_ru[:50] + "..."
                elif clean_query in term.definition_zh:
                    best_score, best_field, best_match_text = 0.50, "def_zh", term.definition_zh[:50] + "..."

            if best_score >= min_score:
                results.append(
                    SearchResult(
                        term=term,
                        score=round(best_score, 3),
                        matched_field=best_field,
                        matched_text=best_match_text,
                    )
                )

        # Sort results by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def find_direct_match(self, query: str) -> Optional[TechTerm]:
        """Find an exact or highly confident match for the given query."""
        results = self.search(query, limit=1, min_score=0.90)
        if results:
            return results[0].term
        return None

    def get_random_terms(self, count: int = 5, category: Optional[str] = None) -> List[TechTerm]:
        """Get a random selection of terms (e.g. for learning / quizzes)."""
        import random
        pool = self.terms
        if category:
            pool = [t for t in pool if t.category == category]
        if not pool:
            return []
        sample_size = min(count, len(pool))
        return random.sample(pool, sample_size)


class OnlineTranslationFallback:
    """
    Fallback translation client using public translation endpoints
    when a phrase is not in the built-in technical term dictionary.
    """

    @staticmethod
    async def translate_text(text: str, source_lang: Language, target_lang: Language) -> Optional[str]:
        """
        Translate arbitrary text using free public translation API.
        """
        if not text or not text.strip():
            return None

        lang_code_map = {
            Language.EN: "en",
            Language.RU: "ru",
            Language.ZH: "zh",
            Language.BUA: "bua",
            Language.AUTO: "auto",
        }

        sl = lang_code_map.get(source_lang, "auto")
        tl = lang_code_map.get(target_lang, "en")

        # Fallback endpoints: Google Translate and MyMemory
        try:
            # 1. Try Google Translate public endpoint
            g_url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={sl}&tl={tl}&dt=t&q={httpx.URL('', params={'q': text}).params['q']}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(g_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                        translated_parts = [part[0] for part in data[0] if part and len(part) > 0 and part[0]]
                        res = "".join(translated_parts).strip()
                        if res and res != text:
                            return res
        except Exception as e:
            logger.debug(f"Google fallback failed: {e}")

        # If target language is Buryat, MyMemory doesn't support it, but bxr on google can be tried
        if tl == "bua":
            try:
                g_url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={sl}&tl=bxr&dt=t&q={httpx.URL('', params={'q': text}).params['q']}"
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get(g_url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                            translated_parts = [part[0] for part in data[0] if part and len(part) > 0 and part[0]]
                            res = "".join(translated_parts).strip()
                            if res and res != text:
                                return res
            except Exception:
                pass

        try:
            # 2. Try MyMemory Translation API (for EN, RU, ZH)
            if tl != "bua":
                sl_mymemory = "zh-CN" if sl == "zh" else sl
                tl_mymemory = "zh-CN" if tl == "zh" else tl
                pair = f"{sl_mymemory}|{tl_mymemory}"
                if sl == "auto":
                    pair = f"autodetect|{tl_mymemory}"

                url = "https://api.mymemory.translated.net/get"
                params = {"q": text, "langpair": pair}
                headers = {"User-Agent": "TechTermsTranslator/1.0"}

                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get(url, params=params, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        res = data.get("responseData", {}).get("translatedText")
                        if res and res != text:
                            return res
        except Exception as e:
            logger.warning(f"Online translation failed: {e}")

        return None


class TechTranslator:
    """
    Unified high-level translator interface combining local tech dictionary + pinyin + online fallback.
    """

    def __init__(self, engine: Optional[TerminologyEngine] = None):
        self.engine = engine or TerminologyEngine()
        self.online = OnlineTranslationFallback()

    async def translate(
        self,
        query: str,
        category: Optional[str] = None,
        enable_online_fallback: bool = True,
    ) -> TranslationOutput:
        """
        Translate and lookup technical terms across Chinese, English, and Russian.
        """
        detected_lang = detect_language(query)
        output = TranslationOutput(query=query, detected_lang=detected_lang)

        # Look in dictionary
        search_res = self.engine.search(query, category=category, limit=5, min_score=0.45)
        output.search_results = search_res

        if search_res and search_res[0].score >= 0.85:
            output.direct_match = search_res[0].term

        # If detected Chinese, provide pinyin
        if detected_lang == Language.ZH or is_chinese_text(query):
            output.pinyin = get_pinyin(query)

        # If no direct dictionary match and fallback enabled, fetch online translations in parallel
        if not output.direct_match and enable_online_fallback:
            target_langs = [l for l in [Language.EN, Language.RU, Language.ZH, Language.BUA] if l != detected_lang]
            async def _fetch(tl: Language):
                res = await self.online.translate_text(query, detected_lang, tl)
                return tl, res

            tasks = [_fetch(tl) for tl in target_langs]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for item in results:
                if isinstance(item, tuple):
                    tl, trans = item
                    if trans:
                        output.online_translations[tl.value] = trans
                        if tl == Language.ZH and not output.pinyin:
                            output.pinyin = get_pinyin(trans)

        return output
