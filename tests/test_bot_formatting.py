"""
Tests for Telegram Bot formatters and structure.
"""

from bot import format_term_html, get_term_keyboard, build_application
from translator.engine import TerminologyEngine


def test_format_term_html():
    engine = TerminologyEngine()
    term = engine.get_term_by_id("artificial_intelligence")
    assert term is not None
    html_text = format_term_html(term)
    assert "Artificial Intelligence" in html_text
    assert "人工智能" in html_text
    assert "rén gōng zhì néng" in html_text
    assert "Искусственный интеллект" in html_text
    assert "Определения" in html_text


def test_get_term_keyboard():
    engine = TerminologyEngine()
    term = engine.get_term_by_id("artificial_intelligence")
    assert term is not None
    keyboard = get_term_keyboard(term)
    assert keyboard is not None
    assert len(keyboard.inline_keyboard) >= 2
    # Verify Russian voice button exists
    cb_data_list = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert any("voice:ru:" in cb for cb in cb_data_list)
    assert any("voice:zh:" in cb for cb in cb_data_list)


def test_build_application():
    app = build_application()
    assert app is not None
    # Verify handlers are registered
    assert len(app.handlers[0]) >= 5
