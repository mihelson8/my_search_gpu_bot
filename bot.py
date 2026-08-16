import os
import sys
import html
import re
import json
import asyncio
import logging
import xml.etree.ElementTree as ET

import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = "8914024807:AAFUXerMus2OEkbfUCt0H_II70ac1IbzH48"


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 <b>Привет! Я бот для отслеживания курсов валют и цен на GPU.</b>\n\n"
        "📈 <b>/price</b> — актуальный официальный курс Доллара, Юаня и Евро (ЦБ РФ)\n"
        "💻 <b>/gpu</b> — актуальные цены на популярные видеокарты"
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
        await update.message.reply_text(message_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Ошибка при запросе курсов: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка получения курсов валют: {html.escape(str(e))}")


# === Функция парсинга видеокарт (быстрая и стабильная) ===
async def fetch_gpu_prices() -> list[tuple[str, str]]:
    url = "https://www.regard.ru/catalog/1013/videokarty"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        html_content = response.text

    results = []
    # Извлекаем данные о товарах из официального каталога schema.org
    scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html_content, re.DOTALL)
    for s in scripts:
        try:
            data = json.loads(s)
            if isinstance(data, dict) and "itemListElement" in data:
                for item in data["itemListElement"]:
                    name = item.get("name")
                    price_val = item.get("price")
                    if name and price_val:
                        # Форматируем цену: например, 45 990 ₽
                        formatted_price = f"{int(price_val):,} ₽".replace(",", " ")
                        results.append((name, formatted_price))
        except Exception:
            continue

    return results


# === Команда /gpu ===
async def gpu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Запрашиваю свежие цены на видеокарты... Подожди 1-2 секунды.")
    try:
        items = await fetch_gpu_prices()

        if items:
            response = "🔥 <b>Актуальные цены на видеокарты:</b>\n\n"
            for i, (title, item_price) in enumerate(items[:8], 1):
                clean_title = html.escape(title)
                clean_price = html.escape(item_price)
                response += f"{i}. <b>{clean_title}</b>\n   💰 Цена: <code>{clean_price}</code>\n\n"

            await update.message.reply_text(response, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("😔 Не удалось получить список видеокарт в данный момент.")
    except Exception as e:
        logger.error(f"Ошибка при получении цен: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка получения цен: {html.escape(str(e))}")


# === Запуск бота ===
def main():
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

    print("\n" + "="*50)
    print("Бот успешно запущен и готов к работе!")
    print("Откройте Telegram и проверьте /price и /gpu")
    print("="*50 + "\n")

    application.run_polling(
        poll_interval=1.0,
        timeout=30,
        bootstrap_retries=-1
    )


if __name__ == "__main__":
    main()
