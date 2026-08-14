import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
import xml.etree.ElementTree as ET

# ==========================================================
# ВСТАВЬТЕ СЮДА ВАШ НОВЫЙ ТОКЕН (в кавычках)
TOKEN = '8934402151:AAG3LlLq_JuU8ZHk0LP0qy0hPdNZpTvQNfs'
# ==========================================================

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для поиска курса Доллара и Юаня.\n"
        "Напиши команду /price, чтобы узнать актуальные курсы ЦБ РФ."
    )

# Команда /price с поиском по валютным кодам (USD, CNY)
async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Запрашиваю курсы через API ЦБ... Подожди пару секунд.")

    try:
        # Ссылка на официальное API Центробанка
        url = "https://www.cbr.ru/scripts/XML_daily.asp"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        response = requests.get(url, headers=headers)
        root = ET.fromstring(response.content)
        
        usd_price = "Не найден"
        cny_price = "Не найден"
        
        # Перебираем все валюты из XML ответа
        for valute in root.findall('Valute'):
            # Сравниваем коды валют. Это надежнее, чем названия!
            char_code = valute.find('CharCode').text 
            value = valute.find('Value').text.replace(',', '.')
            
            if char_code == "USD":
                usd_price = value
            elif char_code == "CNY":
                cny_price = value
        
        # Отправляем результат в Telegram
        await update.message.reply_text(
            f"🇺🇸 **Курс Доллара США:** {usd_price} руб.\n"
            f"🇨🇳 **Курс Китайского юаня:** {cny_price} руб.",
            parse_mode='Markdown'
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при запросе: {e}. Проверьте интернет.")

# Запуск бота (с исправлением ошибки Windows Overlapped)
if __name__ == '__main__':
    if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('price', price))
    print("✅ Бот запущен! Обновленный поиск по кодам USD и CNY. Напиши /price в Telegram.")
    application.run_polling()
