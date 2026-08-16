"""
Telegram Bot: Technical Terms Translator (Chinese - English - Russian).
Переводчик технических терминов (Китайский - Английский - Русский).
"""

import os
import sys
import html
import json
import time
import random
import asyncio
import logging
import threading
from typing import Optional, List, Dict
from http.server import HTTPServer, BaseHTTPRequestHandler
import xml.etree.ElementTree as ET

import httpx
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    ContextTypes,
    filters,
)

from translator.models import TechTerm, Language, CategoryInfo
from translator.engine import TerminologyEngine, TechTranslator
from translator.pinyin_helper import detect_language, get_pinyin, is_chinese_text

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Переменные окружения и настройки
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TOKEN = os.getenv("BOT_TOKEN", "8995959559:AAHIrwMnaQpMGELlwrO-WfRh-ulCt65UIJ4")
PORT = int(os.getenv("PORT", 10000))

# Инициализация движка словаря
engine = TerminologyEngine()
translator = TechTranslator(engine)

# Главное меню (Reply Keyboard)
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔍 Поиск термина"), KeyboardButton("📚 Категории")],
        [KeyboardButton("🎲 Случайный термин"), KeyboardButton("🧠 Викторина")],
        [KeyboardButton("📈 Курсы валют"), KeyboardButton("ℹ️ Помощь")],
    ],
    resize_keyboard=True,
)


# === Simple HTTP Server for Render Health Check ===
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Technical Terms Translator Bot is running OK!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def start_health_check_server(port: int):
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Health check HTTP-сервер успешно запущен на порту {port}")
    except Exception as e:
        logger.warning(f"Не удалось запустить health check сервер на порту {port}: {e}")


# === Форматирование карточки термина для Telegram (HTML) ===
def format_term_html(term: TechTerm, compact: bool = False) -> str:
    """Форматирует карточку термина в красивом HTML-виде для Telegram."""
    en_clean = html.escape(term.en)
    zh_clean = html.escape(term.zh)
    ru_clean = html.escape(term.ru)
    pinyin_clean = html.escape(term.pinyin)
    trad_clean = f" [{html.escape(term.zh_trad)}]" if term.zh_trad else ""

    text = (
        f"📘 <b>{en_clean}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🇨🇳 <b>Китайский:</b> <code>{zh_clean}</code>{trad_clean}\n"
        f"   🗣 <i>Pinyin:</i> <code>{pinyin_clean}</code>\n"
        f"🇬🇧 <b>Английский:</b> <code>{en_clean}</code>\n"
        f"🇷🇺 <b>Русский:</b> <code>{ru_clean}</code>\n\n"
    )

    if not compact:
        if term.definition_ru or term.definition_en or term.definition_zh:
            text += "📖 <b>Определения:</b>\n"
            if term.definition_ru:
                text += f"🇷🇺 {html.escape(term.definition_ru)}\n"
            if term.definition_en:
                text += f"🇬🇧 <i>{html.escape(term.definition_en)}</i>\n"
            if term.definition_zh:
                text += f"🇨🇳 {html.escape(term.definition_zh)}\n"
            text += "\n"

        if term.examples:
            text += "💡 <b>Пример употребления:</b>\n"
            ex = term.examples[0]
            text += f"🇬🇧 {html.escape(ex.en)}\n"
            text += f"🇨🇳 {html.escape(ex.zh)}"
            if ex.pinyin:
                text += f" (<i>{html.escape(ex.pinyin)}</i>)"
            text += f"\n🇷🇺 {html.escape(ex.ru)}\n\n"

        synonyms = []
        if term.synonyms_en:
            synonyms.append(f"EN: {', '.join(term.synonyms_en)}")
        if term.synonyms_zh:
            synonyms.append(f"ZH: {', '.join(term.synonyms_zh)}")
        if term.synonyms_ru:
            synonyms.append(f"RU: {', '.join(term.synonyms_ru)}")

        if synonyms:
            text += f"🏷 <b>Синонимы:</b> {html.escape(' | '.join(synonyms))}\n"

        cat_info = engine.get_category_by_id(term.category)
        cat_name = cat_info.name_ru if cat_info else term.category
        text += f"📁 <b>Категория:</b> {cat_name}\n"

    return text


def get_term_keyboard(term: TechTerm) -> InlineKeyboardMarkup:
    """Создает инлайн-кнопки для термина (похожие термины, случайный термин)."""
    buttons = []
    row1 = [
        InlineKeyboardButton("🎲 Другой случайный", callback_data="random_term"),
        InlineKeyboardButton("📚 В категорию", callback_data=f"cat_terms:{term.category}"),
    ]
    buttons.append(row1)

    if term.related_terms:
        rel_buttons = []
        for rel_id in term.related_terms[:2]:
            rel_term = engine.get_term_by_id(rel_id)
            if rel_term:
                rel_buttons.append(
                    InlineKeyboardButton(f"🔗 {rel_term.en}", callback_data=f"show_term:{rel_term.id}")
                )
        if rel_buttons:
            buttons.append(rel_buttons)

    return InlineKeyboardMarkup(buttons)


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 <b>Добро пожаловать в Переводчик технических терминов!</b>\n"
        "🇨🇳 <b>中文</b> | 🇬🇧 <b>English</b> | 🇷🇺 <b>Русский</b>\n\n"
        "Я помогу вам переводить и изучать IT и технические термины на китайском, английском и русском языках.\n\n"
        "✨ <b>Что я умею:</b>\n"
        "• 🔍 <b>Мгновенный поиск:</b> отправьте мне любое слово на русском, английском, китайском (иероглифами или пиньинем)\n"
        "• 📚 <b>Категории:</b> ИИ/ML, разработка ПО, железо, сети, базы данных, DevOps, кибербезопасность\n"
        "• 🗣 <b>Пиньинь с тонами:</b> правильное произношение для каждого китайского термина\n"
        "• 🧠 <b>Викторина:</b> проверяйте знания терминов в интерактивном тесте\n"
        "• 🌐 <b>Онлайн-перевод:</b> перевод любых предложений и фраз\n\n"
        "👇 <i>Попробуйте прямо сейчас: отправьте мне, например, <code>neural network</code>, <code>深度学习</code> или <code>компилятор</code>!</i>"
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KEYBOARD,
    )


# === Команда /help ===
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 <b>Справка по использованию бота:</b>\n\n"
        "🔹 <b>Поиск термина:</b>\n"
        "Просто напишите нужное слово в чат на любом языке:\n"
        "• <code>deep learning</code>\n"
        "• <code>人工智能</code>\n"
        "• <code>многопоточность</code>\n"
        "• <code>shendu xuexi</code> (поиск по пиньиню)\n\n"
        "🔹 <b>Команды:</b>\n"
        "/search &lt;термин&gt; — поиск по базе\n"
        "/categories — список категорий IT-терминов\n"
        "/random — показать случайный термин с примером\n"
        "/quiz — запустить викторину для проверки знаний\n"
        "/translate &lt;текст&gt; — онлайн-перевод текста\n"
        "/price — официальные курсы валют ЦБ РФ\n"
        "/gpu — актуальные цены на популярные видеокарты\n\n"
        "🔹 <b>Инлайн-режим:</b>\n"
        "Вы можете использовать бота в любом чате: напишите <code>@имя_бота deep learning</code> и выберите результат!"
    )
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KEYBOARD,
    )


# === Команда /random ===
async def random_term(update: Update, context: ContextTypes.DEFAULT_TYPE):
    terms = engine.get_random_terms(1)
    if not terms:
        await update.message.reply_text("В базе пока нет терминов.")
        return

    term = terms[0]
    text = f"🎲 <b>Случайный технический термин:</b>\n\n" + format_term_html(term)
    keyboard = get_term_keyboard(term)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


# === Команда /categories ===
async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cats = engine.get_all_categories()
    text = (
        "📚 <b>Категории технических терминов:</b>\n\n"
        "Выберите интересующий раздел, чтобы просмотреть термины 👇"
    )
    keyboard_buttons = []
    for cat in cats:
        count = len(engine.get_terms_by_category(cat.id))
        btn_text = f"{cat.icon} {cat.name_ru} ({count})"
        keyboard_buttons.append([InlineKeyboardButton(btn_text, callback_data=f"cat_terms:{cat.id}")])

    markup = InlineKeyboardMarkup(keyboard_buttons)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


# === Викторина / Flashcard Quiz ===
async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    terms = engine.get_random_terms(4)
    if len(terms) < 4:
        await update.message.reply_text("Недостаточно терминов для викторины.")
        return

    target = terms[0]
    options = terms[:]
    random.shuffle(options)

    # Сохраняем правильный ответ в user_data
    correct_idx = options.index(target)

    question_text = (
        "🧠 <b>Викторина по IT-терминам!</b>\n\n"
        f"Что означает китайский термин:\n"
        f"🇨🇳 <b><code>{html.escape(target.zh)}</code></b> (<i>{html.escape(target.pinyin)}</i>)?\n\n"
        "Выберите правильный вариант перевода 👇"
    )

    buttons = []
    for i, opt in enumerate(options):
        btn_text = f"{i + 1}. {opt.en} — {opt.ru}"
        cb_data = f"quiz_ans:{i}:{correct_idx}:{target.id}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])

    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(question_text, parse_mode=ParseMode.HTML, reply_markup=markup)


# === Обработка текстового поиска и сообщений ===
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    if not user_text:
        return

    # Обработка нажатий на постоянные кнопки
    if user_text == "🔍 Поиск термина":
        await update.message.reply_text(
            "🔍 Введите слово или термин на русском, английском или китайском (иероглифы или пиньинь):",
            reply_markup=MAIN_KEYBOARD,
        )
        return
    elif user_text == "📚 Категории":
        await categories_command(update, context)
        return
    elif user_text == "🎲 Случайный термин":
        await random_term(update, context)
        return
    elif user_text == "🧠 Викторина":
        await quiz_command(update, context)
        return
    elif "Курсы валют" in user_text:
        await price(update, context)
        return
    elif "Помощь" in user_text:
        await help_command(update, context)
        return

    # Поиск термина через TerminologyEngine / TechTranslator
    output = await translator.translate(user_text)

    if output.direct_match:
        # Точное совпадение
        card = format_term_html(output.direct_match)
        keyboard = get_term_keyboard(output.direct_match)
        await update.message.reply_text(card, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    elif output.search_results:
        # Несколько похожих результатов
        response_text = f"🔍 <b>Результаты поиска по запросу '<code>{html.escape(user_text)}</code>':</b>\n\n"
        buttons = []

        for i, res in enumerate(output.search_results[:5], 1):
            t = res.term
            match_pct = int(res.score * 100)
            response_text += (
                f"{i}. <b>{html.escape(t.en)}</b> ↔ <b>{html.escape(t.zh)}</b> (<i>{html.escape(t.pinyin)}</i>)\n"
                f"   🇷🇺 {html.escape(t.ru)}\n\n"
            )
            buttons.append([
                InlineKeyboardButton(
                    f"📖 {t.en} ({match_pct}%)",
                    callback_data=f"show_term:{t.id}",
                )
            ])

        markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(response_text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        # Термин не найден в словаре -> онлайн перевод
        det_lang = output.detected_lang.display_name_ru
        response_text = (
            f"ℹ️ Термин '<b>{html.escape(user_text)}</b>' не найден в словаре.\n"
            f"Определен язык: <i>{det_lang}</i>\n\n"
        )

        if output.pinyin:
            response_text += f"🇨🇳 <b>Pinyin:</b> <code>{html.escape(output.pinyin)}</code>\n\n"

        if output.online_translations:
            response_text += "🌐 <b>Онлайн-перевод:</b>\n"
            for lang, trans_text in output.online_translations.items():
                flag = "🇬🇧" if lang == "en" else "🇷🇺" if lang == "ru" else "🇨🇳"
                response_text += f"{flag} {html.escape(trans_text)}\n"
        else:
            response_text += "Попробуйте изменить формулировку или проверьте правильность написания."

        await update.message.reply_text(
            response_text,
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KEYBOARD,
        )


# === Обработка нажатий на инлайн-кнопки (Callback Query) ===
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "random_term":
        terms = engine.get_random_terms(1)
        if terms:
            term = terms[0]
            text = f"🎲 <b>Случайный технический термин:</b>\n\n" + format_term_html(term)
            keyboard = get_term_keyboard(term)
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    elif data.startswith("show_term:"):
        term_id = data.split(":", 1)[1]
        term = engine.get_term_by_id(term_id)
        if term:
            text = format_term_html(term)
            keyboard = get_term_keyboard(term)
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    elif data.startswith("cat_terms:"):
        cat_id = data.split(":", 1)[1]
        cat = engine.get_category_by_id(cat_id)
        terms = engine.get_terms_by_category(cat_id)

        cat_title = f"{cat.icon} {cat.name_ru}" if cat else cat_id
        text = f"📚 <b>Категория: {cat_title}</b>\n\nВыберите термин для подробного описания:"

        buttons = []
        for t in terms:
            buttons.append([
                InlineKeyboardButton(f"{t.en} ↔ {t.zh}", callback_data=f"show_term:{t.id}")
            ])
        buttons.append([InlineKeyboardButton("◀️ Ко всем категориям", callback_data="all_categories")])

        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)

    elif data == "all_categories":
        cats = engine.get_all_categories()
        text = "📚 <b>Категории технических терминов:</b>\n\nВыберите категорию 👇"
        buttons = []
        for cat in cats:
            count = len(engine.get_terms_by_category(cat.id))
            btn_text = f"{cat.icon} {cat.name_ru} ({count})"
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"cat_terms:{cat.id}")])
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)

    elif data.startswith("quiz_ans:"):
        _, selected_str, correct_str, target_id = data.split(":")
        selected_idx = int(selected_str)
        correct_idx = int(correct_str)
        term = engine.get_term_by_id(target_id)

        if selected_idx == correct_idx:
            result_header = "🎉 <b>Правильно! Отличная работа!</b>\n\n"
        else:
            result_header = "❌ <b>Неправильно.</b>\n\n"

        if term:
            text = result_header + format_term_html(term)
        else:
            text = result_header

        buttons = [
            [InlineKeyboardButton("🧠 Следующий вопрос", callback_data="next_quiz")],
            [InlineKeyboardButton("🎲 Случайный термин", callback_data="random_term")],
        ]
        markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)

    elif data == "next_quiz":
        terms = engine.get_random_terms(4)
        if len(terms) >= 4:
            target = terms[0]
            options = terms[:]
            random.shuffle(options)
            correct_idx = options.index(target)

            question_text = (
                "🧠 <b>Викторина по IT-терминам!</b>\n\n"
                f"Что означает китайский термин:\n"
                f"🇨🇳 <b><code>{html.escape(target.zh)}</code></b> (<i>{html.escape(target.pinyin)}</i>)?\n\n"
                "Выберите правильный вариант перевода 👇"
            )

            buttons = []
            for i, opt in enumerate(options):
                btn_text = f"{i + 1}. {opt.en} — {opt.ru}"
                cb_data = f"quiz_ans:{i}:{correct_idx}:{target.id}"
                buttons.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])

            markup = InlineKeyboardMarkup(buttons)
            await query.edit_message_text(question_text, parse_mode=ParseMode.HTML, reply_markup=markup)


# === Инлайн-поиск (Inline Query Handler) ===
async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    results = []

    if not query:
        # Показываем случайные популярные термины
        terms = engine.get_random_terms(5)
    else:
        search_res = engine.search(query, limit=10, min_score=0.4)
        terms = [r.term for r in search_res]

    for term in terms:
        msg_content = format_term_html(term)
        item = InlineQueryResultArticle(
            id=term.id,
            title=f"{term.en} ↔ {term.zh} ({term.pinyin})",
            description=f"🇷🇺 {term.ru} | 🇨🇳 {term.zh}",
            input_message_content=InputTextMessageContent(
                msg_content,
                parse_mode=ParseMode.HTML,
            ),
        )
        results.append(item)

    await update.inline_query.answer(results, cache_time=10)


# === Команда получения курсов валют (ЦБ РФ) ===
async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Запрашиваю курсы через API ЦБ РФ... Подожди секунду.")
    try:
        url = "https://www.cbr.ru/scripts/XML_daily.asp"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            xml_data = response.content

        root = ET.fromstring(xml_data)

        usd_price = "Не найден"
        cny_price = "Не найден"
        eur_price = "Не найден"

        for valute in root.findall("Valute"):
            char_code = valute.find("CharCode")
            value = valute.find("Value")
            nominal = valute.find("Nominal")

            if char_code is not None and value is not None:
                code = char_code.text.strip()
                val = value.text.strip().replace(",", ".")
                nom = int(nominal.text.strip()) if nominal is not None and nominal.text else 1
                unit_val = float(val) / nom

                if code == "USD":
                    usd_price = f"{unit_val:.2f}"
                elif code == "CNY":
                    cny_price = f"{unit_val:.2f}"
                elif code == "EUR":
                    eur_price = f"{unit_val:.2f}"

        message_text = (
            "🏦 <b>Официальные курсы валют (ЦБ РФ):</b>\n\n"
            f"🇺🇸 <b>Доллар США (USD):</b> {usd_price} ₽\n"
            f"🇨🇳 <b>Китайский юань (CNY):</b> {cny_price} ₽\n"
            f"🇪🇺 <b>Евро (EUR):</b> {eur_price} ₽"
        )
        await update.message.reply_text(
            message_text,
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KEYBOARD,
        )
    except Exception as e:
        logger.error(f"Ошибка при запросе курсов: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Ошибка получения курсов валют: {html.escape(str(e))}",
            reply_markup=MAIN_KEYBOARD,
        )


# === Сборка приложения Telegram бота ===
def build_application():
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("random", random_term))
    app.add_handler(CommandHandler("categories", categories_command))
    app.add_handler(CommandHandler("category", categories_command))
    app.add_handler(CommandHandler("quiz", quiz_command))
    app.add_handler(CommandHandler("price", price))

    # Обработчик инлайн-кнопок
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Обработчик инлайн-режима
    app.add_handler(InlineQueryHandler(inline_query_handler))

    # Текстовые сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


# === Главная функция запуска ===
def main():
    start_health_check_server(PORT)

    application = build_application()

    print("\n" + "=" * 60)
    print("🤖 Бот-переводчик технических терминов (ZH - EN - RU) запущен!")
    print(f"📚 Загружено терминов: {len(engine.terms)}")
    print(f"📁 Загружено категорий: {len(engine.categories)}")
    print("=" * 60 + "\n")

    application.run_polling(
        poll_interval=1.0,
        timeout=30,
        bootstrap_retries=-1,
    )


if __name__ == "__main__":
    main()
