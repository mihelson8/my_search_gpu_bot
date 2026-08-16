"""
Tests for language detection and Pinyin utilities.
"""

from translator.models import Language
from translator.pinyin_helper import (
    detect_language,
    get_pinyin,
    normalize_pinyin,
    is_chinese_text,
    is_cyrillic_text,
)


def test_detect_language_chinese():
    assert detect_language("人工智能") == Language.ZH
    assert detect_language("深度学习") == Language.ZH
    assert detect_language("什么是神经网络？") == Language.ZH


def test_detect_language_russian():
    assert detect_language("Искусственный интеллект") == Language.RU
    assert detect_language("глубокое обучение") == Language.RU
    assert detect_language("компилятор и интерпретатор") == Language.RU


def test_detect_language_english():
    assert detect_language("Artificial Intelligence") == Language.EN
    assert detect_language("Deep Learning") == Language.EN
    assert detect_language("CPU and GPU architecture") == Language.EN


def test_is_chinese_text():
    assert is_chinese_text("自然语言处理") is True
    assert is_chinese_text("NLP (自然语言处理)") is True
    assert is_chinese_text("Machine Learning") is False
    assert is_chinese_text("Машинное обучение") is False


def test_is_cyrillic_text():
    assert is_cyrillic_text("Привет") is True
    assert is_cyrillic_text("Python разработчик") is True
    assert is_cyrillic_text("Hello World") is False
    assert is_cyrillic_text("你好") is False


def test_get_pinyin():
    py = get_pinyin("人工智能")
    assert "rén" in py and "zhì" in py
    py_plain = get_pinyin("深度学习", tone_marks=False)
    assert "shen" in py_plain and "xue" in py_plain


def test_normalize_pinyin():
    assert normalize_pinyin("shēndù xuéxí") == "shenduxuexi"
    assert normalize_pinyin("rén gōng zhì néng") == "rengongzhineng"
    assert normalize_pinyin("jiān dū xué xí") == "jianduxuexi"
