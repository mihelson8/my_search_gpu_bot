"""
WeChat Official Account Webhook Server for Technical Terms & Daily Translator.
Официальный веб-сервер / Вебхук для WeChat (微信公众号).
100% официальный API Tencent, безопасность от блокировок.
"""

import os
import sys
import time
import hashlib
import asyncio
import logging
import xml.etree.ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from translator.models import TechTerm, Language
from translator.engine import TerminologyEngine, TechTranslator
from translator.pinyin_helper import get_pinyin, is_chinese_text

logger = logging.getLogger(__name__)

# WeChat Verification Token (задается в панели WeChat и здесь)
WECHAT_TOKEN = os.getenv("WECHAT_TOKEN", "my_wechat_translator_token_123")
PORT = int(os.getenv("PORT", 10000))

# Инициализация движка словаря
engine = TerminologyEngine()
translator = TechTranslator(engine)


def check_wechat_signature(signature: str, timestamp: str, nonce: str, token: str = WECHAT_TOKEN) -> bool:
    """
    Проверка подписи WeChat сервера по стандарту Tencent:
    SHA1(sort([token, timestamp, nonce])) == signature
    """
    if not signature or not timestamp or not nonce:
        return False
    tmp_list = sorted([token, timestamp, nonce])
    tmp_str = "".join(tmp_list)
    calc_hash = hashlib.sha1(tmp_str.encode("utf-8")).hexdigest()
    return calc_hash == signature


def build_text_reply_xml(to_user: str, from_user: str, content: str) -> str:
    """Генерация стандартного XML-ответа для WeChat."""
    create_time = int(time.time())
    xml_template = f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{create_time}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{content}]]></Content>
</xml>"""
    return xml_template


def format_wechat_reply(output, user_query: str) -> str:
    """Форматирует перевод под ограничения и интерфейс WeChat."""
    if output.direct_match:
        t = output.direct_match
        trad_part = f" [{t.zh_trad}]" if t.zh_trad else ""
        bua_part = f"\n🔵 Буряад: {t.bua}" if t.bua else ""

        reply = (
            f"📘 {t.ru} ↔ {t.zh}\n"
            f"━━━━━━━━━━━━━━\n"
            f"🇨🇳 Путунхуа: {t.zh}{trad_part}\n"
            f"🗣 Pinyin: {t.pinyin}\n"
            f"🇭🇰 Кантонский: {t.zh}\n"
            f"🇺🇸 English: {t.en}\n"
            f"🇷🇺 Русский: {t.ru}{bua_part}\n"
        )
        if t.definition_ru:
            reply += f"\n📖 Определение: {t.definition_ru}\n"
        if t.examples:
            ex = t.examples[0]
            reply += f"\n💡 Пример:\n• 🇷🇺 {ex.ru}\n• 🇨🇳 {ex.zh} ({ex.pinyin})\n• 🇺🇸 {ex.en}"
        return reply

    # Онлайн перевод произвольной фразы
    zh_val = output.online_translations.get("zh", "")
    ru_val = output.online_translations.get("ru", "")
    en_val = output.online_translations.get("en", "")
    bua_val = output.online_translations.get("bua", "")

    reply = f"🌐 Перевод «{user_query}»:\n━━━━━━━━━━━━━━\n"
    if ru_val and output.detected_lang != Language.RU:
        reply += f"🇷🇺 Русский: {ru_val}\n"
    if zh_val:
        py = get_pinyin(zh_val)
        reply += f"🇨🇳 Путунхуа: {zh_val}\n"
        if py:
            reply += f"🗣 Pinyin: {py}\n"
        reply += f"🇭🇰 Кантонский: {zh_val}\n"
    elif output.detected_lang == Language.ZH or is_chinese_text(user_query):
        py = get_pinyin(user_query)
        reply += f"🇨🇳 Путунхуа: {user_query}\n"
        if py:
            reply += f"🗣 Pinyin: {py}\n"
        reply += f"🇭🇰 Кантонский: {user_query}\n"

    if en_val and output.detected_lang != Language.EN:
        reply += f"🇺🇸 English: {en_val}\n"
    if bua_val and output.detected_lang != Language.BUA:
        reply += f"🔵 Буряад: {bua_val}\n"

    return reply


class WeChatRequestHandler(BaseHTTPRequestHandler):
    """HTTP обработчик для WeChat Webhook и Health check."""

    def do_GET(self):
        """
        1. Верификация сервера WeChat (эхо-ответ echostr при валидной подписи).
        2. Health Check для Render.
        """
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        signature = params.get("signature", [""])[0]
        timestamp = params.get("timestamp", [""])[0]
        nonce = params.get("nonce", [""])[0]
        echostr = params.get("echostr", [""])[0]

        # Если это запрос верификации от WeChat
        if signature and timestamp and nonce and echostr:
            if check_wechat_signature(signature, timestamp, nonce, WECHAT_TOKEN):
                logger.info("WeChat webhook verification successful!")
                self.send_response(200)
                self.send_header("Content-type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(echostr.encode("utf-8"))
                return
            else:
                logger.warning("WeChat webhook verification failed (bad signature).")
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Invalid signature")
                return

        # Иначе обычный Health Check для Render
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"WeChat Translator Server is running OK!")

    def do_POST(self):
        """Обработка входящих сообщений пользователей из WeChat."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        signature = params.get("signature", [""])[0]
        timestamp = params.get("timestamp", [""])[0]
        nonce = params.get("nonce", [""])[0]

        # Валидация подписи запроса
        if not check_wechat_signature(signature, timestamp, nonce, WECHAT_TOKEN):
            self.send_response(403)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            root = ET.fromstring(post_data)
            to_user = root.find("ToUserName").text
            from_user = root.find("FromUserName").text
            msg_type = root.find("MsgType").text

            reply_content = ""

            if msg_type == "text":
                user_msg = root.find("Content").text.strip()
                # Получаем перевод через движок
                output = asyncio.run(translator.translate(user_msg))
                reply_content = format_wechat_reply(output, user_msg)

            elif msg_type == "event":
                event_type = root.find("Event").text
                if event_type == "subscribe":
                    reply_content = (
                        "👋 欢迎使用多语言翻译助手！\n"
                        "Добро пожаловать в Переводчик!\n\n"
                        "Поддерживаемые языки:\n"
                        "🇨🇳 中文 (普通话 & 白话)\n"
                        "🇷🇺 Русский\n"
                        "🇺🇸 American English\n"
                        "🔵 Буряад хэлэн (Бурятский)\n\n"
                        "✍️ Отправьте любое слово или фразу для мгновенного перевода!"
                    )

            if reply_content:
                reply_xml = build_text_reply_xml(from_user, to_user, reply_content)
                self.send_response(200)
                self.send_header("Content-type", "application/xml; charset=utf-8")
                self.end_headers()
                self.wfile.write(reply_xml.encode("utf-8"))
            else:
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(b"success")

        except Exception as e:
            logger.error(f"Error handling WeChat POST: {e}", exc_info=True)
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"success")

    def log_message(self, format, *args):
        pass


def run_wechat_server():
    class ReusableHTTPServer(HTTPServer):
        allow_reuse_address = True

    server = ReusableHTTPServer(("0.0.0.0", PORT), WeChatRequestHandler)
    print("=" * 60, flush=True)
    print(f"🇨🇳 Сервер WeChat переводчика успешно запущен на порту {PORT}!", flush=True)
    print(f"🔑 Токен WeChat: {WECHAT_TOKEN}", flush=True)
    print("=" * 60, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_wechat_server()
