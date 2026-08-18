"""
WeChat Official Account Webhook Server with Full Voice & Text Translation Support.
Официальный сервер WeChat с поддержкой голосовых сообщений (Voice Recognition)
и голосовой озвучки перевода (Voice Reply / Speech Synthesis).
"""

import os
import io
import sys
import time
import hashlib
import asyncio
import logging
import threading
import xml.etree.ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import httpx
from pydub import AudioSegment
import speech_recognition as sr

from translator.models import TechTerm, Language
from translator.engine import TerminologyEngine, TechTranslator
from translator.pinyin_helper import get_pinyin, is_chinese_text, detect_language
from translator.voice_helper import generate_tts_audio, recognize_speech_from_ogg

logger = logging.getLogger(__name__)

# WeChat Verification Token и App Credentials
WECHAT_TOKEN = os.getenv("WECHAT_TOKEN", "my_wechat_translator_token_123")
WECHAT_APPID = os.getenv("WECHAT_APPID", "wx9f1912539effdbf3")
WECHAT_SECRET = os.getenv("WECHAT_SECRET", "ec507a7a06fee51bfdfca0f22ce2df8b")
PORT = int(os.getenv("PORT", 10000))

# Кэширование Access Token
_access_token_cache = {"token": "", "expires_at": 0}

# Инициализация движка словаря
engine = TerminologyEngine()
translator = TechTranslator(engine)


def get_wechat_access_token() -> str:
    """Получает и кэширует access_token от официального API WeChat."""
    now = time.time()
    if _access_token_cache["token"] and now < _access_token_cache["expires_at"] - 60:
        return _access_token_cache["token"]

    if not WECHAT_APPID or not WECHAT_SECRET:
        return ""

    try:
        url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={WECHAT_APPID}&secret={WECHAT_SECRET}"
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token")
                expires_in = data.get("expires_in", 7200)
                if token:
                    _access_token_cache["token"] = token
                    _access_token_cache["expires_at"] = now + expires_in
                    return token
    except Exception as e:
        logger.error(f"Failed to get WeChat access token: {e}")

    return ""


def download_wechat_voice_media(media_id: str) -> bytes:
    """Скачивает аудиофайл голосового сообщения пользователя по media_id из WeChat."""
    token = get_wechat_access_token()
    if not token or not media_id:
        return b""

    try:
        url = f"https://api.weixin.qq.com/cgi-bin/media/get?access_token={token}&media_id={media_id}"
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                return resp.content
    except Exception as e:
        logger.error(f"Failed to download voice media {media_id}: {e}")

    return b""


def upload_wechat_voice_media(audio_bytes: bytes, filename: str = "voice.mp3") -> str:
    """Загружает аудиофайл озвучки в WeChat временные медиа и возвращает media_id для голосового ответа."""
    token = get_wechat_access_token()
    if not token or not audio_bytes:
        return ""

    try:
        url = f"https://api.weixin.qq.com/cgi-bin/media/upload?access_token={token}&type=voice"
        files = {"media": (filename, audio_bytes, "audio/mpeg")}
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, files=files)
            if resp.status_code == 200:
                data = resp.json()
                media_id = data.get("media_id")
                if media_id:
                    return media_id
                else:
                    logger.warning(f"WeChat media upload error response: {data}")
    except Exception as e:
        logger.error(f"Failed to upload voice media to WeChat: {e}")

    return ""


def send_wechat_custom_message(to_user: str, msg_type: str, content: str = "", media_id: str = ""):
    """Отправка дополнительного сообщения через WeChat Customer Service API (активный ответ)."""
    token = get_wechat_access_token()
    if not token:
        return

    try:
        url = f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={token}"
        if msg_type == "voice" and media_id:
            payload = {
                "touser": to_user,
                "msgtype": "voice",
                "voice": {"media_id": media_id}
            }
        elif msg_type == "text" and content:
            payload = {
                "touser": to_user,
                "msgtype": "text",
                "text": {"content": content}
            }
        else:
            return

        with httpx.Client(timeout=8.0) as client:
            client.post(url, json=payload)
    except Exception as e:
        logger.error(f"Failed to send custom message to {to_user}: {e}")


def recognize_wechat_voice(audio_bytes: bytes) -> str:
    """Распознавание речи из голосового сообщения WeChat (AMR/Speex/MP3/WAV)."""
    if not audio_bytes:
        return ""

    recognizer = sr.Recognizer()

    try:
        # Конвертация любого аудиоформата в WAV через pydub
        audio_stream = io.BytesIO(audio_bytes)
        try:
            audio = AudioSegment.from_file(audio_stream)
        except Exception:
            audio_stream.seek(0)
            audio = AudioSegment.from_raw(audio_stream, sample_width=2, frame_rate=8000, channels=1)

        wav_stream = io.BytesIO()
        audio.export(wav_stream, format="wav")
        wav_stream.seek(0)

        with sr.AudioFile(wav_stream) as source:
            audio_data = recognizer.record(source)

        for lang_code in ["ru-RU", "zh-CN", "en-US", "zh-HK"]:
            try:
                text = recognizer.recognize_google(audio_data, language=lang_code)
                if text and len(text.strip()) > 0:
                    return text.strip()
            except sr.UnknownValueError:
                continue
            except Exception:
                continue

    except Exception as e:
        logger.error(f"WeChat voice recognition error: {e}", exc_info=True)

    return ""


def check_wechat_signature(signature: str, timestamp: str, nonce: str, token: str = WECHAT_TOKEN) -> bool:
    """Проверка подписи сервера WeChat по стандарту Tencent: SHA1(sort([token, timestamp, nonce]))."""
    if not signature or not timestamp or not nonce:
        return False
    tmp_list = sorted([token, timestamp, nonce])
    tmp_str = "".join(tmp_list)
    calc_hash = hashlib.sha1(tmp_str.encode("utf-8")).hexdigest()
    return calc_hash == signature


def build_text_reply_xml(to_user: str, from_user: str, content: str) -> str:
    """Генерация стандартного XML-ответа для текстового сообщения в WeChat."""
    create_time = int(time.time())
    return f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{create_time}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{content}]]></Content>
</xml>"""


def build_voice_reply_xml(to_user: str, from_user: str, media_id: str) -> str:
    """Генерация XML-ответа для отправки голосового аудиосообщения в WeChat."""
    create_time = int(time.time())
    return f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{create_time}</CreateTime>
<MsgType><![CDATA[voice]]></MsgType>
<Voice>
<MediaId><![CDATA[{media_id}]]></MediaId>
</Voice>
</xml>"""


def format_wechat_reply(output, user_query: str) -> str:
    """Форматирует карточку перевода под ограничения и интерфейс WeChat."""
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
            bua_ex = f"\n• 🔵 {ex.bua}" if ex.bua else ""
            reply += f"\n💡 Пример:\n• 🇷🇺 {ex.ru}\n• 🇨🇳 {ex.zh} ({ex.pinyin})\n• 🇺🇸 {ex.en}{bua_ex}"
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


def async_send_voice_followup(to_user: str, output, user_query: str):
    """
    В фоновом потоке синтезирует озвучку перевода и отправляет аудиосообщение в WeChat.
    """
    try:
        # Определяем, что озвучить
        text_to_speak = ""
        lang_to_speak = "zh"

        if output.direct_match:
            t = output.direct_match
            # Если запрос был на русском/английском — озвучиваем китайский
            if output.detected_lang == Language.ZH or is_chinese_text(user_query):
                text_to_speak = t.ru
                lang_to_speak = "ru"
            else:
                text_to_speak = t.zh
                lang_to_speak = "zh"
        else:
            if (output.detected_lang == Language.ZH or is_chinese_text(user_query)) and "ru" in output.online_translations:
                text_to_speak = output.online_translations["ru"]
                lang_to_speak = "ru"
            elif "zh" in output.online_translations:
                text_to_speak = output.online_translations["zh"]
                lang_to_speak = "zh"

        if text_to_speak:
            audio_io = generate_tts_audio(text_to_speak, lang=lang_to_speak)
            if audio_io:
                media_id = upload_wechat_voice_media(audio_io.getvalue(), filename=f"reply_{lang_to_speak}.mp3")
                if media_id:
                    send_wechat_custom_message(to_user=to_user, msg_type="voice", media_id=media_id)
    except Exception as e:
        logger.error(f"Error in async_send_voice_followup: {e}", exc_info=True)


class WeChatRequestHandler(BaseHTTPRequestHandler):
    """HTTP обработчик для WeChat Webhook и Health check."""

    def do_GET(self):
        """1. Верификация сервера WeChat. 2. Health Check для Render."""
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
        """Обработка входящих текстовых и голосовых сообщений из WeChat."""
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
            user_msg = ""

            # 1. Текстовое сообщение
            if msg_type == "text":
                user_msg = root.find("Content").text.strip()

            # 2. Голосовое сообщение (Voice Message)
            elif msg_type == "voice":
                # Сначала пробуем встроенное распознавание WeChat (если включено в аккаунте)
                recognition_elem = root.find("Recognition")
                if recognition_elem is not None and recognition_elem.text and recognition_elem.text.strip():
                    user_msg = recognition_elem.text.strip()
                else:
                    # Скачиваем аудио по MediaId и распознаем через наш движок
                    media_id_elem = root.find("MediaId")
                    if media_id_elem is not None and media_id_elem.text:
                        media_id = media_id_elem.text
                        audio_data = download_wechat_voice_media(media_id)
                        if audio_data:
                            user_msg = recognize_wechat_voice(audio_data)

            elif msg_type == "event":
                event_type = root.find("Event").text
                if event_type == "subscribe":
                    reply_content = (
                        "👋 欢迎使用多语言翻译助手！\n"
                        "Добро пожаловать в Переводчик!\n\n"
                        "✨ Возможности:\n"
                        "• ✍️ Текстовый перевод\n"
                        "• 🎙 Голосовой ввод (отправляйте голосовые сообщения!)\n"
                        "• 🔊 Голосовая озвучка перевода\n\n"
                        "Поддерживаемые языки:\n"
                        "🇨🇳 中文 (普通话 & 白话/粤语)\n"
                        "🇷🇺 Русский\n"
                        "🇺🇸 American English\n"
                        "🔵 Буряад хэлэн (Бурятский)\n\n"
                        "Отправьте любое слово текстом или голосом!"
                    )

            if user_msg:
                # Получаем перевод через движок
                output = asyncio.run(translator.translate(user_msg))

                # Если пользователь отправил голосовое сообщение — сразу отвечаем голосовым переводом!
                if msg_type == "voice":
                    text_to_speak = ""
                    lang_to_speak = "zh"

                    if output.direct_match:
                        t = output.direct_match
                        if output.detected_lang == Language.ZH or is_chinese_text(user_msg):
                            text_to_speak = t.ru
                            lang_to_speak = "ru"
                        else:
                            text_to_speak = t.zh
                            lang_to_speak = "zh"
                    else:
                        if (output.detected_lang == Language.ZH or is_chinese_text(user_msg)) and "ru" in output.online_translations:
                            text_to_speak = output.online_translations["ru"]
                            lang_to_speak = "ru"
                        elif "zh" in output.online_translations:
                            text_to_speak = output.online_translations["zh"]
                            lang_to_speak = "zh"

                    media_id = ""
                    if text_to_speak:
                        audio_io = generate_tts_audio(text_to_speak, lang=lang_to_speak)
                        if audio_io:
                            media_id = upload_wechat_voice_media(audio_io.getvalue(), filename=f"reply_{lang_to_speak}.mp3")

                    # Если аудио успешно создано и загружено в WeChat — сразу возвращаем голосовой ответ (XML voice reply)
                    if media_id:
                        voice_xml = build_voice_reply_xml(from_user, to_user, media_id)
                        self.send_response(200)
                        self.send_header("Content-type", "application/xml; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(voice_xml.encode("utf-8"))

                        # А текстовую карточку с пиньинем отправляем параллельно следом
                        reply_content = format_wechat_reply(output, user_msg)
                        threading.Thread(
                            target=send_wechat_custom_message,
                            args=(from_user, "text", reply_content, ""),
                            daemon=True
                        ).start()
                        return

                # Для текстового сообщения возвращаем текстовый перевод и фоном озвучку
                reply_content = format_wechat_reply(output, user_msg)
                threading.Thread(
                    target=async_send_voice_followup,
                    args=(from_user, output, user_msg),
                    daemon=True
                ).start()

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
    print(f"📱 AppID: {WECHAT_APPID}", flush=True)
    print("=" * 60, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_wechat_server()
