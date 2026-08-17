"""
Telegram Bot for Sports Betting Analytics and Risk Assessment.
Телеграм-бот для спортивной аналитики, анализа рисков, сравнения коэффициентов и расчета ставок.
"""

import os
import sys
import html
import logging
from typing import Optional, List, Dict

try:
    from telegram import (
        Update,
        ReplyKeyboardMarkup,
        KeyboardButton,
        InlineKeyboardMarkup,
        InlineKeyboardButton,
    )
    from telegram.constants import ParseMode
    from telegram.ext import (
        ApplicationBuilder,
        CommandHandler,
        MessageHandler,
        CallbackQueryHandler,
        ContextTypes,
        filters,
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

from sports_analytics.engine import (
    RiskLevel,
    SportType,
    SportsAnalyticsEngine,
    TeamStats,
    OddsAnalysis,
    SPORT_PROFILES,
)
from sports_analytics.data import TEAM_DATABASE

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Главное меню бота
MAIN_KEYBOARD = [
    ["🏆 Виды спорта & Риски", "⚽ Разбор матча (АПЛ / Ла Лига)"],
    ["🎾 Теннис (Низкий риск)", "🏀 Баскетбол (NBA)"],
    ["🧮 Калькулятор Value Bet", "💰 Калькулятор маржи букмекера"],
    ["🛡️ Стратегии банкролла", "ℹ️ О боте & Инструкция"],
]


def format_sports_overview_html() -> str:
    """Форматирует обзор видов спорта и их уровней риска в HTML."""
    text = (
        "🏆 <b>СРАВНЕНИЕ ВИДОВ СПОРТА ПО УРОВНЮ РИСКА</b>\n\n"
        "Чем ниже дисперсия и меньше случайных факторов, тем надежнее аналитическая модель:\n\n"
    )
    
    for st, profile in SPORT_PROFILES.items():
        draw_text = "3 исхода (с ничьей)" if profile.default_draw_possible else "2 исхода (без ничьих)"
        text += (
            f"<b>{profile.name}</b>\n"
            f"• <b>Уровень дисперсии:</b> {profile.base_variance_score:.1f} / 5.0\n"
            f"• <b>Маржа БК:</b> {profile.typical_margin_range[0]}%–{profile.typical_margin_range[1]}%\n"
            f"• <b>Рынок:</b> {draw_text}\n"
            f"• <b>Особенности:</b> {profile.description}\n"
            f"• <b>Безопасные маркеты:</b> <i>{', '.join(profile.recommended_markets)}</i>\n\n"
        )
    
    text += (
        "💡 <b>Вывод:</b> Наименее рискованными для системного анализа являются "
        "<b>Теннис (АТР/WTA)</b> и <b>Баскетбол (NBA/Евролига)</b> из-за высокой плотности событий "
        "и отсутствия ничьих."
    )
    return text


def format_football_match_html(
    home_name: str,
    away_name: str,
    odds_1: float,
    odds_x: float,
    odds_2: float,
) -> str:
    """Форматирует полный анализ футбольного матча в HTML."""
    home = TEAM_DATABASE.get(home_name)
    away = TEAM_DATABASE.get(away_name)

    if not home or not away:
        return f"❌ Команды {home_name} или {away_name} не найдены в базе."

    # Моделирование силы команд
    home_attack = (home.xg_for / max(1, home.played_matches)) / 1.5 * home.home_advantage_factor
    home_defense = (home.xg_against / max(1, home.played_matches)) / 1.2
    away_attack = (away.xg_for / max(1, away.played_matches)) / 1.5
    away_defense = (away.xg_against / max(1, away.played_matches)) / 1.2

    probs = SportsAnalyticsEngine.calculate_football_poisson(
        home_attack_strength=home_attack,
        home_defense_weakness=home_defense,
        away_attack_strength=away_attack,
        away_defense_weakness=away_defense,
    )

    odds_list = [odds_1, odds_x, odds_2]
    margin = SportsAnalyticsEngine.calculate_margin(odds_list)

    a_1 = SportsAnalyticsEngine.analyze_market(
        market_name=f"П1 ({home.name})",
        sport=SportType.FOOTBALL,
        odds=odds_1,
        calculated_prob=probs["home_win"],
        all_market_odds=odds_list,
    )
    a_x = SportsAnalyticsEngine.analyze_market(
        market_name="Ничья (X)",
        sport=SportType.FOOTBALL,
        odds=odds_x,
        calculated_prob=probs["draw"],
        all_market_odds=odds_list,
    )
    a_2 = SportsAnalyticsEngine.analyze_market(
        market_name=f"П2 ({away.name})",
        sport=SportType.FOOTBALL,
        odds=odds_2,
        calculated_prob=probs["away_win"],
        all_market_odds=odds_list,
    )

    calc_1x_odds = round(1.0 / (1.0 / odds_1 + 1.0 / odds_x), 2)
    a_1x = SportsAnalyticsEngine.analyze_market(
        market_name=f"1X ({home.name} не проиграет)",
        sport=SportType.FOOTBALL,
        odds=calc_1x_odds,
        calculated_prob=probs["double_chance_1x"],
        all_market_odds=[calc_1x_odds, odds_2],
    )

    text = (
        f"⚽ <b>АНАЛИЗ МАТЧА: {home.name} vs {away.name}</b>\n\n"
        f"📋 <b>Данные команд:</b>\n"
        f"• {home.name}: Форма {'-'.join(home.form_recent_5)} | xG: {home.xg_for:.1f} | Травмы: {home.key_injuries_count}\n"
        f"• {away.name}: Форма {'-'.join(away.form_recent_5)} | xG: {away.xg_for:.1f} | Травмы: {away.key_injuries_count}\n\n"
        f"📊 <b>Математическая модель (Пуассон + xG):</b>\n"
        f"• Ожидаемые голы: {home.name} <b>{probs['home_exp_goals']:.2f}</b> — <b>{probs['away_exp_goals']:.2f}</b> {away.name}\n"
        f"• Вероятность П1: <b>{probs['home_win']*100:.1f}%</b> (Справедл. кэф: {1/probs['home_win']:.2f})\n"
        f"• Вероятность X:  <b>{probs['draw']*100:.1f}%</b> (Справедл. кэф: {1/probs['draw']:.2f})\n"
        f"• Вероятность П2: <b>{probs['away_win']*100:.1f}%</b> (Справедл. кэф: {1/probs['away_win']:.2f})\n"
        f"• Двойной шанс 1X: <b>{probs['double_chance_1x']*100:.1f}%</b>\n"
        f"• Тотал Б (2.5):  <b>{probs['over_2_5']*100:.1f}%</b>\n\n"
        f"💰 <b>Маржа букмекера:</b> {margin:.2f}%\n\n"
        f"🎯 <b>Сравнение коэффициентов и поиск Value Bets:</b>\n"
    )

    markets = [a_1, a_x, a_2, a_1x]
    for m in markets:
        val_badge = "🔥 <b>[VALUE +EV]</b>" if m.is_value else "❌"
        text += (
            f"• <b>{m.market_name}</b>: Кэф <code>{m.odds:.2f}</code> | "
            f"EV: <code>{m.ev_percent:+.1f}%</code> {val_badge}\n"
            f"  └ Риск: <i>{m.risk_level.value}</i>\n"
        )

    value_markets = [m for m in markets if m.is_value]
    text += "\n🛡️ <b>Рекомендации по ставкам:</b>\n"
    if value_markets:
        for vm in value_markets:
            text += (
                f"✅ <b>{vm.market_name}</b> (Кэф {vm.odds:.2f})\n"
                f"  • Флэт-ставка (безопасная): <b>{vm.recommended_flat_stake_percent:.1f}% от банка</b>\n"
                f"  • Критерий Келли (0.25x): <b>{vm.kelly_stake_percent:.2f}% от банка</b>\n"
            )
    else:
        text += "⚠️ Валуйных исходов (+EV) с достаточным перевесом не найдено. Рекомендуется пропустить матч.\n"

    return text


def format_value_calc_html(odds: float, estimated_prob_percent: float, sport: str = "football") -> str:
    """Форматирует расчет Value Bet и ставки Келли в HTML."""
    prob = estimated_prob_percent / 100.0
    st = SportType.TENNIS if sport.lower() == "tennis" else SportType.FOOTBALL
    
    ev = SportsAnalyticsEngine.calculate_expected_value(prob, odds)
    fair_odds = (1.0 / prob) if prob > 0 else 999.0
    kelly = SportsAnalyticsEngine.kelly_criterion(prob, odds, fraction=0.25)
    risk, expl, flat = SportsAnalyticsEngine.evaluate_bet_risk(sport=st, odds=odds, calculated_prob=prob)

    is_value = ev > 1.5

    text = (
        f"🧮 <b>РАСЧЕТ ВАЛУЙНОСТИ И РИСКОВ (VALUE BET)</b>\n\n"
        f"• Коэффициент букмекера: <code>{odds:.2f}</code>\n"
        f"• Ваша оценка вероятности: <code>{estimated_prob_percent:.1f}%</code>\n"
        f"• Справедливый коэффициент: <code>{fair_odds:.2f}</code>\n\n"
        f"📈 <b>Expected Value (Математическое ожидание):</b> <code>{ev:+.2f}%</code>\n"
        f"Статус: {'🔥 <b>ВАЛУЙНАЯ СТАВКА (+EV)</b>' if is_value else '❌ <b>МИНУСОВАЯ СТАВКА (-EV)</b>'}\n\n"
        f"🛡️ <b>Оценка риска:</b>\n"
        f"• Уровень: <b>{risk.value}</b>\n"
        f"• Описание: <i>{expl}</i>\n\n"
    )

    if is_value:
        text += (
            f"💰 <b>Рекомендуемый размер ставки:</b>\n"
            f"• <b>Флэт (минимальный риск):</b> <code>{flat:.1f}%</code> от банка\n"
            f"• <b>Дробный Келли (0.25x):</b> <code>{kelly:.2f}%</code> от банка\n"
        )
    else:
        text += "⛔ <i>Ставить не рекомендуется, так как букмекерская линия переоценена.</i>"

    return text


def format_margin_calc_html(odds_list: List[float]) -> str:
    """Форматирует расчет маржи букмекера в HTML."""
    margin = SportsAnalyticsEngine.calculate_margin(odds_list)
    fair_probs = SportsAnalyticsEngine.fair_probabilities(odds_list)

    text = (
        f"💰 <b>РАСЧЕТ МАРЖИ БУКМЕКЕРА</b>\n\n"
        f"• Коэффициенты: <code>{' / '.join(f'{o:.2f}' for o in odds_list)}</code>\n"
        f"• <b>Маржа БК:</b> <code>{margin:.2f}%</code>\n\n"
        f"📊 <b>Справедливые вероятности исходов (без маржи):</b>\n"
    )

    for i, (o, p) in enumerate(zip(odds_list, fair_probs)):
        raw_p = (1.0 / o) * 100
        text += f"• Исход {i+1} (кэф {o:.2f}): <b>{p*100:.1f}%</b> (букмекер заложил {raw_p:.1f}%)\n"

    text += "\n💡 <i>Чем ниже маржа (до 3-4%), тем выгоднее ставить на дистанции. Маржа выше 7-8% делает ставки убыточными.</i>"
    return text


def format_bankroll_guide_html() -> str:
    """Форматирует руководство по риск-менеджменту в HTML."""
    return (
        "🛡️ <b>СТРАТЕГИИ УПРАВЛЕНИЯ БАНКРОЛЛОМ (РИСК-МЕНЕДЖМЕНТ)</b>\n\n"
        "Главная причина проигрыша игроков — не ошибки в прогнозах, а неверный выбор суммы ставки.\n\n"
        "<b>1. Стратегия «Фиксированный Флэт» (Наименее рискованная):</b>\n"
        "• Размер ставки: строго <b>1%–2%</b> от первоначального банка.\n"
        "• Не меняется независимо от уверенности или серии проигрышей.\n"
        "• Выдерживает серии до 15–20 неудач подряд без угрозы банкротства.\n\n"
        "<b>2. Дробный критерий Келли (Fractional Kelly 0.25x):</b>\n"
        "• Математически оптимизирует рост капитала при наличии подтвержденного перевеса (Value).\n"
        "• Формула: <code>f = 0.25 × (b*p - q) / b</code>\n"
        "• Автоматически снижает сумму ставки при высоком коэффициенте или спорной вероятности.\n\n"
        "<b>3. Золотые правила дисциплины:</b>\n"
        "❌ Никогда не использовать догон / Мартингейл (гарантирует слив банка при длинной серии).\n"
        "❌ Не отыгрываться сразу после проигрыша (тильт).\n"
        "✅ Вести журнал ставок с фиксацией ROI и коэффициентов закрытия (CLV)."
    )


def format_help_html() -> str:
    """Форматирует инструкцию бота."""
    return (
        "🤖 <b>СПОРТИВНО-АНАЛИТИЧЕСКИЙ БОТ: ИНСТРУКЦИЯ</b>\n\n"
        "Бот помогает анализировать риски, проверять коэффициенты букмекеров и находить математически выгодные ставки (+EV).\n\n"
        "<b>Команды бота:</b>\n"
        "• <code>/sports</code> — обзор видов спорта, маржи и наименее рискованных рынков\n"
        "• <code>/match</code> — аналитический разбор топ-матча (Ман Сити vs Ливерпуль)\n"
        "• <code>/value [кэф] [вероятность%]</code> — быстрый расчет Value Bet (пример: <code>/value 2.15 55</code>)\n"
        "• <code>/margin [кэф1] [кэф2] [кэф3]</code> — расчет маржи букмекера (пример: <code>/margin 1.90 1.90</code>)\n"
        "• <code>/bankroll</code> — правила безопасного управления банком\n\n"
        "Также вы можете использовать удобное кнопочное меню внизу экрана ⬇️"
    )


# Telegram Bot Handlers (if python-telegram-bot is installed)
if TELEGRAM_AVAILABLE:

    async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start."""
        reply_markup = ReplyKeyboardMarkup(
            [[KeyboardButton(text) for text in row] for row in MAIN_KEYBOARD],
            resize_keyboard=True,
        )
        welcome_text = (
            "👋 <b>Добро пожаловать в Спортивно-Аналитический Бот!</b>\n\n"
            "Здесь собраны математические модели (распределение Пуассона, xG), оценка рисков по видам спорта, "
            "расчет маржи букмекеров и алгоритмы поиска валуйных ставок (+EV).\n\n"
            "Выберите интересующий раздел в меню ниже ⬇️"
        )
        if update.message:
            await update.message.reply_text(
                welcome_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )

    async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(format_help_html(), parse_mode=ParseMode.HTML)

    async def sports_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(format_sports_overview_html(), parse_mode=ParseMode.HTML)

    async def match_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            text = format_football_match_html(
                home_name="Манчестер Сити",
                away_name="Ливерпуль",
                odds_1=2.15,
                odds_x=3.60,
                odds_2=3.40,
            )
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def bankroll_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(format_bankroll_guide_html(), parse_mode=ParseMode.HTML)

    async def value_calc_cmd_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not context.args or len(context.args) < 2:
            if update.message:
                await update.message.reply_text(
                    "Использование: <code>/value [коэффициент] [вероятность%]</code>\n"
                    "Пример: <code>/value 2.10 55</code> (кэф 2.10 при оценке вероятности 55%)",
                    parse_mode=ParseMode.HTML,
                )
            return

        try:
            odds = float(context.args[0])
            prob = float(context.args[1])
            res_text = format_value_calc_html(odds, prob)
            await update.message.reply_text(res_text, parse_mode=ParseMode.HTML)
        except ValueError:
            await update.message.reply_text("❌ Ошибка: Введите корректные числа.")

    async def margin_calc_cmd_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not context.args or len(context.args) < 2:
            if update.message:
                await update.message.reply_text(
                    "Использование: <code>/margin [кэф1] [кэф2] [кэф3...]</code>\n"
                    "Пример для 2 исходов: <code>/margin 1.90 1.90</code>\n"
                    "Пример для 3 исходов: <code>/margin 2.10 3.40 3.60</code>",
                    parse_mode=ParseMode.HTML,
                )
            return

        try:
            odds_list = [float(x) for x in context.args]
            res_text = format_margin_calc_html(odds_list)
            await update.message.reply_text(res_text, parse_mode=ParseMode.HTML)
        except ValueError:
            await update.message.reply_text("❌ Ошибка: Введите корректные числа.")

    async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return

        user_text = update.message.text.strip()

        if user_text == "🏆 Виды спорта & Риски":
            await update.message.reply_text(format_sports_overview_html(), parse_mode=ParseMode.HTML)
        elif user_text == "⚽ Разбор матча (АПЛ / Ла Лига)":
            text = format_football_match_html(
                home_name="Манчестер Сити",
                away_name="Ливерпуль",
                odds_1=2.15,
                odds_x=3.60,
                odds_2=3.40,
            )
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        elif user_text == "🎾 Теннис (Низкий риск)":
            tennis_text = (
                "🎾 <b>ТЕННИС: АНАЛИЗ МАТЧА СИННЕР vs АЛЬКАРАС</b>\n\n"
                "• Покрытие: Hard (Открытый)\n"
                "• Янник Синнер: Выигрыш 1-й подачи 88%, Удержание геймов: 91%\n"
                "• Карлос Алькарас: Выигрыш 1-й подачи 85%, Удержание геймов: 87%\n\n"
                "📊 <b>Котировки букмекера:</b>\n"
                "• П1 (Синнер): <code>1.75</code> (Расчетная вероятность: 62%)\n"
                "• П2 (Алькарас): <code>2.15</code> (Расчетная вероятность: 38%)\n\n"
                "🎯 <b>Результат анализа:</b>\n"
                "🔥 <b>Value Bet: Победа Синнера (П1)</b>\n"
                "• Expected Value (EV): <b>+8.5%</b>\n"
                "• Уровень риска: <b>Умеренно-низкий (Moderate Low)</b>\n"
                "• Рекомендуемый флэт: <b>1.5% от банка</b>"
            )
            await update.message.reply_text(tennis_text, parse_mode=ParseMode.HTML)
        elif user_text == "🏀 Баскетбол (NBA)":
            nba_text = (
                "🏀 <b>БАСКЕТБОЛ (NBA): БОСТОН СЕЛТИКС vs ДЕНВЕР НАГГЕТС</b>\n\n"
                "• Темп (Pace): 99.2 владений\n"
                "• Бостон: Офф. рейтинг 121.0 | Защ. рейтинг 110.0\n"
                "• Денвер: Офф. рейтинг 116.0 | Защ. рейтинг 110.5\n\n"
                "📊 <b>Рынок с форой (-4.5 очка на Бостон):</b>\n"
                "• Бостон (-4.5): <code>1.92</code> | Расчетная вер-ть: 54.5%\n"
                "• Денвер (+4.5): <code>1.92</code> | Расчетная вер-ть: 45.5%\n\n"
                "🎯 <b>Результат анализа:</b>\n"
                "🔥 <b>Value Bet: Бостон (-4.5)</b>\n"
                "• Expected Value: <b>+4.6%</b>\n"
                "• Уровень риска: <b>Умеренно-низкий</b>\n"
                "• Рекомендуемый флэт: <b>1.5% от банка</b>"
            )
            await update.message.reply_text(nba_text, parse_mode=ParseMode.HTML)
        elif user_text == "🧮 Калькулятор Value Bet":
            demo_calc = format_value_calc_html(odds=2.15, estimated_prob_percent=55.0)
            hint = "\n\n<i>Чтобы рассчитать свой коэффициент, отправьте:</i> <code>/value [кэф] [вероятность%]</code>"
            await update.message.reply_text(demo_calc + hint, parse_mode=ParseMode.HTML)
        elif user_text == "💰 Калькулятор маржи букмекера":
            demo_margin = format_margin_calc_html([1.90, 1.90])
            hint = "\n\n<i>Чтобы рассчитать свою маржу, отправьте:</i> <code>/margin [кэф1] [кэф2] [кэф3]</code>"
            await update.message.reply_text(demo_margin + hint, parse_mode=ParseMode.HTML)
        elif user_text == "🛡️ Стратегии банкролла":
            await update.message.reply_text(format_bankroll_guide_html(), parse_mode=ParseMode.HTML)
        elif user_text == "ℹ️ О боте & Инструкция":
            await update.message.reply_text(format_help_html(), parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(
                "Используйте кнопки меню ниже или команду <code>/help</code> для справки.",
                parse_mode=ParseMode.HTML,
            )


def build_sports_bot_application(token: str):
    """Создает и настраивает экземпляр Application для Telegram-бота."""
    if not TELEGRAM_AVAILABLE:
        raise RuntimeError("python-telegram-bot не установлен.")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("sports", sports_handler))
    app.add_handler(CommandHandler("match", match_handler))
    app.add_handler(CommandHandler("bankroll", bankroll_handler))
    app.add_handler(CommandHandler("value", value_calc_cmd_handler))
    app.add_handler(CommandHandler("margin", margin_calc_cmd_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    return app


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("Ошибка: Переменная окружения BOT_TOKEN не установлена.")
        print("Установите токен: export BOT_TOKEN='your_token'")
        print("Или запустите консольный скрипт: python3 sports_analytics_cli.py")
        sys.exit(1)

    print("Запуск Спортивно-Аналитического Telegram Бота...")
    app = build_sports_bot_application(token)
    app.run_polling()


if __name__ == "__main__":
    main()
