"""
Sports Betting Analytics & Risk Analysis Engine.
Mathematical models for probability estimation, odds margin calculation,
value betting identification, and bankroll risk management.
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class SportType(str, Enum):
    FOOTBALL = "football"
    BASKETBALL = "basketball"
    TENNIS = "tennis"
    HOCKEY = "hockey"
    CS2 = "cs2"


class RiskLevel(str, Enum):
    LOW = "Низкий (Safe)"
    LOW_MEDIUM = "Умеренно-низкий (Moderate Low)"
    MEDIUM = "Средний (Balanced)"
    HIGH = "Высокий (High Risk)"
    VERY_HIGH = "Очень высокий (Extreme / Speculative)"


@dataclass
class SportProfile:
    name: str
    sport_type: SportType
    default_draw_possible: bool
    typical_margin_range: Tuple[float, float]
    base_variance_score: float  # 1.0 (low variance) to 5.0 (high variance)
    recommended_markets: List[str]
    description: str


SPORT_PROFILES: Dict[SportType, SportProfile] = {
    SportType.TENNIS: SportProfile(
        name="Теннис (Одиночный)",
        sport_type=SportType.TENNIS,
        default_draw_possible=False,
        typical_margin_range=(3.0, 6.0),
        base_variance_score=1.5,
        recommended_markets=[
            "Победа в матче (П1/П2)",
            "Фора по сетам (+1.5)",
            "Индивидуальный тотал геймов фаворита",
        ],
        description="2 исхода, нет ничьих, результат зависит от сотен розыгрышей, высокая предсказуемость формы.",
    ),
    SportType.BASKETBALL: SportProfile(
        name="Баскетбол (NBA / Евролига)",
        sport_type=SportType.BASKETBALL,
        default_draw_possible=False,
        typical_margin_range=(3.5, 6.5),
        base_variance_score=1.8,
        recommended_markets=[
            "Победа с учетом ОТ",
            "Азиатская фора (+/- очков)",
            "Командный тотал очков",
        ],
        description="Высокая результативность (100+ владений), нивелируется случайность одного броска.",
    ),
    SportType.FOOTBALL: SportProfile(
        name="Футбол (Топ Лиги)",
        sport_type=SportType.FOOTBALL,
        default_draw_possible=True,
        typical_margin_range=(2.5, 5.5),
        base_variance_score=3.0,
        recommended_markets=[
            "Двойной исход (1X / X2)",
            "Фора (0) / DNB (Draw No Bet)",
            "Тотал больше 1.5 / Азиатский тотал",
            "Статистика (угловые, ЖК)",
        ],
        description="3 исхода (1X2), низкая результативность увеличивает влияние случайных событий (удаления, рикошеты).",
    ),
    SportType.HOCKEY: SportProfile(
        name="Хоккей (NHL / КХЛ)",
        sport_type=SportType.HOCKEY,
        default_draw_possible=True,
        typical_margin_range=(4.0, 7.0),
        base_variance_score=3.5,
        recommended_markets=[
            "Победа в матче (с учетом ОТ и буллитов)",
            "Фора (+1.5)",
            "Тотал больше 4.5",
        ],
        description="Высокая скорость игры, роль вратаря достигает 50% успеха, частые овертаймы в регулярке.",
    ),
    SportType.CS2: SportProfile(
        name="Киберспорт (CS2)",
        sport_type=SportType.CS2,
        default_draw_possible=False,
        typical_margin_range=(5.0, 8.5),
        base_variance_score=3.8,
        recommended_markets=[
            "Победа по картам (Фора +1.5 карты)",
            "Тотал карт больше 2.5",
            "Победа в пике своей карты",
        ],
        description="Сильная привязка к маппулу (Map Pool) и сторонам (CT/T), но подвержен психологической нестабильности.",
    ),
}


@dataclass
class TeamStats:
    name: str
    played_matches: int
    wins: int
    draws: int = 0
    losses: int = 0
    goals_or_points_scored: float = 0.0
    goals_or_points_conceded: float = 0.0
    xg_for: float = 0.0
    xg_against: float = 0.0
    form_recent_5: List[str] = field(default_factory=list)  # e.g., ["W", "W", "D", "L", "W"]
    key_injuries_count: int = 0
    rest_days: int = 4
    home_advantage_factor: float = 1.15


@dataclass
class OddsAnalysis:
    market_name: str
    odds: float
    implied_prob_raw: float
    implied_prob_fair: float
    calculated_prob: float
    ev_percent: float  # Expected value %
    margin_percent: float
    is_value: bool
    kelly_stake_percent: float
    recommended_flat_stake_percent: float
    risk_level: RiskLevel
    risk_explanation: str


class SportsAnalyticsEngine:
    """Core mathematical and analytical engine for sports betting analysis."""

    @staticmethod
    def calculate_margin(odds_list: List[float]) -> float:
        """
        Calculates bookmaker margin in percent.
        Margin = (Sum(1/odds) - 1) * 100
        """
        if not odds_list or any(o <= 1.0 for o in odds_list):
            return 0.0
        inv_sum = sum(1.0 / o for o in odds_list)
        return max(0.0, (inv_sum - 1.0) * 100.0)

    @staticmethod
    def fair_probabilities(odds_list: List[float]) -> List[float]:
        """
        Calculates true implied probabilities by removing bookmaker margin proportionally.
        """
        if not odds_list or any(o <= 1.0 for o in odds_list):
            return [0.0] * len(odds_list)
        raw_probs = [1.0 / o for o in odds_list]
        total_raw = sum(raw_probs)
        if total_raw <= 0:
            return [0.0] * len(odds_list)
        return [p / total_raw for p in raw_probs]

    @staticmethod
    def poisson_pmf(k: int, lambda_param: float) -> float:
        """Poisson Probability Mass Function: P(k; lambda) = (lambda^k * e^-lambda) / k!"""
        if lambda_param <= 0:
            return 1.0 if k == 0 else 0.0
        return (math.pow(lambda_param, k) * math.exp(-lambda_param)) / math.factorial(k)

    @classmethod
    def calculate_football_poisson(
        cls,
        home_attack_strength: float,
        home_defense_weakness: float,
        away_attack_strength: float,
        away_defense_weakness: float,
        league_avg_home_goals: float = 1.45,
        league_avg_away_goals: float = 1.15,
        max_goals: int = 6,
    ) -> Dict[str, float]:
        """
        Calculates match outcome probabilities (1, X, 2, Over 2.5, Both Teams to Score) using bivariate Poisson model.
        """
        home_exp_goals = home_attack_strength * away_defense_weakness * league_avg_home_goals
        away_exp_goals = away_attack_strength * home_defense_weakness * league_avg_away_goals

        # Prevent unrealistic negative or zero expectations
        home_exp_goals = max(0.2, home_exp_goals)
        away_exp_goals = max(0.2, away_exp_goals)

        prob_home_win = 0.0
        prob_draw = 0.0
        prob_away_win = 0.0
        prob_over_2_5 = 0.0
        prob_btts_yes = 0.0

        for h in range(max_goals + 1):
            p_h = cls.poisson_pmf(h, home_exp_goals)
            for a in range(max_goals + 1):
                p_a = cls.poisson_pmf(a, away_exp_goals)
                joint_p = p_h * p_a

                if h > a:
                    prob_home_win += joint_p
                elif h == a:
                    prob_draw += joint_p
                else:
                    prob_away_win += joint_p

                if (h + a) > 2.5:
                    prob_over_2_5 += joint_p

                if h > 0 and a > 0:
                    prob_btts_yes += joint_p

        # Normalization
        total_1x2 = prob_home_win + prob_draw + prob_away_win
        if total_1x2 > 0:
            prob_home_win /= total_1x2
            prob_draw /= total_1x2
            prob_away_win /= total_1x2

        return {
            "home_exp_goals": home_exp_goals,
            "away_exp_goals": away_exp_goals,
            "home_win": prob_home_win,
            "draw": prob_draw,
            "away_win": prob_away_win,
            "double_chance_1x": prob_home_win + prob_draw,
            "double_chance_x2": prob_away_win + prob_draw,
            "dnb_home": prob_home_win / (prob_home_win + prob_away_win) if (prob_home_win + prob_away_win) > 0 else 0.5,
            "over_2_5": min(1.0, prob_over_2_5),
            "under_2_5": max(0.0, 1.0 - prob_over_2_5),
            "btts_yes": min(1.0, prob_btts_yes),
            "btts_no": max(0.0, 1.0 - prob_btts_yes),
        }

    @staticmethod
    def calculate_expected_value(prob: float, odds: float) -> float:
        """
        Expected Value (EV) calculation in percentage:
        EV = (Probability * Odds - 1) * 100%
        """
        return (prob * odds - 1.0) * 100.0

    @staticmethod
    def kelly_criterion(prob: float, odds: float, fraction: float = 0.25) -> float:
        """
        Fractional Kelly Criterion for optimal position sizing.
        Full Kelly = (b*p - q) / b, where b = odds - 1, p = prob, q = 1 - p.
        Fractional Kelly (e.g. 0.25 / Quarter Kelly) drastically reduces bankroll volatility.
        Returns recommended percentage of total bankroll (0.0 to 10.0 max safety cap).
        """
        if odds <= 1.0 or prob <= 0:
            return 0.0

        b = odds - 1.0
        q = 1.0 - prob
        full_kelly = (b * prob - q) / b

        if full_kelly <= 0:
            return 0.0

        stake = full_kelly * fraction * 100.0
        # Hard safety cap of 5% on single bet to minimize ruin risk
        return min(5.0, round(stake, 2))

    @classmethod
    def evaluate_bet_risk(
        cls,
        sport: SportType,
        odds: float,
        calculated_prob: float,
        is_draw_included: bool = False,
        injury_penalty: float = 0.0,
        rest_penalty: float = 0.0,
    ) -> Tuple[RiskLevel, str, float]:
        """
        Evaluates risk score and provides risk tier and plain-language explanation.
        Returns: (RiskLevel, Explanation, RecommendedFlatStakePercent)
        """
        profile = SPORT_PROFILES[sport]
        
        # Risk factors
        # 1. Base sport variance (1.0 to 4.0)
        # 2. Odds level (higher odds = higher variance)
        # 3. Probability (< 50% increases probability of long losing streaks)
        # 4. Situational factors (injuries, fatigue)
        
        odds_risk = math.log2(max(1.01, odds)) * 1.8
        prob_risk = max(0.0, (1.0 - calculated_prob) * 4.0)
        situational_risk = injury_penalty * 1.5 + rest_penalty * 1.0
        
        total_risk_score = profile.base_variance_score + odds_risk + prob_risk + situational_risk

        if total_risk_score < 3.2 and odds < 1.60 and calculated_prob >= 0.65:
            risk = RiskLevel.LOW
            rec_flat = 2.0
            explanation = "Минимальный риск: высокая расчетная вероятность, низкая дисперсия рынка."
        elif total_risk_score < 4.5 and odds < 2.10 and calculated_prob >= 0.48:
            risk = RiskLevel.LOW_MEDIUM
            rec_flat = 1.5
            explanation = "Умеренно-низкий риск: сбалансированное соотношение вероятности и коэффициента."
        elif total_risk_score < 6.0 and odds < 3.00:
            risk = RiskLevel.MEDIUM
            rec_flat = 1.0
            explanation = "Средний риск: стандартная дисперсия, рекомендуется строгий флэт не более 1%."
        elif total_risk_score < 7.5:
            risk = RiskLevel.HIGH
            rec_flat = 0.5
            explanation = "Высокий риск: повышенная волатильность исхода или высокий коэффициент."
        else:
            risk = RiskLevel.VERY_HIGH
            rec_flat = 0.25
            explanation = "Экстремальный риск: спекулятивная ставка с высокой вероятностью проигрыша на короткой дистанции."

        return risk, explanation, rec_flat

    @classmethod
    def analyze_market(
        cls,
        market_name: str,
        sport: SportType,
        odds: float,
        calculated_prob: float,
        all_market_odds: List[float],
        injury_penalty: float = 0.0,
        rest_penalty: float = 0.0,
    ) -> OddsAnalysis:
        """
        Performs full mathematical & risk analysis of a single market/outcome.
        """
        margin = cls.calculate_margin(all_market_odds)
        fair_probs = cls.fair_probabilities(all_market_odds)
        
        # Find index or approximate
        raw_implied = (1.0 / odds) if odds > 0 else 0.0
        
        # Calculate fair implied prob corresponding to this odds
        if odds in all_market_odds:
            idx = all_market_odds.index(odds)
            fair_implied = fair_probs[idx]
        else:
            fair_implied = raw_implied / (1.0 + margin / 100.0) if margin > 0 else raw_implied

        ev_percent = cls.calculate_expected_value(calculated_prob, odds)
        is_value = ev_percent > 1.5  # Positive EV > 1.5% considered actionable value

        kelly_stake = cls.kelly_criterion(calculated_prob, odds, fraction=0.25) if is_value else 0.0
        risk_level, explanation, flat_stake = cls.evaluate_bet_risk(
            sport=sport,
            odds=odds,
            calculated_prob=calculated_prob,
            injury_penalty=injury_penalty,
            rest_penalty=rest_penalty,
        )

        return OddsAnalysis(
            market_name=market_name,
            odds=odds,
            implied_prob_raw=raw_implied,
            implied_prob_fair=fair_implied,
            calculated_prob=calculated_prob,
            ev_percent=ev_percent,
            margin_percent=margin,
            is_value=is_value,
            kelly_stake_percent=kelly_stake,
            recommended_flat_stake_percent=flat_stake if is_value else 0.0,
            risk_level=risk_level,
            risk_explanation=explanation,
        )
