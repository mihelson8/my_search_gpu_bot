"""
Unit tests for Sports Analytics Engine (using built-in unittest).
"""

import math
import unittest

from sports_analytics.engine import (
    RiskLevel,
    SportType,
    SportsAnalyticsEngine,
    SPORT_PROFILES,
)


class TestSportsAnalytics(unittest.TestCase):

    def test_margin_calculation(self):
        # 2-way market with no margin (fair coin flip)
        self.assertAlmostEqual(SportsAnalyticsEngine.calculate_margin([2.0, 2.0]), 0.0, places=4)

        # Typical 2-way market with margin (1.90 / 1.90)
        # (1/1.9 + 1/1.9 - 1) * 100 = ~5.263%
        margin_2way = SportsAnalyticsEngine.calculate_margin([1.90, 1.90])
        self.assertAlmostEqual(margin_2way, 5.263, places=2)

        # 3-way 1X2 market (2.00, 3.50, 4.00)
        # 1/2.0 + 1/3.5 + 1/4.0 = 0.5 + 0.2857 + 0.25 = 1.0357 => 3.57%
        margin_3way = SportsAnalyticsEngine.calculate_margin([2.00, 3.50, 4.00])
        self.assertAlmostEqual(margin_3way, 3.571, places=2)

    def test_fair_probabilities(self):
        odds = [2.0, 2.0]
        fair = SportsAnalyticsEngine.fair_probabilities(odds)
        self.assertEqual(len(fair), 2)
        self.assertAlmostEqual(fair[0], 0.5)
        self.assertAlmostEqual(fair[1], 0.5)

        odds_3way = [2.00, 3.50, 4.00]
        fair_3way = SportsAnalyticsEngine.fair_probabilities(odds_3way)
        self.assertAlmostEqual(sum(fair_3way), 1.0)
        self.assertTrue(fair_3way[0] > fair_3way[1] > fair_3way[2])

    def test_poisson_pmf(self):
        # P(0; 1.0) = e^-1 = ~0.367879
        self.assertAlmostEqual(SportsAnalyticsEngine.poisson_pmf(0, 1.0), math.exp(-1.0), places=5)
        # P(1; 1.0) = 1 * e^-1 = ~0.367879
        self.assertAlmostEqual(SportsAnalyticsEngine.poisson_pmf(1, 1.0), math.exp(-1.0), places=5)

    def test_football_poisson_distribution(self):
        res = SportsAnalyticsEngine.calculate_football_poisson(
            home_attack_strength=1.5,
            home_defense_weakness=0.8,
            away_attack_strength=1.1,
            away_defense_weakness=1.0,
        )

        self.assertIn("home_win", res)
        self.assertIn("draw", res)
        self.assertIn("away_win", res)
        self.assertIn("over_2_5", res)
        self.assertIn("under_2_5", res)

        # Probabilities must sum to ~1.0
        self.assertAlmostEqual(res["home_win"] + res["draw"] + res["away_win"], 1.0, places=4)
        self.assertAlmostEqual(res["over_2_5"] + res["under_2_5"], 1.0, places=4)

        # Stronger home team should have higher home win probability
        self.assertGreater(res["home_win"], res["away_win"])

    def test_expected_value_and_kelly(self):
        # Negative EV: 50% prob at 1.90 odds => EV = (0.5 * 1.90 - 1) = -5%
        ev_neg = SportsAnalyticsEngine.calculate_expected_value(0.5, 1.90)
        self.assertAlmostEqual(ev_neg, -5.0, places=4)
        stake_neg = SportsAnalyticsEngine.kelly_criterion(0.5, 1.90)
        self.assertEqual(stake_neg, 0.0)

        # Positive EV: 60% prob at 2.00 odds => EV = (0.6 * 2.0 - 1) = +20%
        ev_pos = SportsAnalyticsEngine.calculate_expected_value(0.6, 2.00)
        self.assertAlmostEqual(ev_pos, 20.0, places=4)
        # Full Kelly: (1 * 0.6 - 0.4) / 1 = 0.20 (20%)
        # Quarter Kelly (0.25): 20% * 0.25 = 5.0%
        stake_pos = SportsAnalyticsEngine.kelly_criterion(0.6, 2.00, fraction=0.25)
        self.assertAlmostEqual(stake_pos, 5.0, places=2)

    def test_risk_evaluation(self):
        # Low risk bet: Tennis, 70% probability, 1.45 odds
        risk, expl, flat_stake = SportsAnalyticsEngine.evaluate_bet_risk(
            sport=SportType.TENNIS,
            odds=1.45,
            calculated_prob=0.70,
        )
        self.assertIn(risk, (RiskLevel.LOW, RiskLevel.LOW_MEDIUM))
        self.assertGreaterEqual(flat_stake, 1.5)

        # High risk speculative bet: Football away win at 5.50 odds with 15% prob
        risk_high, expl_high, flat_high = SportsAnalyticsEngine.evaluate_bet_risk(
            sport=SportType.FOOTBALL,
            odds=5.50,
            calculated_prob=0.15,
        )
        self.assertIn(risk_high, (RiskLevel.HIGH, RiskLevel.VERY_HIGH))
        self.assertLessEqual(flat_high, 0.5)

    def test_analyze_market_full(self):
        analysis = SportsAnalyticsEngine.analyze_market(
            market_name="Победа Фаворита",
            sport=SportType.TENNIS,
            odds=1.80,
            calculated_prob=0.65,
            all_market_odds=[1.80, 2.10],
        )

        self.assertTrue(analysis.is_value)
        self.assertGreater(analysis.ev_percent, 0)
        self.assertGreater(analysis.margin_percent, 0)
        self.assertGreater(analysis.kelly_stake_percent, 0)
        self.assertGreater(analysis.recommended_flat_stake_percent, 0)


if __name__ == "__main__":
    unittest.main()
