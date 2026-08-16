import os
import sys
import html
import asyncio
import logging
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен вашего бота
TOKEN = os.getenv("BOT_TOKEN", "8914024807:AAFUXerMus2OEkbfUCt0H_II70ac1IbzH48")

# API токен Browserless.io
BROWSERLESS_TOKEN = os.getenv("BROWSERLESS_TOKEN", "2V4mHaHXY9vr0ZG60e17e7d354904b69ee46bc5231ccb7704")

# Настройки хостинга
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8000))


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 <b>Привет! Я бот для отслеживания курсов валют и цен на GPU.</b>\n\n"
        "📈 <b>/price</b> — актуальный официальный курс Доллара, Юаня и Евро (ЦБ РФ)\n"
        "💻 <b>/gpu</b> — актуальные цены на видеокарты в DNS"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)


# === Команда /price (Курсы валют через API ЦБ РФ) ===
async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Запрашиваю курсы через API ЦБ РФ... Подожди несколько секунд.")
    try:
        url = "https://www.cbr.ru/scripts/XML_daily.asp"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
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
        await update.message.reply_text(message_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка при запросе курсов: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка получения курсов валют: {html.escape(str(e))}")


# === Функция синхронного парсинга через Browserless.io ===
def parse_dns_gpu_sync(browserless_token: str) -> list[tuple[str, str]]:
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    command_executor = f"https://chrome.browserless.io/webdriver?token={browserless_token}"
    driver = webdriver.Remote(command_executor=command_executor, options=options)

    results = []
    try:
        url = "https://www.dns-shop.ru/search/?q=видеокарта&category=17a89aab164077e2"
        driver.set_page_load_timeout(30)
        driver.get(url)

        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".catalog-product, .catalog-item, .product-buy__price")))

        products = driver.find_elements(By.CSS_SELECTOR, ".catalog-product, .catalog-item")

        for item in products[:10]:
            try:
                title_elem = item.find_element(By.CSS_SELECTOR, ".catalog-product__name, a.ui-link")
                price_elem = item.find_element(By.CSS_SELECTOR, ".product-buy__price")

                title = title_elem.text.strip()
                price_val = price_elem.text.strip()

                if title and price_val:
                    results.append((title, price_val))
            except Exception:
                continue

    finally:
        driver.quit()

    return results


# === Команда /gpu ===
async def gpu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not BROWSERLESS_TOKEN:
        await update.message.reply_text(
            "⚠️ <b>Токен Browserless не задан!</b>",
            parse_mode=ParseMode.HTML
        )
        return

    await update.message.reply_text("🔍 Сканирую сайт DNS через облачный браузер... Это займёт 15-25 секунд.")
    try:
        items = await asyncio.to_thread(parse_dns_gpu_sync, BROWSERLESS_TOKEN)

        if items:
            response = "🔥 <b>Актуальные цены на видеокарты в DNS:</b>\n\n"
            for i, (title, item_price) in enumerate(items, 1):
                clean_title = html.escape(title)
                clean_price = html.escape(item_price)
                response += f"{i}. <b>{clean_title}</b>\n   💰 Цена: <code>{clean_price}</code>\n\n"

            await update.message.reply_text(response, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(
                "😔 Не удалось получить цены с сайта DNS (возможно, сайт временно включил капчу)."
            )
    except Exception as e:
        logger.error(f"Ошибка при парсинге DNS: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка парсера: {html.escape(str(e))}")


# === Точка входа в программу ===
def main():
    if not TOKEN:
        logger.error("Ошибка: Токен бота не задан!")
        sys.exit(1)

    # Увеличиваем таймауты подключения к Telegram API, чтобы избежать TimedOut
    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("price", price))
    application.add_handler(CommandHandler("gpu", gpu))

    if WEBHOOK_URL:
        clean_webhook_url = WEBHOOK_URL.rstrip("/")
        logger.info(f"Запуск в режиме Webhook на порту {PORT}, URL: {clean_webhook_url}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{clean_webhook_url}/{TOKEN}"
        )
    else:
        logger.info("Бот успешно запущен в режиме Polling! Слушаю команды...")
        application.run_polling(
            poll_interval=1.0,
            timeout=30,
            bootstrap_retries=-1
        )


if __name__ == "__main__":
    main()
