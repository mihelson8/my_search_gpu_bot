"""
Telegram Bot for Feline Visual Triage.
Телеграм-бот для предварительной оценки состояния кошки по визуальным признакам
с фотографий и коротких видео, с подбором справочных данных о препаратах.

Бот не ставит диагноз и не назначает лечение: он оценивает срочность обращения
к ветеринарному врачу и готовит структурированную информацию для приёма.
"""

import asyncio
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional, Tuple

try:
    from telegram import (
        BotCommand,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        KeyboardButton,
        ReplyKeyboardMarkup,
        Update,
    )
    from telegram.constants import ParseMode
    from telegram.error import BadRequest
    from telegram.ext import (
        ApplicationBuilder,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

from vetcare.engine import EMERGENCY_SIGNS, CaseSession, PatientInfo, VisualTriageEngine
from vetcare.knowledge import (
    MEDICATIONS,
    SIGNS,
    ZONE_LABELS,
    BodyZone,
    medication_groups,
    signs_by_zone,
)
from vetcare.media import (
    MAX_FILE_MB,
    MAX_VIDEO_SECONDS,
    check_video,
    extract_frames_from_bytes,
    ffmpeg_path,
)
from vetcare.report import (
    format_assessment_html,
    format_emergency_html,
    format_first_aid_html,
    format_help_html,
    format_media_analysis_html,
    format_medication_card_html,
    format_medication_index_html,
    format_photo_guide_html,
    format_session_summary_html,
    format_sign_card_html,
    format_start_html,
    format_toxic_html,
    format_video_guide_html,
    format_zone_intro_html,
)
from vetcare.vision import analyze_frames, analyze_image, merge_analyses

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ENGINE = VisualTriageEngine()

BTN_PHOTO = "📸 Анализ по фото"
BTN_VIDEO = "🎬 Анализ по видео"
BTN_SIGNS = "🩺 Симптомы по зонам"
BTN_REPORT = "📋 Мой отчёт"
BTN_DRUGS = "💊 Справочник лекарств"
BTN_TOXIC = "☠️ Опасные препараты"
BTN_EMERGENCY = "🚨 Экстренные признаки"
BTN_FIRST_AID = "🧰 Первая помощь"
BTN_CASE = "🗂 Текущий разбор"
BTN_HELP = "ℹ️ Помощь"

MAIN_KEYBOARD = [
    [BTN_PHOTO, BTN_VIDEO],
    [BTN_SIGNS, BTN_REPORT],
    [BTN_DRUGS, BTN_TOXIC],
    [BTN_EMERGENCY, BTN_FIRST_AID],
    [BTN_CASE, BTN_HELP],
]

BOT_COMMANDS: List[Tuple[str, str]] = [
    ("start", "Главное меню"),
    ("analyze", "Как снимать фото и видео"),
    ("signs", "Отметить симптомы по зонам тела"),
    ("report", "Оценка по текущему разбору"),
    ("patient", "Указать пол, возраст и вес питомца"),
    ("drugs", "Справочник препаратов"),
    ("toxic", "Что кошкам давать нельзя"),
    ("emergency", "Экстренные признаки"),
    ("firstaid", "Первая помощь до клиники"),
    ("reset", "Очистить текущий разбор"),
    ("help", "Справка по работе бота"),
]

ZONE_ORDER: List[BodyZone] = [
    BodyZone.EYES,
    BodyZone.EARS,
    BodyZone.SKIN,
    BodyZone.MOUTH,
    BodyZone.RESPIRATORY,
    BodyZone.GI,
    BodyZone.URINARY,
    BodyZone.NEURO,
    BodyZone.LOCOMOTION,
    BodyZone.GENERAL,
]

MAX_SUGGESTED_BUTTONS = 6


def main_menu_markup():
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in MAIN_KEYBOARD],
        resize_keyboard=True,
    )


def get_session(context) -> CaseSession:
    """Возвращает разбор текущего пользователя, создавая его при первом обращении."""
    session = context.user_data.get("session")
    if not isinstance(session, CaseSession):
        session = CaseSession()
        context.user_data["session"] = session
    return session


def parse_patient_args(args: List[str]) -> Tuple[PatientInfo, List[str]]:
    """Разбирает свободную строку вида «Барсик кот 5 4.2» в данные пациента."""
    patient = PatientInfo()
    numbers: List[float] = []
    name_parts: List[str] = []
    problems: List[str] = []

    male_words = {"кот", "самец", "мальчик", "male", "m"}
    female_words = {"кошка", "самка", "девочка", "female", "f"}

    for token in args:
        lowered = token.lower().strip(",")
        if lowered in male_words:
            patient.is_male = True
            continue
        if lowered in female_words:
            patient.is_male = False
            continue
        try:
            numbers.append(float(lowered.replace(",", ".")))
            continue
        except ValueError:
            name_parts.append(token)

    if numbers:
        patient.age_years = numbers[0]
    if len(numbers) > 1:
        patient.weight_kg = numbers[1]
    if name_parts:
        patient.name = " ".join(name_parts)[:40]

    if patient.age_years is not None and not 0 <= patient.age_years <= 30:
        problems.append("возраст выглядит нереальным, укажите в годах")
        patient.age_years = None
    if patient.weight_kg is not None and not 0.1 <= patient.weight_kg <= 15:
        problems.append("вес выглядит нереальным, укажите в килограммах")
        patient.weight_kg = None

    return patient, problems


def build_zones_keyboard(session: CaseSession):
    """Меню зон тела с количеством отмеченных признаков в каждой зоне."""
    rows = []
    for index in range(0, len(ZONE_ORDER), 2):
        row = []
        for zone in ZONE_ORDER[index: index + 2]:
            marked = sum(
                1
                for sign in signs_by_zone(zone)
                if sign.code in session.confirmed_signs
            )
            title = ZONE_LABELS[zone]
            if marked:
                title = f"{title} ({marked})"
            row.append(InlineKeyboardButton(title, callback_data=f"zone:{zone.value}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🎯 Показать оценку", callback_data="report")])
    rows.append([InlineKeyboardButton("🧹 Очистить разбор", callback_data="reset")])
    return InlineKeyboardMarkup(rows)


def build_zone_keyboard(zone: BodyZone, session: CaseSession):
    """Чеклист признаков одной зоны с переключателями."""
    rows = []
    for sign in signs_by_zone(zone):
        mark = "✅" if sign.code in session.confirmed_signs else "⬜"
        flag = " 🚨" if sign.is_red_flag else ""
        camera = " 🎬" if sign.video_only else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{mark} {sign.label}{flag}{camera}",
                    callback_data=f"sign:{zone.value}:{sign.code}",
                ),
                InlineKeyboardButton("❓", callback_data=f"ask:{sign.code}"),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("⬅️ Зоны", callback_data="zones"),
            InlineKeyboardButton("🎯 Оценка", callback_data="report"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_media_keyboard(session: CaseSession):
    """Кнопки подтверждения признаков, подсказанных разбором медиа."""
    rows = []
    for sign_code in session.suggested_signs[:MAX_SUGGESTED_BUTTONS]:
        sign = SIGNS[sign_code]
        rows.append(
            [
                InlineKeyboardButton(f"✅ {sign.label}", callback_data=f"conf:{sign_code}"),
                InlineKeyboardButton("нет", callback_data=f"no:{sign_code}"),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("🩺 Все симптомы", callback_data="zones"),
            InlineKeyboardButton("🎯 Оценка", callback_data="report"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_drug_groups_keyboard():
    groups = sorted(medication_groups().keys())
    rows = [
        [InlineKeyboardButton(group, callback_data=f"dgrp:{index}")]
        for index, group in enumerate(groups)
    ]
    return InlineKeyboardMarkup(rows)


def build_drug_list_keyboard(group_index: int):
    groups = sorted(medication_groups().keys())
    if not 0 <= group_index < len(groups):
        return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Группы", callback_data="drugs")]])
    group = groups[group_index]
    rows = [
        [InlineKeyboardButton(med.name, callback_data=f"drug:{med.code}")]
        for med in medication_groups()[group]
    ]
    rows.append([InlineKeyboardButton("⬅️ Группы", callback_data="drugs")])
    return InlineKeyboardMarkup(rows)


def emergency_alert_html(sign_code: str) -> Optional[str]:
    """Баннер немедленного действия при подтверждении угрожающего признака."""
    if sign_code not in EMERGENCY_SIGNS:
        return None
    sign = SIGNS.get(sign_code)
    if sign is None:
        return None
    return (
        "🔴 <b>ЭТО УГРОЖАЮЩИЙ ПРИЗНАК</b>\n\n"
        f"«{sign.label}» у кошек означает состояние, при котором счёт идёт на часы.\n\n"
        "Не собирайте больше фото и не ждите оценку бота: звоните в круглосуточную "
        "клинику и выезжайте. Ничего не давайте внутрь без указания врача."
    )


if TELEGRAM_AVAILABLE:

    async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        get_session(context)
        if update.message:
            await update.message.reply_text(
                format_start_html(),
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_markup(),
            )

    async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(format_help_html(), parse_mode=ParseMode.HTML)

    async def analyze_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(format_photo_guide_html(), parse_mode=ParseMode.HTML)
            await update.message.reply_text(format_video_guide_html(), parse_mode=ParseMode.HTML)

    async def signs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = get_session(context)
        if update.message:
            await update.message.reply_text(
                "🩺 <b>Выберите зону тела</b>, чтобы отметить признаки.\n\n"
                "🚨 отмечены тревожные признаки, 🎬 лучше видны на видео.",
                parse_mode=ParseMode.HTML,
                reply_markup=build_zones_keyboard(session),
            )

    async def report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = get_session(context)
        if not update.message:
            return
        if session.is_empty:
            await update.message.reply_text(
                "Пока нечего оценивать. Пришлите фото или видео, либо отметьте симптомы "
                "в разделе «Симптомы по зонам».",
                parse_mode=ParseMode.HTML,
                reply_markup=build_zones_keyboard(session),
            )
            return
        assessment = ENGINE.assess(session)
        await update.message.reply_text(
            format_assessment_html(assessment, session),
            parse_mode=ParseMode.HTML,
            reply_markup=build_zones_keyboard(session),
        )

    async def case_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = get_session(context)
        if update.message:
            await update.message.reply_text(
                format_session_summary_html(session),
                parse_mode=ParseMode.HTML,
                reply_markup=build_zones_keyboard(session),
            )

    async def drugs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(
                format_medication_index_html(),
                parse_mode=ParseMode.HTML,
                reply_markup=build_drug_groups_keyboard(),
            )

    async def toxic_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(format_toxic_html(), parse_mode=ParseMode.HTML)

    async def emergency_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(format_emergency_html(), parse_mode=ParseMode.HTML)

    async def first_aid_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(format_first_aid_html(), parse_mode=ParseMode.HTML)

    async def reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = get_session(context)
        session.reset()
        context.user_data.pop("media_group_id", None)
        context.user_data.pop("media_group_items", None)
        context.user_data.pop("media_group_message_id", None)
        if update.message:
            await update.message.reply_text(
                "🧹 Разбор очищен. Можно начинать заново: пришлите фото или видео.",
                reply_markup=main_menu_markup(),
            )

    async def patient_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        session = get_session(context)
        if not context.args:
            await update.message.reply_text(
                "Укажите данные питомца: <code>/patient Барсик кот 5 4.2</code>\n"
                "Порядок свободный: имя, пол (кот или кошка), возраст в годах, вес в кг.\n\n"
                "Пол и возраст влияют на оценку срочности: у котов закупорка уретры "
                "развивается быстрее, а котята и пожилые кошки декомпенсируются раньше.",
                parse_mode=ParseMode.HTML,
            )
            return

        patient, problems = parse_patient_args(list(context.args))
        session.patient = patient
        details = []
        if patient.name:
            details.append(f"имя {patient.name}")
        if patient.is_male is not None:
            details.append("кот" if patient.is_male else "кошка")
        if patient.age_years is not None:
            details.append(f"возраст {patient.age_years:g} лет")
        if patient.weight_kg is not None:
            details.append(f"вес {patient.weight_kg:g} кг")

        text = "✅ Данные сохранены: " + (", ".join(details) if details else "ничего не распознано")
        if problems:
            text += "\n⚠️ " + "; ".join(problems)
        await update.message.reply_text(text)

    async def _download_bytes(message, file_id: str) -> Optional[bytes]:
        try:
            telegram_file = await message.get_bot().get_file(file_id)
            return bytes(await telegram_file.download_as_bytearray())
        except Exception as exc:  # noqa: BLE001 - сеть и лимиты Telegram
            logger.warning("Не удалось скачать файл %s: %s", file_id, exc)
            return None

    async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        if message is None:
            return

        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document and (message.document.mime_type or "").startswith("image/"):
            file_id = message.document.file_id
        else:
            return

        session = get_session(context)
        data = await _download_bytes(message, file_id)
        if data is None:
            await message.reply_text(
                "Не удалось скачать фото. Попробуйте отправить его ещё раз, "
                "лучше как сжатое изображение, а не файлом."
            )
            return

        analysis = await asyncio.to_thread(analyze_image, data)
        session.add_media(analysis)

        group_id = message.media_group_id
        if group_id and context.user_data.get("media_group_id") == group_id:
            items = context.user_data.setdefault("media_group_items", [])
            items.append(analysis)
            aggregated = merge_analyses(items, kind="photo")
            message_id = context.user_data.get("media_group_message_id")
            if message_id:
                text = (
                    f"📷 Обработано фото в альбоме: <b>{len(items)}</b>\n\n"
                    + format_media_analysis_html(aggregated)
                )
                try:
                    await context.bot.edit_message_text(
                        chat_id=message.chat_id,
                        message_id=message_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=build_media_keyboard(session),
                    )
                except BadRequest as exc:
                    logger.debug("Сообщение альбома не обновлено: %s", exc)
                return

        sent = await message.reply_text(
            format_media_analysis_html(analysis),
            parse_mode=ParseMode.HTML,
            reply_markup=build_media_keyboard(session),
        )
        if group_id:
            context.user_data["media_group_id"] = group_id
            context.user_data["media_group_items"] = [analysis]
            context.user_data["media_group_message_id"] = sent.message_id

    async def video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        if message is None:
            return

        media = message.video or message.video_note or message.animation
        if media is None and message.document:
            if (message.document.mime_type or "").startswith("video/"):
                media = message.document
        if media is None:
            return

        duration = getattr(media, "duration", None)
        verdict = check_video(duration, media.file_size)
        if not verdict.accepted:
            await message.reply_text(
                f"⚠️ {verdict.message}\n\n" + format_video_guide_html(),
                parse_mode=ParseMode.HTML,
            )
            return

        if ffmpeg_path() is None:
            await message.reply_text(
                "На сервере не установлен ffmpeg, поэтому видео разобрать нельзя. "
                "Пришлите несколько фотографий проблемной зоны."
            )
            return

        session = get_session(context)
        status = await message.reply_text(
            "⏳ Разбираю видео: извлекаю кадры и оцениваю движение..."
        )

        data = await _download_bytes(message, media.file_id)
        if data is None:
            await status.edit_text(
                "Не удалось скачать видео. Проверьте, что файл короче "
                f"{MAX_VIDEO_SECONDS} секунд и меньше {MAX_FILE_MB} МБ."
            )
            return

        frames = await asyncio.to_thread(extract_frames_from_bytes, data)
        analysis = await asyncio.to_thread(analyze_frames, frames, "video")
        session.add_media(analysis)

        await status.edit_text(
            format_media_analysis_html(analysis),
            parse_mode=ParseMode.HTML,
            reply_markup=build_media_keyboard(session),
        )

    async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.data is None:
            return
        await query.answer()

        session = get_session(context)
        data = query.data

        if data == "zones":
            await query.edit_message_text(
                "🩺 <b>Выберите зону тела</b>, чтобы отметить признаки.\n\n"
                "🚨 отмечены тревожные признаки, 🎬 лучше видны на видео.",
                parse_mode=ParseMode.HTML,
                reply_markup=build_zones_keyboard(session),
            )
            return

        if data == "report":
            if session.is_empty:
                await query.edit_message_text(
                    "Пока нечего оценивать. Пришлите фото или видео, либо отметьте признаки.",
                    reply_markup=build_zones_keyboard(session),
                )
                return
            assessment = ENGINE.assess(session)
            await query.edit_message_text(
                format_assessment_html(assessment, session),
                parse_mode=ParseMode.HTML,
                reply_markup=build_zones_keyboard(session),
            )
            return

        if data == "reset":
            session.reset()
            await query.edit_message_text(
                "🧹 Разбор очищен. Пришлите новое фото или видео.",
                reply_markup=build_zones_keyboard(session),
            )
            return

        if data.startswith("zone:"):
            try:
                zone = BodyZone(data.split(":", 1)[1])
            except ValueError:
                return
            await query.edit_message_text(
                format_zone_intro_html(zone),
                parse_mode=ParseMode.HTML,
                reply_markup=build_zone_keyboard(zone, session),
            )
            return

        if data.startswith("sign:"):
            _, zone_value, sign_code = data.split(":", 2)
            try:
                zone = BodyZone(zone_value)
            except ValueError:
                return
            confirmed = session.toggle(sign_code)
            try:
                await query.edit_message_reply_markup(
                    reply_markup=build_zone_keyboard(zone, session)
                )
            except BadRequest as exc:
                logger.debug("Клавиатура зоны не обновлена: %s", exc)
            if confirmed:
                alert = emergency_alert_html(sign_code)
                if alert:
                    await query.message.reply_text(alert, parse_mode=ParseMode.HTML)
            return

        if data.startswith("conf:") or data.startswith("no:"):
            action, sign_code = data.split(":", 1)
            if action == "conf":
                session.confirm(sign_code)
            else:
                session.reject(sign_code)
            try:
                await query.edit_message_reply_markup(
                    reply_markup=build_media_keyboard(session)
                )
            except BadRequest as exc:
                logger.debug("Клавиатура подсказок не обновлена: %s", exc)
            if action == "conf":
                alert = emergency_alert_html(sign_code)
                if alert:
                    await query.message.reply_text(alert, parse_mode=ParseMode.HTML)
            return

        if data.startswith("ask:"):
            sign_code = data.split(":", 1)[1]
            await query.message.reply_text(
                format_sign_card_html(sign_code), parse_mode=ParseMode.HTML
            )
            return

        if data == "drugs":
            await query.edit_message_text(
                format_medication_index_html(),
                parse_mode=ParseMode.HTML,
                reply_markup=build_drug_groups_keyboard(),
            )
            return

        if data.startswith("dgrp:"):
            try:
                group_index = int(data.split(":", 1)[1])
            except ValueError:
                return
            groups = sorted(medication_groups().keys())
            title = groups[group_index] if 0 <= group_index < len(groups) else "Группа"
            await query.edit_message_text(
                f"💊 <b>{title}</b>\n\nВыберите препарат, чтобы открыть карточку.",
                parse_mode=ParseMode.HTML,
                reply_markup=build_drug_list_keyboard(group_index),
            )
            return

        if data.startswith("drug:"):
            code = data.split(":", 1)[1]
            med = MEDICATIONS.get(code)
            if med is None:
                return
            await query.message.reply_text(
                format_medication_card_html(med), parse_mode=ParseMode.HTML
            )
            return

    MENU_ACTIONS: Dict[str, str] = {
        BTN_PHOTO: "photo_guide",
        BTN_VIDEO: "video_guide",
        BTN_SIGNS: "signs",
        BTN_REPORT: "report",
        BTN_DRUGS: "drugs",
        BTN_TOXIC: "toxic",
        BTN_EMERGENCY: "emergency",
        BTN_FIRST_AID: "first_aid",
        BTN_CASE: "case",
        BTN_HELP: "help",
    }

    async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return

        action = MENU_ACTIONS.get(update.message.text.strip())

        if action == "photo_guide":
            await update.message.reply_text(format_photo_guide_html(), parse_mode=ParseMode.HTML)
        elif action == "video_guide":
            await update.message.reply_text(format_video_guide_html(), parse_mode=ParseMode.HTML)
        elif action == "signs":
            await signs_handler(update, context)
        elif action == "report":
            await report_handler(update, context)
        elif action == "drugs":
            await drugs_handler(update, context)
        elif action == "toxic":
            await toxic_handler(update, context)
        elif action == "emergency":
            await emergency_handler(update, context)
        elif action == "first_aid":
            await first_aid_handler(update, context)
        elif action == "case":
            await case_handler(update, context)
        elif action == "help":
            await help_handler(update, context)
        else:
            await update.message.reply_text(
                "Я работаю с фото и короткими видео. Пришлите снимок проблемной зоны "
                "или выберите пункт меню ниже.\n\n"
                "Описать симптомы словами можно через раздел «Симптомы по зонам»: "
                "там они превращаются в структурированный чеклист.",
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_markup(),
            )

    async def post_init(application) -> None:
        await application.bot.set_my_commands(
            [BotCommand(command, description) for command, description in BOT_COMMANDS]
        )


def build_vet_bot_application(token: str):
    """Создаёт и настраивает приложение Telegram-бота."""
    if not TELEGRAM_AVAILABLE:
        raise RuntimeError("python-telegram-bot не установлен.")

    app = ApplicationBuilder().token(token).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("analyze", analyze_handler))
    app.add_handler(CommandHandler("signs", signs_handler))
    app.add_handler(CommandHandler("report", report_handler))
    app.add_handler(CommandHandler("case", case_handler))
    app.add_handler(CommandHandler("patient", patient_handler))
    app.add_handler(CommandHandler("drugs", drugs_handler))
    app.add_handler(CommandHandler("toxic", toxic_handler))
    app.add_handler(CommandHandler("emergency", emergency_handler))
    app.add_handler(CommandHandler("firstaid", first_aid_handler))
    app.add_handler(CommandHandler("reset", reset_handler))

    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, photo_handler))
    app.add_handler(
        MessageHandler(
            filters.VIDEO | filters.VIDEO_NOTE | filters.ANIMATION | filters.Document.VIDEO,
            video_handler,
        )
    )
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    return app


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Feline Visual Triage Telegram Bot is running OK!")

    def log_message(self, format, *args):
        pass


def start_health_check_server(port: int = 10000):
    """Запускает фоновый HTTP-сервер для health-check хостинга."""
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info("Health-check HTTP сервер запущен на порту %s", port)
    except OSError as exc:
        logger.warning("Не удалось запустить health-check сервер на порту %s: %s", port, exc)


def main():
    # В репозитории несколько ботов, поэтому у этого может быть свой токен.
    token = os.getenv("VET_BOT_TOKEN") or os.getenv("BOT_TOKEN", "")
    port = int(os.getenv("PORT", 10000))

    if not token:
        print("Ошибка: переменная окружения VET_BOT_TOKEN или BOT_TOKEN не установлена.")
        print("Установите токен: export VET_BOT_TOKEN='ваш_токен_от_BotFather'")
        print("Или запустите консольный режим: python3 vetcare_cli.py")
        sys.exit(1)

    if ffmpeg_path() is None:
        logger.warning("ffmpeg не найден: разбор видео будет недоступен, фото работают штатно")

    start_health_check_server(port)

    print("Запуск ветеринарного Telegram-бота визуального триажа...")
    app = build_vet_bot_application(token)
    app.run_polling()


if __name__ == "__main__":
    main()
