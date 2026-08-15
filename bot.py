import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import undetected_chromedriver as uc
import time

# ==========================================
# ВСТАВЬ СЮДА СВОЙ НОВЫЙ ТОКЕН (в кавычках)
TOKEN = '8934402151:AAG3LlLq_JuU8ZHk0LP0qy0hPdNZpTvQNfs'
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я парсер цен на GPU. Напиши /price, чтобы узнать цены на видеокарты.")

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Сканирую сайт DNS... Это займёт 20-30 секунд. Подожди, пожалуйста.")
    try:
        # Настройки для браузера (безголовый режим для сервера)
        options = uc.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        # Исправление ошибки Binary Location. Указываем путь к браузеру.
        driver = uc.Chrome(
            options=options, 
            version_main=151, 
            driver_executable_path='/usr/bin/google-chrome'
        )

        url = "https://www.dns-shop.ru/search/?q=видеокарта&category=17a89aab164077e2"
        driver.get(url)
        time.sleep(5)

        # Ищем цены на карточках товаров
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

# Настройка и запуск бота через Webhook (для Render)
application = ApplicationBuilder().token(TOKEN).build()
application.add_handler(CommandHandler('start', start))
application.add_handler(CommandHandler('price', price))

if __name__ == '__main__':
    application.run_webhook(
        listen='0.0.0.0',
        port=8000,
        webhook_url='https://my_search_gpu_bot.onrender.com' # Убедись, что этот адрес совпадает с твоим на Render
    )
