"""
Tests for Search and Translation Engine.
"""

import pytest
from translator.engine import TerminologyEngine, TechTranslator
from translator.models import Language


def test_search_english_exact():
    engine = TerminologyEngine()
    results = engine.search("Deep Learning")
    assert len(results) > 0
    assert results[0].term.id == "deep_learning"
    assert results[0].score == 1.0


def test_search_chinese_exact():
    engine = TerminologyEngine()
    results = engine.search("深度学习")
    assert len(results) > 0
    assert results[0].term.id == "deep_learning"
    assert results[0].score == 1.0


def test_search_russian_exact():
    engine = TerminologyEngine()
    results = engine.search("Глубокое обучение")
    assert len(results) > 0
    assert results[0].term.id == "deep_learning"
    assert results[0].score == 1.0


def test_search_pinyin():
    engine = TerminologyEngine()
    results = engine.search("shendu xuexi")
    assert len(results) > 0
    assert results[0].term.id == "deep_learning"
    assert results[0].score >= 0.85


def test_search_synonyms():
    engine = TerminologyEngine()
    results_ai = engine.search("LLM")
    assert len(results_ai) > 0
    assert results_ai[0].term.id == "large_language_model"

    results_k8s = engine.search("K8s")
    assert len(results_k8s) > 0
    assert results_k8s[0].term.id == "kubernetes"


def test_search_fuzzy():
    engine = TerminologyEngine()
    results = engine.search("artifishal inteligence")
    assert len(results) > 0
    assert any(r.term.id == "artificial_intelligence" for r in results)


def test_translator_pipeline():
    import asyncio
    async def _test():
        translator = TechTranslator()
        output = await translator.translate("neural network", enable_online_fallback=False)
        assert output.detected_lang == Language.EN
        assert output.direct_match is not None
        assert output.direct_match.id == "neural_network"
        assert output.direct_match.zh == "神经网络"
        assert output.direct_match.ru == "Нейронная сеть"
    asyncio.run(_test())
