#!/usr/bin/env python3
"""
Sports Betting Analytics & Risk Assessment CLI Tool.
Анализ видов спорта, рисков, команд, коэффициентов и поиск валуйных ставок.
"""

import sys
import argparse
from typing import List, Optional

from sports_analytics.engine import (
    RiskLevel,
    SportType,
    SportsAnalyticsEngine,
    TeamStats,
    OddsAnalysis,
    SPORT_PROFILES,
)
from sports_analytics.data import TEAM_DATABASE


def print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(f" {title.upper()}")
    print("=" * 70)


def print_sports_overview() -> None:
    print_header("Сравнение видов спорта по уровню риска и пригодности для анализа")
    
    for st, profile in SPORT_PROFILES.items():
        print(f"\n🏆 {profile.name} (Код: {st.value})")
        print(f"   • Базовая дисперсия (риск): {profile.base_variance_score:.1f} / 5.0")
        print(f"   • Типичная маржа букмекеров: {profile.typical_margin_range[0]}% - {profile.typical_margin_range[1]}%")
        print(f"   • Наличие ничьей (1X2): {'Да (3 исхода)' if profile.default_draw_possible else 'Нет (2 исхода)'}")
        print(f"   • Описание: {profile.description}")
        print("   • Рекомендуемые наименее рискованные рынки:")
        for m in profile.recommended_markets:
            print(f"     - {m}")


def analyze_football_match(
    home_team_name: str,
    away_team_name: str,
    odds_1: float,
    odds_x: float,
    odds_2: float,
    odds_over25: Optional[float] = None,
    odds_under25: Optional[float] = None,
    odds_1x: Optional[float] = None,
    odds_x2: Optional[float] = None,
) -> None:
    home = TEAM_DATABASE.get(home_team_name)
    away = TEAM_DATABASE.get(away_team_name)

    if not home or not away:
        print(f"Ошибка: Команды '{home_team_name}' или '{away_team_name}' не найдены в базе.")
        print(f"Доступные команды: {', '.join(TEAM_DATABASE.keys())}")
        return

    print_header(f"Аналитический разбор матча: {home.name} vs {away.name}")
    print(f"Форма {home.name} (последние 5): {'-'.join(home.form_recent_5)} | Травмы: {home.key_injuries_count} | Отдых: {home.rest_days} дн.")
    print(f"Форма {away.name} (последние 5): {'-'.join(away.form_recent_5)} | Травмы: {away.key_injuries_count} | Отдых: {away.rest_days} дн.")

    # Calculate relative attack and defense strengths based on goals and xG
    home_attack = (home.xg_for / max(1, home.played_matches)) / 1.5 * home.home_advantage_factor
    home_defense = (home.xg_against / max(1, home.played_matches)) / 1.2
    away_attack = (away.xg_for / max(1, away.played_matches)) / 1.5
    away_defense = (away.xg_against / max(1, away.played_matches)) / 1.2

    # Adjust for injuries and fatigue
    if home.key_injuries_count > 0:
        home_attack *= (1.0 - 0.05 * home.key_injuries_count)
    if away.key_injuries_count > 0:
        away_attack *= (1.0 - 0.05 * away.key_injuries_count)

    probs = SportsAnalyticsEngine.calculate_football_poisson(
        home_attack_strength=home_attack,
        home_defense_weakness=home_defense,
        away_attack_strength=away_attack,
        away_defense_weakness=away_defense,
    )

    print("\n📊 1. Расчетная математическая модель (Двумерный Пуассон + xG):")
    print(f"   • Ожидаемые голы (xG): {home.name} {probs['home_exp_goals']:.2f} — {probs['away_exp_goals']:.2f} {away.name}")
    print(f"   • Вероятность победы {home.name} (П1): {probs['home_win']*100:.1f}%")
    print(f"   • Вероятность ничьей (X):             {probs['draw']*100:.1f}%")
    print(f"   • Вероятность победы {away.name} (П2): {probs['away_win']*100:.1f}%")
    print(f"   • Вероятность 1X (П1 или ничья):       {probs['double_chance_1x']*100:.1f}%")
    print(f"   • Вероятность X2 (П2 или ничья):       {probs['double_chance_x2']*100:.1f}%")
    print(f"   • Вероятность Тотал Больше 2.5:        {probs['over_2_5']*100:.1f}%")

    # 1X2 Market Analysis
    market_1x2_odds = [odds_1, odds_x, odds_2]
    margin = SportsAnalyticsEngine.calculate_margin(market_1x2_odds)
    print(f"\n💰 2. Маржа букмекера на 1X2: {margin:.2f}%")

    analyses: List[OddsAnalysis] = []
    
    # 1X2 outcomes
    analyses.append(
        SportsAnalyticsEngine.analyze_market(
            market_name=f"Победа {home.name} (П1)",
            sport=SportType.FOOTBALL,
            odds=odds_1,
            calculated_prob=probs["home_win"],
            all_market_odds=market_1x2_odds,
            injury_penalty=home.key_injuries_count * 0.2,
            rest_penalty=max(0, 4 - home.rest_days) * 0.2,
        )
    )
    analyses.append(
        SportsAnalyticsEngine.analyze_market(
            market_name="Ничья (X)",
            sport=SportType.FOOTBALL,
            odds=odds_x,
            calculated_prob=probs["draw"],
            all_market_odds=market_1x2_odds,
        )
    )
    analyses.append(
        SportsAnalyticsEngine.analyze_market(
            market_name=f"Победа {away.name} (П2)",
            sport=SportType.FOOTBALL,
            odds=odds_2,
            calculated_prob=probs["away_win"],
            all_market_odds=market_1x2_odds,
            injury_penalty=away.key_injuries_count * 0.2,
            rest_penalty=max(0, 4 - away.rest_days) * 0.2,
        )
    )

    # Low-risk double chance markets
    calc_1x_odds = odds_1x if odds_1x else 1.0 / (1.0 / odds_1 + 1.0 / odds_x)
    analyses.append(
        SportsAnalyticsEngine.analyze_market(
            market_name=f"Двойной шанс 1X ({home.name} не проиграет)",
            sport=SportType.FOOTBALL,
            odds=calc_1x_odds,
            calculated_prob=probs["double_chance_1x"],
            all_market_odds=[calc_1x_odds, odds_2],
        )
    )

    if odds_over25 and odds_under25:
        tot_margin_odds = [odds_over25, odds_under25]
        analyses.append(
            SportsAnalyticsEngine.analyze_market(
                market_name="Тотал Больше 2.5",
                sport=SportType.FOOTBALL,
                odds=odds_over25,
                calculated_prob=probs["over_2_5"],
                all_market_odds=tot_margin_odds,
            )
        )
        analyses.append(
            SportsAnalyticsEngine.analyze_market(
                market_name="Тотал Меньше 2.5",
                sport=SportType.FOOTBALL,
                odds=odds_under25,
                calculated_prob=probs["under_2_5"],
                all_market_odds=tot_margin_odds,
            )
        )

    print("\n🎯 3. Сравнение коэффициентов, поиск Value Bets (+EV) и оценка рисков:")
    print("-" * 70)
    print(f"{'Маркет':<32} | {'Кэф':<5} | {'Справедл.':<9} | {'EV (+/-)':<8} | {'Риск-категория':<12}")
    print("-" * 70)

    for a in analyses:
        fair_odds = (1.0 / a.calculated_prob) if a.calculated_prob > 0 else 999.0
        ev_str = f"{a.ev_percent:+.1f}%"
        val_flag = " ⭐ VALUE" if a.is_value else ""
        print(f"{a.market_name[:32]:<32} | {a.odds:<5.2f} | {fair_odds:<9.2f} | {ev_str:<8} | {a.risk_level.value[:12]}{val_flag}")

    print("\n🛡️ 4. Рекомендации по банкролл-менеджменту:")
    value_bets = [a for a in analyses if a.is_value]
    if not value_bets:
        print("   ⚠️ Нет исходов с математическим преимуществом (+EV). Рекомендуется пропустить матч.")
    else:
        for vb in value_bets:
            print(f"\n   ✅ Рекомендованный выбор: {vb.market_name}")
            print(f"      • Коэффициент: {vb.odds:.2f} (Математическое ожидание EV: {vb.ev_percent:+.1f}%)")
            print(f"      • Уровень риска: {vb.risk_level.value}")
            print(f"      • Пояснение: {vb.risk_explanation}")
            print(f"      • Флэт-ставка (минимальный риск): {vb.recommended_flat_stake_percent:.1f}% от банка")
            print(f"      • Дробный критерий Келли (0.25x): {vb.kelly_stake_percent:.2f}% от банка")


def analyze_custom_odds(
    sport_name: str,
    event_name: str,
    odds_list: List[float],
    estimated_probs: List[float],
    labels: List[str],
) -> None:
    sport_type_map = {
        "football": SportType.FOOTBALL,
        "футбол": SportType.FOOTBALL,
        "basketball": SportType.BASKETBALL,
        "баскетбол": SportType.BASKETBALL,
        "tennis": SportType.TENNIS,
        "теннис": SportType.TENNIS,
        "hockey": SportType.HOCKEY,
        "хоккей": SportType.HOCKEY,
        "cs2": SportType.CS2,
        "киберспорт": SportType.CS2,
    }
    st = sport_type_map.get(sport_name.lower(), SportType.FOOTBALL)
    profile = SPORT_PROFILES[st]

    print_header(f"Пользовательский анализ: {event_name} [{profile.name}]")
    margin = SportsAnalyticsEngine.calculate_margin(odds_list)
    print(f"Маржа букмекера на данном рынке: {margin:.2f}%")

    for i, (odd, prob, label) in enumerate(zip(odds_list, estimated_probs, labels)):
        analysis = SportsAnalyticsEngine.analyze_market(
            market_name=label,
            sport=st,
            odds=odd,
            calculated_prob=prob,
            all_market_odds=odds_list,
        )
        fair_odd = 1.0 / prob if prob > 0 else 999.0
        print(f"\n📌 Исходит: {label}")
        print(f"   • Коэффициент: {odd:.2f} | Справедливый кэф (без маржи): {fair_odd:.2f}")
        print(f"   • Ваша вероятность: {prob*100:.1f}% | Букмерская чистая: {analysis.implied_prob_fair*100:.1f}%")
        print(f"   • Expected Value (EV): {analysis.ev_percent:+.2f}% {'🔥 ВАЛУЙНАЯ СТАВКА' if analysis.is_value else '❌ МИНУСОВОЕ EV'}")
        print(f"   • Уровень риска: {analysis.risk_level.value}")
        print(f"   • Пояснение: {analysis.risk_explanation}")
        if analysis.is_value:
            print(f"   • Рекомендуемый размер ставки: {analysis.recommended_flat_stake_percent:.1f}% (Флэт) / {analysis.kelly_stake_percent:.2f}% (Келли)")


def main():
    parser = argparse.ArgumentParser(description="Спортивно-аналитический инструмент оценки рисков и коэффициентов")
    subparsers = parser.add_subparsers(dest="command", help="Команда для выполнения")

    # Command 1: Sports overview
    subparsers.add_parser("sports", help="Показать сравнение всех видов спорта по рискам и марже")

    # Command 2: Analyze Football match
    fb_parser = subparsers.add_parser("football", help="Анализ футбольного матча между командами из базы")
    fb_parser.add_argument("--home", type=str, default="Манчестер Сити", help="Хозяева (название команды)")
    fb_parser.add_argument("--away", type=str, default="Ливерпуль", help="Гости (название команды)")
    fb_parser.add_argument("--odds1", type=float, default=2.15, help="Кэф на П1")
    fb_parser.add_argument("--oddsX", type=float, default=3.60, help="Кэф на ничью")
    fb_parser.add_argument("--odds2", type=float, default=3.40, help="Кэф на П2")
    fb_parser.add_argument("--over25", type=float, default=1.75, help="Кэф на Тотал Больше 2.5")
    fb_parser.add_argument("--under25", type=float, default=2.10, help="Кэф на Тотал Меньше 2.5")

    # Command 3: Custom event analysis
    custom_parser = subparsers.add_parser("custom", help="Анализ произвольного матча/коэффициентов")
    custom_parser.add_argument("--sport", type=str, default="tennis", help="Вид спорта (football, basketball, tennis, hockey, cs2)")
    custom_parser.add_argument("--name", type=str, default="Янник Синнер vs Карлос Алькарас", help="Название матча")
    custom_parser.add_argument("--odds", nargs="+", type=float, default=[1.72, 2.15], help="Коэффициенты исходов (например: 1.72 2.15)")
    custom_parser.add_argument("--probs", nargs="+", type=float, default=[0.62, 0.38], help="Ваша оценка вероятностей от 0.0 до 1.0 (например: 0.62 0.38)")
    custom_parser.add_argument("--labels", nargs="+", type=str, default=["Победа Синнера", "Победа Алькараса"], help="Названия исходов")

    # Interactive demo if no args
    if len(sys.argv) == 1:
        print_sports_overview()
        print("\n" + "=" * 70)
        print(" ДЕМОНСТРАЦИОННЫЙ РАСЧЕТ МАТЧА АПЛ: Манчестер Сити vs Ливерпуль")
        print("=" * 70)
        analyze_football_match(
            home_team_name="Манчестер Сити",
            away_team_name="Ливерпуль",
            odds_1=2.15,
            odds_x=3.60,
            odds_2=3.40,
            odds_over25=1.75,
            odds_under25=2.10,
        )
        print("\n" + "=" * 70)
        print(" ДЕМОНСТРАЦИОННЫЙ РАСЧЕТ ТЕННИСНОГО МАТЧА (Низкий риск): Синнер vs Алькарас")
        print("=" * 70)
        analyze_custom_odds(
            sport_name="tennis",
            event_name="Янник Синнер vs Карлос Алькарас",
            odds_list=[1.75, 2.15],
            estimated_probs=[0.62, 0.38],
            labels=["П1 (Синнер)", "П2 (Алькарас)"],
        )
        return

    args = parser.parse_args()

    if args.command == "sports":
        print_sports_overview()
    elif args.command == "football":
        analyze_football_match(
            home_team_name=args.home,
            away_team_name=args.away,
            odds_1=args.odds1,
            odds_x=args.oddsX,
            odds_2=args.odds2,
            odds_over25=args.over25,
            odds_under25=args.under25,
        )
    elif args.command == "custom":
        analyze_custom_odds(
            sport_name=args.sport,
            event_name=args.name,
            odds_list=args.odds,
            estimated_probs=args.probs,
            labels=args.labels,
        )


if __name__ == "__main__":
    main()
