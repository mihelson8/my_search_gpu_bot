"""
Tests for CLI output formatters.
"""

from cli import format_term_card, format_translation_output
from translator.engine import TerminologyEngine, TechTranslator
from translator.models import TranslationOutput, Language


def test_format_term_card():
    engine = TerminologyEngine()
    term = engine.get_term_by_id("cpu")
    assert term is not None
    card = format_term_card(term)
    assert "Central Processing Unit" in card
    assert "中央处理器" in card
    assert "Центральный процессор" in card


def test_format_translation_output_direct():
    engine = TerminologyEngine()
    term = engine.get_term_by_id("cpu")
    output = TranslationOutput(
        query="cpu",
        detected_lang=Language.EN,
        direct_match=term,
    )
    formatted = format_translation_output(output)
    assert "Точное совпадение в словаре" in formatted
    assert "Central Processing Unit" in formatted
