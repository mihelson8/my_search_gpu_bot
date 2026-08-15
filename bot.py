import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import undetected_chromedriver as uc
import time
import requests
import xml.etree.ElementTree as ET

TOKEN = '8934402151:AAG3LlLq_JuU8ZHk0LP0qy0hPdNZpTvQNfs'

# === Команда для курсов валют ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для курсов валют и цен на GPU.\n"
        "📈 Отправь /price для курса Доллара и Юаня.\n"
        "💻 Отправь /gpu для цен на видеокарты."
    )

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Запрашиваю курсы через API ЦБ... Подожди.")
    try:
        url = "https://www.cbr.ru/scripts/XML_daily.asp"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        response = requests.get(url, headers=headers)
        root = ET.fromstring(response.content)
        
        usd_price = "Не найден"
        cny_price = "Не найден"
        for valute in root.findall('Valute'):
            char_code = valute.find('CharCode').text
            value = valute.find('Value').text.replace(',', '.')
            if char_code == "USD":
                usd_price = value
            elif char_code == "CNY":
                cny_price = value
        
        await update.message.reply_text(
            f"🇺🇸 **Курс Доллара США:** {usd_price} руб.\n"
            f"🇨🇳 **Курс Китайского юаня:** {cny_price} руб.",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка курсов: {e}.")

# === Команда для парсинга видеокарт ===
async def gpu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Сканирую сайт DNS через облачный браузер... Это займёт 20-30 секунд.")
    try:
        # Подключаемся напрямую к Browserless (без поиска браузера на сервере)
        driver = uc.Chrome(
            browserless_url="wss://chrome.browserless.io?token=2V4mHaHXY9vr0ZG60e17e7d354904b69ee46bc5231ccb7704"
        )
        url = "https://www.dns-shop.ru/search/?q=видеокарта&category=17a89aab164077e2"
        driver.get(url)
        time.sleep(7)

        elements = driver.find_elements("css selector", ".product-buy__price")
        prices = [el.text.strip() for el in elements if el.text.strip()]
        driver.quit()

        if prices:
            response = "🔥 **Актуальные цены на видеокарты в DNS:**\n\n"
            for i, price in enumerate(prices[:10], 1):
                response += f"{i}. {price}\n"
            await update.message.reply_text(response, parse_mode='Markdown')
        else:
            await update.message.reply_text("😔 Не удалось найти цены.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка парсера: {e}")

# === Настройка и запуск ===
application = ApplicationBuilder().token(TOKEN).build()
application.add_handler(CommandHandler('start', start))
application.add_handler(CommandHandler('price', price))
application.add_handler(CommandHandler('gpu', gpu))

if __name__ == '__main__':
    application.run_webhook(
        listen='0.0.0.0',
        port=8000,
        url_path='',
        webhook_url='https://my-search-gpu-bot.onrender.com'
    )
