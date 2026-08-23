"""
MAX Messenger Bot: Technical Terms Translator (Chinese - English - Russian).
Чат-бот для российского мессенджера MAX (platform-api2.max.ru).

Официальный Bot API: https://dev.max.ru/docs-api
Режимы: Webhook (production) и Long Polling (локальная разработка).
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from translator.engine import TerminologyEngine, TechTranslator
from translator.models import Language, TechTerm
from translator.pinyin_helper import get_pinyin, is_chinese_text

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Конфигурация ---
MAX_API_BASE = os.getenv("MAX_API_BASE", "https://platform-api2.max.ru").rstrip("/")
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "").strip()
MAX_WEBHOOK_SECRET = os.getenv("MAX_WEBHOOK_SECRET", "").strip()
MAX_WEBHOOK_URL = os.getenv("MAX_WEBHOOK_URL", "").strip()
MAX_MODE = os.getenv("MAX_MODE", "auto").strip().lower()  # auto | webhook | polling
PORT = int(os.getenv("PORT", "10000"))

engine = TerminologyEngine()
translator = TechTranslator(engine)

# Кэш последних переводов по user_id для callback-озвучки текста
_user_last: Dict[int, Dict[str, Any]] = {}

WELCOME_TEXT = (
    "Добро пожаловать в Переводчик языков и терминов!\n"
    "🇷🇺 Русский | 🇨🇳 Путунхуа & Байхуа | 🇺🇸 American English | 🔵 Буряад хэлэн\n\n"
    "Отправьте слово или фразу текстом — бот переведёт на русский, китайский, "
    "английский и бурятский, покажет пиньинь и карточку из словаря IT/повседневных терминов.\n\n"
    "Команды:\n"
    "/start — приветствие\n"
    "/help — справка\n"
    "/random — случайный термин\n"
    "/categories — категории словаря\n"
    "/quiz — викторина\n\n"
    "Пример: спасибо, 多少钱, deep learning, Мэндээ"
)

HELP_TEXT = (
    "Справка по боту MAX:\n\n"
    "• Напишите любое слово/фразу на RU / EN / ZH / BUA\n"
    "• Поиск по пиньиню: shendu xuexi\n"
    "• /random — случайная карточка\n"
    "• /categories — разделы словаря\n"
    "• /quiz — мини-викторина\n\n"
    "Документация API: https://dev.max.ru/docs-api"
)


class MaxApiError(Exception):
    """Ошибка ответа MAX Bot API."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"MAX API {status_code}: {body[:300]}")


class MaxApiClient:
    """Минимальный клиент официального MAX Bot API (platform-api2.max.ru)."""

    def __init__(self, token: str, base_url: str = MAX_API_BASE, timeout: float = 60.0):
        if not token:
            raise ValueError("MAX_BOT_TOKEN is required")
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_body,
            )
        if resp.status_code >= 400:
            raise MaxApiError(resp.status_code, resp.text)
        if not resp.content:
            return {}
        data = resp.json()
        return data if isinstance(data, dict) else {"data": data}

    def get_me(self) -> Dict[str, Any]:
        return self.request("GET", "/me")

    def send_message(
        self,
        text: str,
        *,
        chat_id: Optional[int] = None,
        user_id: Optional[int] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        fmt: Optional[str] = "html",
        notify: bool = True,
    ) -> Dict[str, Any]:
        if chat_id is None and user_id is None:
            raise ValueError("chat_id or user_id is required")
        params: Dict[str, Any] = {}
        if chat_id is not None:
            params["chat_id"] = chat_id
        if user_id is not None:
            params["user_id"] = user_id
        body: Dict[str, Any] = {
            "text": text[:4000],
            "notify": notify,
        }
        if fmt:
            body["format"] = fmt
        if attachments is not None:
            body["attachments"] = attachments
        return self.request("POST", "/messages", params=params, json_body=body)

    def get_updates(
        self,
        *,
        marker: Optional[int] = None,
        limit: int = 100,
        timeout: int = 30,
        types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "timeout": timeout}
        if marker is not None:
            params["marker"] = marker
        if types:
            params["types"] = ",".join(types)
        return self.request("GET", "/updates", params=params)

    def subscribe_webhook(
        self,
        url: str,
        *,
        update_types: Optional[List[str]] = None,
        secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"url": url}
        if update_types:
            body["update_types"] = update_types
        if secret:
            body["secret"] = secret
        return self.request("POST", "/subscriptions", json_body=body)

    def list_subscriptions(self) -> Dict[str, Any]:
        return self.request("GET", "/subscriptions")


def inline_keyboard(rows: List[List[Dict[str, str]]]) -> List[Dict[str, Any]]:
    """Собирает attachment inline_keyboard для POST /messages."""
    return [
        {
            "type": "inline_keyboard",
            "payload": {"buttons": rows},
        }
    ]


def main_menu_keyboard() -> List[Dict[str, Any]]:
    return inline_keyboard(
        [
            [
                {"type": "callback", "text": "🎲 Случайная", "payload": "cmd:random"},
                {"type": "callback", "text": "📚 Категории", "payload": "cmd:categories"},
            ],
            [
                {"type": "callback", "text": "🧠 Викторина", "payload": "cmd:quiz"},
                {"type": "callback", "text": "❓ Справка", "payload": "cmd:help"},
            ],
        ]
    )


def term_keyboard(term: TechTerm) -> List[Dict[str, Any]]:
    rows: List[List[Dict[str, str]]] = [
        [
            {"type": "callback", "text": "🎲 Ещё термин", "payload": "cmd:random"},
            {"type": "callback", "text": "📚 Категории", "payload": "cmd:categories"},
        ]
    ]
    if term.related_terms:
        rel_row: List[Dict[str, str]] = []
        for rel_id in term.related_terms[:2]:
            rel = engine.get_term_by_id(rel_id)
            if rel:
                rel_row.append(
                    {
                        "type": "callback",
                        "text": f"🔗 {rel.en[:24]}",
                        "payload": f"show_term:{rel.id}",
                    }
                )
        if rel_row:
            rows.append(rel_row)
    return inline_keyboard(rows)


def extract_text_from_update(update: Dict[str, Any]) -> str:
    message = update.get("message") or {}
    body = message.get("body") or {}
    return (body.get("text") or "").strip()


def extract_targets(update: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    """
    Возвращает (chat_id, user_id) для ответа.
    В личном диалоге chat_id у recipient может отсутствовать — отвечаем по user_id.
    """
    update_type = update.get("update_type")
    if update_type == "bot_started":
        return update.get("chat_id"), (update.get("user") or {}).get("user_id")

    if update_type == "message_callback":
        callback = update.get("callback") or {}
        message = callback.get("message") or update.get("message") or {}
        recipient = message.get("recipient") or {}
        sender = callback.get("user") or callback.get("sender") or {}
        chat_id = recipient.get("chat_id") or update.get("chat_id")
        user_id = sender.get("user_id")
        return chat_id, user_id

    message = update.get("message") or {}
    recipient = message.get("recipient") or {}
    sender = message.get("sender") or {}
    chat_id = recipient.get("chat_id")
    user_id = sender.get("user_id") or recipient.get("user_id")
    chat_type = recipient.get("chat_type")
    # В dialog надёжнее слать по user_id
    if chat_type == "dialog" and user_id is not None:
        return None, user_id
    return chat_id, user_id


def format_term_html(term: TechTerm) -> str:
    trad = f" [{html.escape(term.zh_trad)}]" if term.zh_trad else ""
    bua = f"\n🔵 <b>Буряад:</b> <code>{html.escape(term.bua)}</code>" if term.bua else ""
    text = (
        f"📘 <b>{html.escape(term.ru)}</b> ↔ <b>{html.escape(term.zh)}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🇨🇳 <b>Путунхуа:</b> <code>{html.escape(term.zh)}</code>{trad}\n"
        f"🗣 <i>Pinyin:</i> <code>{html.escape(term.pinyin)}</code>\n"
        f"🇭🇰 <b>Кантонский:</b> <code>{html.escape(term.zh)}</code>\n"
        f"🇺🇸 <b>English:</b> <code>{html.escape(term.en)}</code>\n"
        f"🇷🇺 <b>Русский:</b> <code>{html.escape(term.ru)}</code>{bua}\n"
    )
    if term.definition_ru:
        text += f"\n📖 {html.escape(term.definition_ru)}\n"
    if term.examples:
        ex = term.examples[0]
        bua_ex = f"\n• 🔵 {html.escape(ex.bua)}" if ex.bua else ""
        text += (
            f"\n💡 <b>Пример:</b>\n"
            f"• 🇷🇺 {html.escape(ex.ru)}\n"
            f"• 🇨🇳 {html.escape(ex.zh)} (<i>{html.escape(ex.pinyin)}</i>)\n"
            f"• 🇺🇸 {html.escape(ex.en)}{bua_ex}"
        )
    return text


def format_online_html(output, user_query: str) -> str:
    response = (
        f"🌐 <b>Перевод «<code>{html.escape(user_query)}</code>»:</b>\n"
        f"<i>Язык: {html.escape(output.detected_lang.display_name_ru)}</i>\n"
        f"━━━━━━━━━━━━━━━━\n"
    )
    if output.detected_lang != Language.RU:
        ru_val = output.online_translations.get("ru", "")
        if ru_val:
            response += f"🇷🇺 <b>Русский:</b> <code>{html.escape(ru_val)}</code>\n"
    zh_val = output.online_translations.get("zh", "")
    if zh_val:
        py = get_pinyin(zh_val)
        response += f"🇨🇳 <b>Путунхуа:</b> <code>{html.escape(zh_val)}</code>\n"
        if py:
            response += f"🗣 <i>Pinyin:</i> <code>{html.escape(py)}</code>\n"
        response += f"🇭🇰 <b>Кантонский:</b> <code>{html.escape(zh_val)}</code>\n"
    elif output.detected_lang == Language.ZH or is_chinese_text(user_query):
        py = get_pinyin(user_query)
        response += f"🇨🇳 <b>Путунхуа:</b> <code>{html.escape(user_query)}</code>\n"
        if py:
            response += f"🗣 <i>Pinyin:</i> <code>{html.escape(py)}</code>\n"
        response += f"🇭🇰 <b>Кантонский:</b> <code>{html.escape(user_query)}</code>\n"
    if output.detected_lang != Language.EN:
        en_val = output.online_translations.get("en", "")
        if en_val:
            response += f"🇺🇸 <b>American English:</b> <code>{html.escape(en_val)}</code>\n"
    bua_val = output.online_translations.get("bua", "")
    if bua_val and output.detected_lang != Language.BUA:
        response += f"🔵 <b>Бурятский:</b> <code>{html.escape(bua_val)}</code>\n"
    return response


def format_search_html(user_text: str, results) -> Tuple[str, List[Dict[str, Any]]]:
    text = f"🔍 <b>Результаты по «<code>{html.escape(user_text)}</code>»:</b>\n\n"
    buttons: List[List[Dict[str, str]]] = []
    for i, res in enumerate(results[:5], 1):
        t = res.term
        pct = int(res.score * 100)
        bua_part = f" | 🔵 {html.escape(t.bua)}" if t.bua else ""
        text += (
            f"{i}. <b>{html.escape(t.en)}</b> ↔ <b>{html.escape(t.zh)}</b> "
            f"(<i>{html.escape(t.pinyin)}</i>)\n"
            f"   🇷🇺 {html.escape(t.ru)}{bua_part}\n\n"
        )
        buttons.append(
            [
                {
                    "type": "callback",
                    "text": f"📖 {t.en[:28]} ({pct}%)",
                    "payload": f"show_term:{t.id}",
                }
            ]
        )
    return text, inline_keyboard(buttons)


async def build_reply_for_text(user_text: str, user_id: Optional[int] = None) -> Tuple[str, List[Dict[str, Any]]]:
    """Строит текст ответа и клавиатуру для пользовательского сообщения."""
    lowered = user_text.strip()
    if not lowered:
        return "Отправьте текст для перевода.", main_menu_keyboard()

    if lowered in ("/start", "start", "старт"):
        return WELCOME_TEXT, main_menu_keyboard()
    if lowered in ("/help", "help", "помощь", "❓ Справка"):
        return HELP_TEXT, main_menu_keyboard()
    if lowered in ("/random", "🎲 Случайная", "случайный", "random"):
        terms = engine.get_random_terms(1)
        if not terms:
            return "В базе пока нет терминов.", main_menu_keyboard()
        return format_term_html(terms[0]), term_keyboard(terms[0])
    if lowered in ("/categories", "📚 Категории", "категории"):
        cats = engine.get_all_categories()
        lines = ["📚 <b>Категории:</b>\n"]
        buttons: List[List[Dict[str, str]]] = []
        for cat in cats[:20]:
            count = len(engine.get_terms_by_category(cat.id))
            lines.append(f"{cat.icon} {html.escape(cat.name_ru)} ({count})")
            buttons.append(
                [
                    {
                        "type": "callback",
                        "text": f"{cat.icon} {cat.name_ru[:30]}",
                        "payload": f"cat_terms:{cat.id}",
                    }
                ]
            )
        return "\n".join(lines), inline_keyboard(buttons)
    if lowered in ("/quiz", "🧠 Викторина", "викторина"):
        terms = engine.get_random_terms(4)
        if len(terms) < 4:
            return "Недостаточно терминов для викторины.", main_menu_keyboard()
        target = terms[0]
        options = terms[:]
        import random as _random

        _random.shuffle(options)
        correct_idx = options.index(target)
        text = (
            "🧠 <b>Викторина!</b>\n\n"
            f"Что означает:\n🇨🇳 <b><code>{html.escape(target.zh)}</code></b> "
            f"(<i>{html.escape(target.pinyin)}</i>)?\n"
        )
        buttons = []
        for i, opt in enumerate(options):
            buttons.append(
                [
                    {
                        "type": "callback",
                        "text": f"{i + 1}. {opt.en[:40]}",
                        "payload": f"quiz_ans:{i}:{correct_idx}:{target.id}",
                    }
                ]
            )
        return text, inline_keyboard(buttons)

    output = await translator.translate(lowered)
    if user_id is not None:
        _user_last[user_id] = {
            "translations": output.online_translations,
            "query": lowered,
            "detected": output.detected_lang.value,
        }

    if output.direct_match:
        return format_term_html(output.direct_match), term_keyboard(output.direct_match)
    if output.search_results:
        return format_search_html(lowered, output.search_results)
    return format_online_html(output, lowered), main_menu_keyboard()


async def handle_callback_payload(payload: str, user_id: Optional[int]) -> Tuple[str, List[Dict[str, Any]]]:
    if payload.startswith("cmd:"):
        cmd = payload.split(":", 1)[1]
        mapping = {
            "random": "/random",
            "categories": "/categories",
            "quiz": "/quiz",
            "help": "/help",
        }
        return await build_reply_for_text(mapping.get(cmd, "/help"), user_id)

    if payload.startswith("show_term:"):
        term_id = payload.split(":", 1)[1]
        term = engine.get_term_by_id(term_id)
        if not term:
            return "Термин не найден.", main_menu_keyboard()
        return format_term_html(term), term_keyboard(term)

    if payload.startswith("cat_terms:"):
        cat_id = payload.split(":", 1)[1]
        terms = engine.get_terms_by_category(cat_id)[:8]
        if not terms:
            return "В этой категории пока нет терминов.", main_menu_keyboard()
        lines = [f"📚 <b>Термины категории</b> <code>{html.escape(cat_id)}</code>:\n"]
        buttons: List[List[Dict[str, str]]] = []
        for t in terms:
            lines.append(f"• {html.escape(t.en)} — {html.escape(t.ru)} / {html.escape(t.zh)}")
            buttons.append(
                [{"type": "callback", "text": f"📖 {t.en[:28]}", "payload": f"show_term:{t.id}"}]
            )
        buttons.append([{"type": "callback", "text": "⬅️ Категории", "payload": "cmd:categories"}])
        return "\n".join(lines), inline_keyboard(buttons)

    if payload.startswith("quiz_ans:"):
        parts = payload.split(":")
        if len(parts) != 4:
            return "Некорректный ответ викторины.", main_menu_keyboard()
        _, chosen_s, correct_s, term_id = parts
        try:
            chosen = int(chosen_s)
            correct = int(correct_s)
        except ValueError:
            return "Некорректный ответ викторины.", main_menu_keyboard()
        term = engine.get_term_by_id(term_id)
        if chosen == correct:
            msg = "✅ Верно!"
        else:
            msg = "❌ Неверно."
        if term:
            msg += f"\n\nПравильно: <b>{html.escape(term.en)}</b> — {html.escape(term.ru)}"
            return msg, term_keyboard(term)
        return msg, main_menu_keyboard()

    return "Неизвестная команда.", main_menu_keyboard()


async def process_update(client: MaxApiClient, update: Dict[str, Any]) -> None:
    update_type = update.get("update_type")
    chat_id, user_id = extract_targets(update)

    if update_type == "bot_started":
        text, kb = WELCOME_TEXT, main_menu_keyboard()
        client.send_message(text, chat_id=chat_id, user_id=user_id, attachments=kb)
        return

    if update_type == "message_callback":
        callback = update.get("callback") or {}
        payload = callback.get("payload") or ""
        text, kb = await handle_callback_payload(payload, user_id)
        client.send_message(text, chat_id=chat_id, user_id=user_id, attachments=kb)
        return

    if update_type != "message_created":
        logger.debug("Skip update_type=%s", update_type)
        return

    sender = (update.get("message") or {}).get("sender") or {}
    if sender.get("is_bot"):
        return

    user_text = extract_text_from_update(update)
    if not user_text:
        return

    text, kb = await build_reply_for_text(user_text, user_id)
    client.send_message(text, chat_id=chat_id, user_id=user_id, attachments=kb)


def verify_webhook_secret(headers: Dict[str, str]) -> bool:
    if not MAX_WEBHOOK_SECRET:
        return True
    incoming = headers.get("X-Max-Bot-Api-Secret") or headers.get("x-max-bot-api-secret") or ""
    return incoming == MAX_WEBHOOK_SECRET


def make_webhook_handler(client: MaxApiClient):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            logger.info("HTTP %s - %s", self.address_string(), fmt % args)

        def _send(self, code: int, body: bytes = b"ok", content_type: str = "text/plain") -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/health", "/healthz"):
                payload = json.dumps({"status": "ok", "service": "max-bot"}).encode()
                self._send(200, payload, "application/json")
                return
            self._send(404, b"not found")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path not in ("/max/webhook", "/webhook", "/"):
                self._send(404, b"not found")
                return
            if not verify_webhook_secret({k: v for k, v in self.headers.items()}):
                self._send(403, b"forbidden")
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                update = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._send(400, b"bad json")
                return
            # MAX требует 200 быстро — обрабатываем в фоне
            self._send(200, b"ok")
            try:
                asyncio.run(process_update(client, update))
            except Exception:
                logger.exception("Failed to process MAX webhook update")

    return Handler


def run_webhook_server(client: MaxApiClient) -> None:
    handler = make_webhook_handler(client)
    server = HTTPServer(("0.0.0.0", PORT), handler)
    logger.info("MAX webhook server listening on 0.0.0.0:%s", PORT)
    if MAX_WEBHOOK_URL:
        try:
            result = client.subscribe_webhook(
                MAX_WEBHOOK_URL,
                update_types=["message_created", "message_callback", "bot_started"],
                secret=MAX_WEBHOOK_SECRET or None,
            )
            logger.info("Webhook subscribed: %s -> %s", MAX_WEBHOOK_URL, result)
        except Exception:
            logger.exception("Failed to subscribe webhook; check MAX_WEBHOOK_URL / TLS")
    server.serve_forever()


def run_long_polling(client: MaxApiClient) -> None:
    logger.info("MAX long polling started (dev/test mode)")
    marker: Optional[int] = None
    types = ["message_created", "message_callback", "bot_started"]
    while True:
        try:
            data = client.get_updates(marker=marker, timeout=30, types=types)
            updates = data.get("updates") or []
            marker = data.get("marker", marker)
            for update in updates:
                try:
                    asyncio.run(process_update(client, update))
                except Exception:
                    logger.exception("Failed to process update")
        except MaxApiError as exc:
            logger.error("Polling API error: %s", exc)
            time.sleep(3)
        except Exception:
            logger.exception("Polling loop error")
            time.sleep(3)


def resolve_mode() -> str:
    if MAX_MODE in ("webhook", "polling"):
        return MAX_MODE
    if MAX_WEBHOOK_URL:
        return "webhook"
    return "polling"


def main() -> None:
    if not MAX_BOT_TOKEN:
        raise SystemExit(
            "Задайте MAX_BOT_TOKEN (токен бота из кабинета MAX / «MAX для бизнеса»).\n"
            "Документация: https://dev.max.ru/docs/chatbots/bots-coding/prepare"
        )

    client = MaxApiClient(MAX_BOT_TOKEN)
    try:
        me = client.get_me()
        logger.info("Authorized as MAX bot: %s (@%s)", me.get("name"), me.get("username"))
    except Exception as exc:
        logger.warning("GET /me failed (token may still work for messaging): %s", exc)

    mode = resolve_mode()
    logger.info("Starting MAX bot in %s mode", mode)
    if mode == "webhook":
        # health endpoint always available; polling not used when webhook is active
        run_webhook_server(client)
    else:
        # health check in background for Render/Docker
        def _health() -> None:
            handler = make_webhook_handler(client)
            HTTPServer(("0.0.0.0", PORT), handler).serve_forever()

        threading.Thread(target=_health, daemon=True).start()
        run_long_polling(client)


if __name__ == "__main__":
    main()
