# Telegram Бот: Курсы валют и Цены на GPU

Telegram-бот на Python (`python-telegram-bot`), который:
- Отслеживает официальные курсы валют (USD, CNY, EUR) через API Центрального Банка РФ (`/price`).
- Парсит актуальные цены и названия видеокарт с сайта DNS через удаленный облачный браузер Browserless.io (`/gpu`).

---

## 🚀 Быстрый запуск

### 1. Получение токенов

1. **Telegram Bot Token:**
   - Перейдите в Telegram к [@BotFather](https://t.me/BotFather).
   - Отправьте `/newbot`, следуйте инструкциям и скопируйте полученный токен.
2. **Browserless Token:**
   - Зарегистрируйтесь на сайте [Browserless.io](https://cloud.browserless.io/).
   - Скопируйте ваш API Token из личного кабинета.

---

### 2. Локальный запуск на компьютере (Polling)

1. Клонируйте репозиторий и перейдите в папку проекта:
   ```bash
   git clone <url_репозитория>
   cd <папка_проекта>
   ```

2. Создайте и активируйте виртуальное окружение:
   ```bash
   # Linux / macOS:
   python3 -m venv venv
   source venv/bin/activate

   # Windows:
   python -m venv venv
   venv\Scripts\activate
   ```

3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

4. Создайте файл `.env` на основе примера:
   ```bash
   cp .env.example .env
   ```
   Укажите в `.env` ваши значения `BOT_TOKEN` и `BROWSERLESS_TOKEN`.

5. Запустите бота:
   ```bash
   python bot.py
   ```

---

### 3. Запуск в облаке (Render.com Webhook)

1. Загрузите код в ваш GitHub-репозиторий.
2. Зайдите на [Render.com](https://render.com/) и создайте **New Web Service**.
3. Подключите ваш репозиторий.
4. Укажите:
   - **Environment:** `Python 3` (или `Docker`)
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
5. В разделе **Environment Variables** добавьте:
   - `BOT_TOKEN`: ваш токен Telegram бота.
   - `BROWSERLESS_TOKEN`: ваш токен Browserless.
   - `WEBHOOK_URL`: публичный URL сервиса Render (например, `https://my-gpu-bot.onrender.com`).
6. Нажмите **Deploy Web Service**.
