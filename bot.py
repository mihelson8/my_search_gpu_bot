import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
import time

TOKEN = '8934402151:AAG3LlLq_JuU8ZHk0LP0qy0hPdNZpTvQNfs'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я парсер цен на GPU. Напиши /gpu, чтобы узнать цены на видеокарты.")

async def gpu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Сканирую сайт DNS через облачный браузер... Это займёт 20-30 секунд.")
    
    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        # Подключение к облачному браузеру Browserless с твоим ключом
        driver = uc.Chrome(
            options=options,
            version_main=151,
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
            await update.message.reply_text("😔 Не удалось найти цены. Возможно, сайт изменил оформление.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

application = ApplicationBuilder().token(TOKEN).build()
application.add_handler(CommandHandler('start', start))
application.add_handler(CommandHandler('gpu', gpu))

if __name__ == '__main__':
    application.run_webhook(
        listen='0.0.0.0',
        port=8000,
        url_path='',
        webhook_url='https://my-gpu-bot.onrender.com',
        webhook_timeout=60
    )
