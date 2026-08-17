"""
Tests for Terminology Database and loading.
"""

from translator.engine import TerminologyEngine
from translator.models import Language


def test_database_loads_categories():
    engine = TerminologyEngine()
    categories = engine.get_all_categories()
    assert len(categories) >= 8
    cat_ids = [c.id for c in categories]
    assert "ai_ml" in cat_ids
    assert "software_dev" in cat_ids
    assert "hardware" in cat_ids
    assert "networks" in cat_ids
    assert "databases" in cat_ids


def test_database_loads_terms():
    engine = TerminologyEngine()
    assert len(engine.terms) >= 30
    ai_term = engine.get_term_by_id("artificial_intelligence")
    assert ai_term is not None
    assert ai_term.en == "Artificial Intelligence"
    assert ai_term.zh == "人工智能"
    assert ai_term.ru == "Искусственный интеллект"
    assert len(ai_term.pinyin) > 0
    assert len(ai_term.definition_ru) > 0
    assert len(ai_term.definition_en) > 0
    assert len(ai_term.definition_zh) > 0


def test_get_terms_by_category():
    engine = TerminologyEngine()
    ai_terms = engine.get_terms_by_category("ai_ml")
    assert len(ai_terms) >= 10
    for term in ai_terms:
        assert term.category == "ai_ml"


def test_get_term_in_lang():
    engine = TerminologyEngine()
    term = engine.get_term_by_id("hello_greeting")
    assert term is not None
    assert term.get_term_in_lang(Language.EN) == "Hello / Hi"
    assert term.get_term_in_lang(Language.ZH) == "你好"
    assert term.get_term_in_lang(Language.RU) == "Привет / Здравствуйте"
    assert "Мэндээ" in term.get_term_in_lang(Language.BUA)


def test_random_terms():
    engine = TerminologyEngine()
    sample = engine.get_random_terms(count=3)
    assert len(sample) == 3
    sample_cat = engine.get_random_terms(count=2, category="hardware")
    assert len(sample_cat) == 2
    for t in sample_cat:
        assert t.category == "hardware"
