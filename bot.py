import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
import xml.etree.ElementTree as ET

TOKEN = '8934402151:AAG3LlLq_JuU8ZHk0LP0qy0hPdNZpTvQNfs'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я бот для курса Доллара и Юаня. Отправь /price!")

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
        await update.message.reply_text(f"❌ Ошибка: {e}.")

application = ApplicationBuilder().token(TOKEN).build()
application.add_handler(CommandHandler('start', start))
application.add_handler(CommandHandler('price', price))

if __name__ == '__main__':
    application.run_webhook(
        listen='0.0.0.0',
        port=8000,
        url_path='',
        webhook_url='https://my-search-gpu-bot.onrender.com'
    )