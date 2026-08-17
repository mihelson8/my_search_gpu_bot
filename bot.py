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
from translator.voice_helper import generate_tts_audio, recognize_speech_from_ogg

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

# Главное меню (Reply Keyboard) с удобным выбором языков и режимов
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🇷🇺 Русский"), KeyboardButton("🇬🇧 English")],
        [KeyboardButton("🇨🇳 Путунхуа"), KeyboardButton("🇭🇰 Кантонский / Байхуа")],
        [KeyboardButton("🔍 Поиск термина"), KeyboardButton("📚 Категории")],
        [KeyboardButton("🎲 Случайная фраза"), KeyboardButton("🧠 Викторина")],
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
        # Bind to 0.0.0.0 and handle port reuse cleanly
        class ReusableHTTPServer(HTTPServer):
            allow_reuse_address = True

        server = ReusableHTTPServer(("0.0.0.0", port), HealthCheckHandler)
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
        f"📘 <b>{ru_clean} ↔ {zh_clean} ↔ {en_clean}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🇷🇺 <b>Русский:</b> <code>{ru_clean}</code>\n"
        f"🇨🇳 <b>Путунхуа (Mandarin):</b> <code>{zh_clean}</code>\n"
        f"   🗣 <i>Pinyin:</i> <code>{pinyin_clean}</code>\n"
        f"🇭🇰 <b>Кантонский / Байхуа:</b> <code>{zh_clean}</code>{trad_clean}\n"
        f"🇬🇧 <b>English:</b> <code>{en_clean}</code>\n\n"
    )

    if not compact:
        if term.definition_ru or term.definition_en or term.definition_zh:
            text += "📖 <b>Определения / Пояснения:</b>\n"
            if term.definition_ru:
                text += f"🇷🇺 {html.escape(term.definition_ru)}\n"
            if term.definition_en:
                text += f"🇬🇧 <i>{html.escape(term.definition_en)}</i>\n"
            if term.definition_zh:
                text += f"🇨🇳 {html.escape(term.definition_zh)}\n"
            text += "\n"

        if term.examples:
            text += "💡 <b>Пример употребления в речи:</b>\n"
            ex = term.examples[0]
            text += f"🇷🇺 {html.escape(ex.ru)}\n"
            text += f"🇨🇳 {html.escape(ex.zh)}"
            if ex.pinyin:
                text += f" (<i>{html.escape(ex.pinyin)}</i>)"
            text += f"\n🇬🇧 {html.escape(ex.en)}\n\n"

        synonyms = []
        if term.synonyms_ru:
            synonyms.append(f"RU: {', '.join(term.synonyms_ru)}")
        if term.synonyms_zh:
            synonyms.append(f"ZH: {', '.join(term.synonyms_zh)}")
        if term.synonyms_en:
            synonyms.append(f"EN: {', '.join(term.synonyms_en)}")

        if synonyms:
            text += f"🏷 <b>Синонимы:</b> {html.escape(' | '.join(synonyms))}\n"

        cat_info = engine.get_category_by_id(term.category)
        cat_name = cat_info.name_ru if cat_info else term.category
        text += f"📁 <b>Категория:</b> {cat_name}\n"

    return text


def get_term_keyboard(term: TechTerm) -> InlineKeyboardMarkup:
    """Создает инлайн-кнопки для термина (озвучка Путунхуа/Байхуа/Русский/English, похожие термины, случайный термин)."""
    buttons = []
    row_voice1 = [
        InlineKeyboardButton("🔊 Путунхуа (Mandarin)", callback_data=f"voice:zh:{term.id}"),
        InlineKeyboardButton("🔊 Байхуа (Cantonese)", callback_data=f"voice:yue:{term.id}"),
    ]
    buttons.append(row_voice1)

    row_voice2 = [
        InlineKeyboardButton("🔊 Озвучить (Русский)", callback_data=f"voice:ru:{term.id}"),
        InlineKeyboardButton("🔊 Озвучить (English)", callback_data=f"voice:en:{term.id}"),
    ]
    buttons.append(row_voice2)

    row_nav = [
        InlineKeyboardButton("🎲 Другой случайный", callback_data="random_term"),
        InlineKeyboardButton("📚 В категорию", callback_data=f"cat_terms:{term.category}"),
    ]
    buttons.append(row_nav)

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


def get_online_translation_keyboard(output_translations: dict, query: str = "") -> InlineKeyboardMarkup:
    """Создает инлайн-кнопки озвучки для любого онлайн-перевода произвольного текста."""
    buttons = []
    row_voice1 = []
    if "zh" in output_translations or is_chinese_text(query):
        row_voice1.append(InlineKeyboardButton("🔊 Путунхуа", callback_data="voice_txt:zh"))
        row_voice1.append(InlineKeyboardButton("🔊 Кантонский", callback_data="voice_txt:yue"))
    if row_voice1:
        buttons.append(row_voice1)

    row_voice2 = []
    if "ru" in output_translations or not is_chinese_text(query):
        row_voice2.append(InlineKeyboardButton("🔊 Русский", callback_data="voice_txt:ru"))
    if "en" in output_translations:
        row_voice2.append(InlineKeyboardButton("🔊 English", callback_data="voice_txt:en"))
    if row_voice2:
        buttons.append(row_voice2)

    return InlineKeyboardMarkup(buttons)


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 <b>Добро пожаловать в Переводчик терминов и разговорной речи!</b>\n"
        "🇨🇳 <b>中文 (Путунхуа & Байхуа)</b> | 🇬🇧 <b>English</b> | 🇷🇺 <b>Русский</b>\n\n"
        "Я помогу вам переводить и изучать как <b>IT/технические термины</b>, так и <b>повседневные разговорные фразы</b> на китайском, английском и русском языках.\n\n"
        "✨ <b>Что я умею:</b>\n"
        "• 🔍 <b>Мгновенный поиск:</b> отправьте любое слово или фразу текстом (на русском, английском, китайском или пиньине)\n"
        "• 🎙 <b>Голосовой перевод:</b> отправляйте голосовые сообщения на русском, английском, путунхуа или байхуа\n"
        "• 🔊 <b>Озвучка произношения:</b> кнопки воспроизведения на Путунхуа (Mandarin), Байхуа (Кантонском), Русском и English\n"
        "• 🔤 <b>Основное меню:</b> удобные кнопки языков [🇷🇺 Русский] [🇬🇧 English] [🇨🇳 Путунхуа] [🇭🇰 Кантонский]\n"
        "• 📚 <b>Разделы словаря:</b>\n"
        "   💬 <i>Повседневное общение, рестораны, покупки, отели, такси, офис</i>\n"
        "   🤖 <i>IT, искусственный интеллект, программирование, базы данных, сети, железо</i>\n"
        "• 🗣 <b>Пиньинь с тонами:</b> правильное произношение для каждого китайского выражения\n"
        "• 🧠 <b>Викторина:</b> проверяйте знания слов и фраз в интерактивном тесте\n"
        "• 🌐 <b>Онлайн-перевод:</b> перевод любых длинных предложений и диалогов\n\n"
        "👇 <i>Попробуйте прямо сейчас: напишите, например, <code>спасибо</code>, <code>多少钱</code>, <code>neural network</code> или отправьте голосовое сообщение!</i>"
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
    if user_text == "🇷🇺 Русский":
        await update.message.reply_text(
            "🇷🇺 <b>Режим русского языка:</b>\n"
            "Напишите или наговорите голосом фразу на русском языке — бот переведет её на Путунхуа, Кантонский (Байхуа) и English, покажет пиньинь и озвучит на всех языках!",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KEYBOARD,
        )
        return
    elif user_text == "🇬🇧 English":
        await update.message.reply_text(
            "🇬🇧 <b>English Mode:</b>\n"
            "Type or voice any phrase in English — the bot will translate it to Russian, Mandarin, and Cantonese with full audio pronunciation and Pinyin!",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KEYBOARD,
        )
        return
    elif user_text == "🇨🇳 Путунхуа":
        await update.message.reply_text(
            "🇨🇳 <b>Режим Путунхуа (Mandarin):</b>\n"
            "Напишите иероглифами, пиньинем или наговорите фразу на китайском — бот выдаст перевод на русский и английский с озвучкой на русском, кантонском и путунхуа!",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KEYBOARD,
        )
        return
    elif user_text == "🇭🇰 Кантонский / Байхуа":
        await update.message.reply_text(
            "🇭🇰 <b>Режим Кантонского языка / Байхуа (Cantonese):</b>\n"
            "Напишите или наговорите фразу на кантонском/байхуа — бот переведет её на русский, английский и путунхуа и предложит послушать произношение на всех языках!",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KEYBOARD,
        )
        return
    elif user_text == "🔍 Поиск термина":
        await update.message.reply_text(
            "🔍 Введите слово или фразу на русском, английском, путунхуа или кантонском (иероглифы или пиньинь):",
            reply_markup=MAIN_KEYBOARD,
        )
        return
    elif user_text == "📚 Категории":
        await categories_command(update, context)
        return
    elif user_text in ["🎲 Случайный термин", "🎲 Случайная фраза"]:
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
            f"🌐 <b>Перевод фразы «<code>{html.escape(user_text)}</code>»:</b>\n"
            f"<i>Определен язык: {det_lang}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Сохраняем переводы в user_data для озвучки по кнопкам
        context.user_data["last_translations"] = output.online_translations
        context.user_data["last_query"] = user_text
        context.user_data["last_detected_lang"] = output.detected_lang.value

        # Отображаем переводы по всем ключевым языкам
        if output.detected_lang != Language.RU:
            ru_val = output.online_translations.get("ru", "")
            if ru_val:
                response_text += f"🇷🇺 <b>Русский:</b> <code>{html.escape(ru_val)}</code>\n"

        if output.detected_lang != Language.ZH:
            zh_val = output.online_translations.get("zh", "")
            if zh_val:
                zh_py = get_pinyin(zh_val)
                response_text += f"🇨🇳 <b>Путунхуа (Mandarin):</b> <code>{html.escape(zh_val)}</code>\n"
                if zh_py:
                    response_text += f"   🗣 <i>Pinyin:</i> <code>{html.escape(zh_py)}</code>\n"
                response_text += f"🇭🇰 <b>Кантонский / Байхуа:</b> <code>{html.escape(zh_val)}</code>\n"
        else:
            # Исходный китайский
            py = output.pinyin or get_pinyin(user_text)
            response_text += f"🇨🇳 <b>Путунхуа (Mandarin):</b> <code>{html.escape(user_text)}</code>\n"
            if py:
                response_text += f"   🗣 <i>Pinyin:</i> <code>{html.escape(py)}</code>\n"
            response_text += f"🇭🇰 <b>Кантонский / Байхуа:</b> <code>{html.escape(user_text)}</code>\n"

        if output.detected_lang != Language.EN:
            en_val = output.online_translations.get("en", "")
            if en_val:
                response_text += f"🇬🇧 <b>English:</b> <code>{html.escape(en_val)}</code>\n"

        keyboard = get_online_translation_keyboard(output.online_translations, user_text)

        await update.message.reply_text(
            response_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )


# === Обработка голосовых сообщений (Voice Input) ===
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.voice:
        return

    await update.message.reply_text("🎙 <i>Распознаю голосовое сообщение...</i>", parse_mode=ParseMode.HTML)

    try:
        voice_file = await update.message.voice.get_file()
        ogg_bytes = await voice_file.download_as_bytearray()

        text, detected_lang = recognize_speech_from_ogg(bytes(ogg_bytes))

        if not text:
            await update.message.reply_text(
                "❌ Не удалось распознать речь. Попробуйте сказать четче или написать текстом.",
                reply_markup=MAIN_KEYBOARD,
            )
            return

        lang_name = detected_lang.display_name_ru if detected_lang else "Авто"
        await update.message.reply_text(
            f"🗣 <b>Распознано:</b> «<code>{html.escape(text)}</code>» <i>({lang_name})</i>\n"
            f"🔍 Ищу перевод...",
            parse_mode=ParseMode.HTML,
        )

        # Выполняем поиск/перевод по распознанному тексту
        output = await translator.translate(text)

        if output.direct_match:
            card = format_term_html(output.direct_match)
            keyboard = get_term_keyboard(output.direct_match)
            await update.message.reply_text(card, parse_mode=ParseMode.HTML, reply_markup=keyboard)

            # Если пользователь сказал на китайском, озвучиваем русский перевод, иначе китайский
            if detected_lang == Language.ZH or is_chinese_text(text):
                audio_io = generate_tts_audio(output.direct_match.ru, lang="ru")
                caption_text = f"🔊 Перевод на русском: {output.direct_match.ru}"
            else:
                audio_io = generate_tts_audio(output.direct_match.zh, lang="zh")
                caption_text = f"🔊 Произношение: {output.direct_match.zh} ({output.direct_match.pinyin})"

            if audio_io:
                await update.message.reply_voice(
                    voice=audio_io,
                    caption=caption_text,
                )
        elif output.search_results:
            response_text = f"🔍 <b>Результаты поиска по запросу '<code>{html.escape(text)}</code>':</b>\n\n"
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
            response_text = (
                f"🌐 <b>Перевод голосовой фразы «<code>{html.escape(text)}</code>»:</b>\n"
                f"<i>Определен язык: {lang_name}</i>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            # Сохраняем переводы в user_data для озвучки по кнопкам
            context.user_data["last_translations"] = output.online_translations
            context.user_data["last_query"] = text
            context.user_data["last_detected_lang"] = output.detected_lang.value

            if output.detected_lang != Language.RU:
                ru_val = output.online_translations.get("ru", "")
                if ru_val:
                    response_text += f"🇷🇺 <b>Русский:</b> <code>{html.escape(ru_val)}</code>\n"

            if output.detected_lang != Language.ZH:
                zh_val = output.online_translations.get("zh", "")
                if zh_val:
                    zh_py = get_pinyin(zh_val)
                    response_text += f"🇨🇳 <b>Путунхуа (Mandarin):</b> <code>{html.escape(zh_val)}</code>\n"
                    if zh_py:
                        response_text += f"   🗣 <i>Pinyin:</i> <code>{html.escape(zh_py)}</code>\n"
                    response_text += f"🇭🇰 <b>Кантонский / Байхуа:</b> <code>{html.escape(zh_val)}</code>\n"
            else:
                py = output.pinyin or get_pinyin(text)
                response_text += f"🇨🇳 <b>Путунхуа (Mandarin):</b> <code>{html.escape(text)}</code>\n"
                if py:
                    response_text += f"   🗣 <i>Pinyin:</i> <code>{html.escape(py)}</code>\n"
                response_text += f"🇭🇰 <b>Кантонский / Байхуа:</b> <code>{html.escape(text)}</code>\n"

            if output.detected_lang != Language.EN:
                en_val = output.online_translations.get("en", "")
                if en_val:
                    response_text += f"🇬🇧 <b>English:</b> <code>{html.escape(en_val)}</code>\n"

            keyboard = get_online_translation_keyboard(output.online_translations, text)
            await update.message.reply_text(response_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

            # Автоматическая озвучка: если спросили на китайском — озвучиваем русский перевод, если на русском — китайский
            if (detected_lang == Language.ZH or is_chinese_text(text)) and "ru" in output.online_translations:
                ru_text = output.online_translations["ru"]
                try:
                    audio_io = generate_tts_audio(ru_text, lang="ru")
                    if audio_io:
                        await update.message.reply_voice(voice=audio_io, caption=f"🔊 Перевод (RU): {ru_text}")
                except Exception as ex_tts:
                    logger.warning(f"Voice Russian TTS reply failed: {ex_tts}")
            elif "zh" in output.online_translations:
                zh_text = output.online_translations["zh"]
                try:
                    audio_io = generate_tts_audio(zh_text, lang="zh")
                    if audio_io:
                        await update.message.reply_voice(voice=audio_io, caption=f"🔊 Произношение (ZH): {zh_text}")
                except Exception as ex_tts:
                    logger.warning(f"Voice Chinese TTS reply failed: {ex_tts}")

    except Exception as e:
        logger.error(f"Error handling voice message: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при обработке голосового сообщения. Попробуйте еще раз.")


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

    elif data.startswith("voice:"):
        parts = data.split(":")
        lang_code = parts[1]
        term_id = parts[2]
        term = engine.get_term_by_id(term_id)
        if term:
            if lang_code in ["zh", "yue"]:
                text_to_speak = term.zh
            elif lang_code == "ru":
                text_to_speak = term.ru
            else:
                text_to_speak = term.en

            audio_io = generate_tts_audio(text_to_speak, lang=lang_code)
            if audio_io:
                if lang_code == "yue":
                    caption = f"🇨🇳 <b>{html.escape(text_to_speak)}</b> <i>(Байхуа / Кантонский)</i>"
                elif lang_code == "zh":
                    caption = f"🇨🇳 <b>{html.escape(text_to_speak)}</b>"
                    if term.pinyin:
                        caption += f" (<i>{html.escape(term.pinyin)}</i>)"
                elif lang_code == "ru":
                    caption = f"🇷🇺 <b>{html.escape(text_to_speak)}</b>"
                else:
                    caption = f"🇬🇧 <b>{html.escape(text_to_speak)}</b>"

                await query.message.reply_voice(
                    voice=audio_io,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            else:
                await query.message.reply_text("❌ Не удалось сгенерировать озвучку.")

    elif data.startswith("voice_txt:"):
        lang_code = data.split(":", 1)[1]
        translations = context.user_data.get("last_translations", {})
        query_text = context.user_data.get("last_query", "")
        detected_lang = context.user_data.get("last_detected_lang", "")

        text_to_speak = ""
        if lang_code in ["zh", "yue"]:
            if detected_lang == Language.ZH.value or is_chinese_text(query_text):
                text_to_speak = query_text
            else:
                text_to_speak = translations.get("zh", "")
        elif lang_code == "ru":
            if detected_lang == Language.RU.value:
                text_to_speak = query_text
            else:
                text_to_speak = translations.get("ru", "")
        elif lang_code == "en":
            if detected_lang == Language.EN.value:
                text_to_speak = query_text
            else:
                text_to_speak = translations.get("en", "")

        if text_to_speak:
            audio_io = generate_tts_audio(text_to_speak, lang=lang_code)
            if audio_io:
                if lang_code == "yue":
                    cap = f"🇭🇰 <b>{html.escape(text_to_speak)}</b> <i>(Кантонский / Байхуа)</i>"
                elif lang_code == "zh":
                    py = get_pinyin(text_to_speak)
                    cap = f"🇨🇳 <b>{html.escape(text_to_speak)}</b>"
                    if py:
                        cap += f" (<i>{html.escape(py)}</i>)"
                elif lang_code == "ru":
                    cap = f"🇷🇺 <b>{html.escape(text_to_speak)}</b>"
                else:
                    cap = f"🇬🇧 <b>{html.escape(text_to_speak)}</b>"

                await query.message.reply_voice(
                    voice=audio_io,
                    caption=cap,
                    parse_mode=ParseMode.HTML,
                )
            else:
                await query.message.reply_text("❌ Не удалось сгенерировать озвучку.")
        else:
            await query.message.reply_text("❌ Текст для озвучки не найден.")

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
        .connect_timeout(10.0)
        .read_timeout(10.0)
        .write_timeout(10.0)
        .pool_timeout(10.0)
        .concurrent_updates(True)
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

    # Голосовые сообщения (Voice Input)
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    return app


# === Главная функция запуска ===
def main():
    start_health_check_server(PORT)

    application = build_application()

    print("\n" + "=" * 60, flush=True)
    print("🤖 Бот-переводчик технических терминов (ZH - EN - RU) запущен!", flush=True)
    print(f"📚 Загружено терминов: {len(engine.terms)}", flush=True)
    print(f"📁 Загружено категорий: {len(engine.categories)}", flush=True)
    print(f"🌐 Health check порт: {PORT}", flush=True)
    print("=" * 60 + "\n", flush=True)

    application.run_polling(
        poll_interval=0.2,
        timeout=10,
        bootstrap_retries=-1,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
