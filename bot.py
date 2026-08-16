import os
import sys
import html
import re
import json
import time
import asyncio
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import xml.etree.ElementTree as ET

import httpx
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = os.getenv("BOT_TOKEN", "8914024807:AAFUXerMus2OEkbfUCt0H_II70ac1IbzH48")
PORT = int(os.getenv("PORT", 10000))
SERVICE_URL = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("WEBHOOK_URL") or "https://my-search-gpu-bot-1.onrender.com"

CACHE_FILE = "gpu_prices.json"
CACHE_EXPIRATION = 24 * 60 * 60  # 24 часа (раз в сутки)

# Резервный список цен
FALLBACK_GPU = [
    ("NVIDIA GeForce RTX 5060 Palit Dual 8GB", "45 990 ₽"),
    ("NVIDIA GeForce RTX 5060 Ti Palit Infinity 3 16GB", "74 990 ₽"),
    ("NVIDIA GeForce RTX 5070 Palit Infinity 3 12GB", "82 990 ₽"),
    ("NVIDIA GeForce RTX 5070 Gigabyte WINDFORCE OC 12GB", "85 990 ₽"),
    ("NVIDIA GeForce RTX 5070 Ti Palit GamingPro OC 16GB", "124 990 ₽"),
    ("NVIDIA GeForce RTX 3060 MSI VENTUS 2X 12GB", "45 990 ₽"),
    ("NVIDIA GeForce RTX 5080 Gigabyte Gaming OC 16GB", "189 990 ₽"),
    ("NVIDIA GeForce RTX 5090 Palit GameRock 32GB", "479 990 ₽"),
]

# Кнопки постоянного нижнего меню
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📈 Курсы валют (ЦБ РФ)"), KeyboardButton("💻 Цены на видеокарты")],
    ],
    resize_keyboard=True
)


# === Простой HTTP-сервер для Render Health Check и пингов ===
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot is running OK!")

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
        logger.info(f"Health check HTTP-сервер запущен на порту {port}")
    except Exception as e:
        logger.warning(f"Не удалось запустить health check сервер на порту {port}: {e}")


# === Фоновый пингер для предотвращения засыпания Render Free (Keep-Alive) ===
def self_ping_loop(url: str):
    logger.info(f"Фоновый Keep-Alive пингер активирован для: {url}")
    # Ждем 3 минуты после старта, затем пингуем каждые 9 минут (Render засыпает через 15 мин)
    time.sleep(180)
    while True:
        try:
            r = httpx.get(url, timeout=25.0)
            logger.info(f"Keep-Alive ping -> {url} (статус {r.status_code})")
        except Exception as e:
            logger.warning(f"Ошибка Keep-Alive ping: {e}")
        time.sleep(540)  # 9 минут


def start_keep_alive(url: str):
    if url:
        thread = threading.Thread(target=self_ping_loop, args=(url,), daemon=True)
        thread.start()


# === Функции для работы с кэшем на диске ===
def load_cached_gpu():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("items", []), data.get("timestamp", 0)
        except Exception:
            pass
    return [], 0


def save_cached_gpu(items):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": time.time(),
                "items": items
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Не удалось сохранить кэш цен: {e}")


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 <b>Привет! Я бот для отслеживания курсов валют и цен на GPU.</b>\n\n"
        "Нажимай удобные кнопки внизу экрана для быстрого получения данных 👇\n\n"
        "📈 <b>Курсы валют</b> — официальный курс Доллара, Юаня и Евро от ЦБ РФ\n"
        "💻 <b>Цены на видеокарты</b> — актуальные цены на популярные видеокарты"
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KEYBOARD
    )


# === Команда получения курсов валют ===
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
            reply_markup=MAIN_KEYBOARD
        )
    except Exception as e:
        logger.error(f"Ошибка при запросе курсов: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Ошибка получения курсов валют: {html.escape(str(e))}",
            reply_markup=MAIN_KEYBOARD
        )


# === Функция парсинга цен видеокарт (запускается не чаще 1 раза в сутки) ===
async def fetch_fresh_gpu_prices() -> list[tuple[str, str]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        url = "https://www.regard.ru/catalog/1013/videokarty"
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                results = []
                scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', resp.text, re.DOTALL)
                for s in scripts:
                    try:
                        data = json.loads(s)
                        if isinstance(data, dict) and "itemListElement" in data:
                            for item in data["itemListElement"]:
                                name = item.get("name")
                                price_val = item.get("price")
                                if name and price_val:
                                    clean_name = re.sub(r'^Видеокарта\s+', '', name)
                                    formatted_price = f"{int(price_val):,} ₽".replace(",", " ")
                                    results.append((clean_name, formatted_price))
                    except Exception:
                        continue

                if results:
                    save_cached_gpu(results)
                    return results
    except Exception as e:
        logger.warning(f"Ошибка фонового обновления цен: {e}")

    return []


# === Функция получения цен из кэша (или фоновое обновление) ===
async def get_gpu_prices():
    cached_items, last_time = load_cached_gpu()
    now = time.time()

    if cached_items and (now - last_time < CACHE_EXPIRATION):
        return cached_items, last_time

    fresh_items = await fetch_fresh_gpu_prices()
    if fresh_items:
        return fresh_items, now

    if cached_items:
        return cached_items, last_time
    return FALLBACK_GPU, now


# === Команда получения цен на видеокарты ===
async def gpu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        items, last_time = await get_gpu_prices()

        if last_time > 0:
            time_str = time.strftime("%d.%m.%Y %H:%M", time.localtime(last_time))
            header = f"🔥 <b>Цены на видеокарты (база от {time_str}):</b>\n\n"
        else:
            header = "🔥 <b>Актуальные цены на видеокарты:</b>\n\n"

        response = header
        for i, (title, item_price) in enumerate(items[:8], 1):
            clean_title = html.escape(title)
            clean_price = html.escape(item_price)
            response += f"{i}. <b>{clean_title}</b>\n   💰 Цена: <code>{clean_price}</code>\n\n"

        await update.message.reply_text(
            response,
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_KEYBOARD
        )
    except Exception as e:
        logger.error(f"Ошибка при получении цен: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Ошибка получения цен: {html.escape(str(e))}",
            reply_markup=MAIN_KEYBOARD
        )


# === Обработчик нажатий на текстовые кнопки меню ===
async def handle_text_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "Курсы валют" in text:
        await price(update, context)
    elif "видеокарты" in text or "GPU" in text:
        await gpu(update, context)
    else:
        await start(update, context)


# === Запуск бота ===
def main():
    if not os.path.exists(CACHE_FILE):
        save_cached_gpu(FALLBACK_GPU)

    start_health_check_server(PORT)
    start_keep_alive(SERVICE_URL)

    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("price", price))
    application.add_handler(CommandHandler("gpu", gpu))

    # Обработчик кнопок меню
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_button))

    print("\n" + "="*50)
    print("Бот успешно запущен и работает 24/7!")
    print("="*50 + "\n")

    application.run_polling(
        poll_interval=1.0,
        timeout=30,
        bootstrap_retries=-1
    )


if __name__ == "__main__":
    main()
