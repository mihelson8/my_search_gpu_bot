"""
Tests for Telegram Sports Bot message formatting and logic.
"""

import unittest
from sports_bot import (
    format_sports_overview_html,
    format_football_match_html,
    format_value_calc_html,
    format_margin_calc_html,
    format_bankroll_guide_html,
    format_help_html,
)


class TestSportsBotFormatting(unittest.TestCase):

    def test_sports_overview_html(self):
        text = format_sports_overview_html()
        self.assertIn("СРАВНЕНИЕ ВИДОВ СПОРТА", text)
        self.assertIn("Теннис", text)
        self.assertIn("Баскетбол", text)
        self.assertIn("Футбол", text)
        self.assertIn("Маржа БК", text)

    def test_football_match_html_success(self):
        text = format_football_match_html(
            home_name="Манчестер Сити",
            away_name="Ливерпуль",
            odds_1=2.15,
            odds_x=3.60,
            odds_2=3.40,
        )
        self.assertIn("Манчестер Сити vs Ливерпуль", text)
        self.assertIn("Пуассон", text)
        self.assertIn("Вероятность П1", text)
        self.assertIn("Маржа букмекера", text)

    def test_football_match_html_not_found(self):
        text = format_football_match_html(
            home_name="НесуществующаяКоманда1",
            away_name="НесуществующаяКоманда2",
            odds_1=2.0,
            odds_x=3.0,
            odds_2=4.0,
        )
        self.assertIn("не найдены в базе", text)

    def test_value_calc_html_positive(self):
        # 55% at 2.15 => EV = +18.25%
        text = format_value_calc_html(odds=2.15, estimated_prob_percent=55.0)
        self.assertIn("ВАЛУЙНАЯ СТАВКА", text)
        self.assertIn("Expected Value", text)
        self.assertIn("Флэт", text)
        self.assertIn("Келли", text)

    def test_value_calc_html_negative(self):
        # 40% at 2.00 => EV = -20%
        text = format_value_calc_html(odds=2.00, estimated_prob_percent=40.0)
        self.assertIn("МИНУСОВАЯ СТАВКА", text)
        self.assertIn("Ставить не рекомендуется", text)

    def test_margin_calc_html(self):
        text = format_margin_calc_html([1.90, 1.90])
        self.assertIn("РАСЧЕТ МАРЖИ", text)
        self.assertIn("5.26%", text)

    def test_guides_html(self):
        bankroll_text = format_bankroll_guide_html()
        self.assertIn("СТРАТЕГИИ УПРАВЛЕНИЯ БАНКРОЛЛОМ", bankroll_text)
        self.assertIn("Флэт", bankroll_text)
        self.assertIn("Келли", bankroll_text)

        help_text = format_help_html()
        self.assertIn("/sports", help_text)
        self.assertIn("/value", help_text)
        self.assertIn("/margin", help_text)


if __name__ == "__main__":
    unittest.main()
