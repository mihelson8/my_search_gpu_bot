"""
Формирование текстов отчётов для Telegram (HTML) и консоли.
Вся пользовательская выдача собирается здесь, чтобы бот и CLI показывали одно и то же.
"""

from __future__ import annotations

import html
from typing import List, Optional

from vetcare.engine import Assessment, CaseSession, Differential
from vetcare.knowledge import (
    EMERGENCY_CHECKLIST,
    FIRST_AID_RULES,
    MEDICATIONS,
    SIGNS,
    TOXIC_FOR_CATS,
    URGENCY_EMOJI,
    ZONE_LABELS,
    BodyZone,
    Medication,
    Urgency,
    medication_groups,
    signs_by_zone,
)
from vetcare.media import MAX_FILE_MB, MAX_VIDEO_SECONDS
from vetcare.vision import MediaAnalysis

DISCLAIMER = (
    "⚠️ <b>Важно:</b> бот не ставит диагноз и не назначает лечение. По фото и видео "
    "невозможно достоверно определить заболевание. Это инструмент сортировки: он "
    "подсказывает, насколько срочно нужен ветеринарный врач и какие вопросы ему задать. "
    "Дозы препаратов рассчитывает только врач по весу, возрасту и анализам."
)

SHORT_DISCLAIMER = (
    "ℹ️ Это предварительная оценка по визуальным признакам, а не диагноз. "
    "Решение о лечении принимает ветеринарный врач."
)


def _esc(text: str) -> str:
    return html.escape(str(text), quote=False)


def format_photo_guide_html() -> str:
    return (
        "📸 <b>КАК СНЯТЬ ПОЛЕЗНОЕ ФОТО</b>\n\n"
        "1. Дневной свет или яркая лампа, <b>без вспышки</b>: вспышка искажает цвет слизистых.\n"
        "2. Снимайте с расстояния 20-30 см, приближайте кадр шагами, а не цифровым зумом.\n"
        "3. Нужный участок должен занимать не меньше половины кадра и быть в фокусе.\n"
        "4. Раздвиньте шерсть пальцами, чтобы видеть кожу, а не волос.\n"
        "5. Сделайте 2-3 ракурса: анфас, сбоку и сравнение с симметричной здоровой стороной.\n"
        "6. Не применяйте фильтры и бьютирежим, они меняют оттенки.\n\n"
        "Можно отправить сразу несколько фото одним альбомом, бот разберёт все кадры.\n\n"
        + SHORT_DISCLAIMER
    )


def format_video_guide_html() -> str:
    return (
        "🎬 <b>КАК СНЯТЬ ПОЛЕЗНОЕ ВИДЕО</b>\n\n"
        f"• Длительность до <b>{MAX_VIDEO_SECONDS} секунд</b>, размер файла до <b>{MAX_FILE_MB} МБ</b>.\n"
        "• Видео нужно для того, что не видно на фото: походка, хромота, дыхание, тряска головой, "
        "судороги, поведение в лотке.\n"
        "• Дыхание снимайте в покое, сбоку, чтобы в кадре были грудная клетка и живот целиком.\n"
        "• Походку снимайте по прямой на нескользком полу, лапы обязательно в кадре.\n"
        "• Звук не отключайте: кашель, крик и хрипы важны врачу.\n"
        "• Держите телефон двумя руками, снимайте горизонтально.\n\n"
        "Бот разложит видео на кадры, оценит их качество, движение и предложит признаки для подтверждения.\n\n"
        + SHORT_DISCLAIMER
    )


def format_media_analysis_html(analysis: MediaAnalysis) -> str:
    kind_label = "фото" if analysis.kind == "photo" else "видео"
    lines: List[str] = [f"🔍 <b>Разбор {kind_label}</b>"]

    if analysis.quality is not None:
        quality = analysis.quality
        icon = "✅" if quality.is_usable else "⚠️"
        lines.append(
            f"\n{icon} Кадр {quality.width}x{quality.height}, яркость "
            f"{int(quality.brightness * 100)}%, резкость {quality.sharpness:.3f}"
        )
        if quality.problems:
            for problem in quality.problems:
                lines.append(f"   • {_esc(problem)}")

    if analysis.frames_analyzed > 1:
        lines.append(f"\n🎞 Проанализировано кадров: <b>{analysis.frames_analyzed}</b>")

    if analysis.motion is not None:
        motion = analysis.motion
        lines.append(
            f"📈 Активность в кадре: {motion.mean_motion:.3f}, "
            f"ритмичность движений: {motion.periodicity:.2f}"
        )

    if analysis.cues:
        lines.append("\n<b>Визуальные подсказки:</b>")
        for cue in analysis.cues:
            lines.append(f"• {_esc(cue.label)} — уверенность {cue.confidence_percent}%")
            lines.append(f"   <i>{_esc(cue.explanation)}</i>")
    else:
        lines.append("\nЯвных цветовых отклонений не найдено.")

    for note in analysis.notes:
        lines.append(f"\nℹ️ {_esc(note)}")

    lines.append(
        "\n<b>Подсказки не являются диагнозом.</b> Отметьте ниже, какие признаки вы "
        "действительно видите: от этого зависит оценка."
    )
    return "\n".join(lines)


def _format_differential(index: int, item: Differential) -> str:
    disease = item.disease
    bar_length = max(1, int(round(item.probability / 10)))
    bar = "█" * bar_length
    lines = [
        f"<b>{index}. {_esc(disease.name)}</b> — {item.probability}%",
        f"   {bar}",
        f"   <i>{_esc(disease.latin)}</i>",
        f"   {_esc(disease.description)}",
    ]
    if item.matched_labels:
        lines.append("   ✅ Совпало: " + _esc(", ".join(item.matched_labels)))
    if item.missing_key_labels:
        lines.append("   ❓ Стоит проверить: " + _esc(", ".join(item.missing_key_labels)))
    urgency_icon = URGENCY_EMOJI[disease.urgency]
    lines.append(f"   {urgency_icon} Срочность: {_esc(disease.urgency.value)}")
    if disease.zoonotic:
        lines.append("   🧑‍⚕️ Заразно для человека, соблюдайте гигиену")
    if disease.notes:
        lines.append(f"   💡 {_esc(disease.notes)}")
    return "\n".join(lines)


def format_assessment_html(assessment: Assessment, session: Optional[CaseSession] = None) -> str:
    urgency_icon = URGENCY_EMOJI[assessment.urgency]
    lines: List[str] = ["📋 <b>ПРЕДВАРИТЕЛЬНАЯ ОЦЕНКА СОСТОЯНИЯ</b>"]

    if session is not None and session.patient.name:
        lines.append(f"Пациент: <b>{_esc(session.patient.name)}</b>")

    lines.append(f"\n{urgency_icon} <b>Срочность: {_esc(assessment.urgency.value)}</b>")

    if assessment.urgency == Urgency.EMERGENCY:
        lines.append(
            "🚑 <b>Не ждите ответа бота и не пробуйте лечить дома.</b> "
            "Везите кошку в круглосуточную клинику прямо сейчас."
        )

    if assessment.red_flags:
        lines.append("\n🚨 <b>Тревожные признаки:</b>")
        for flag in assessment.red_flags:
            lines.append(f"• {_esc(flag)}")

    if assessment.confirmed_signs:
        labels = [SIGNS[code].label for code in assessment.confirmed_signs if code in SIGNS]
        lines.append(f"\n🩺 <b>Отмечено признаков:</b> {len(labels)}")
        lines.append(_esc(", ".join(labels)))
    else:
        lines.append(
            "\n🩺 Признаки пока не отмечены, оценка построена только на визуальных подсказках."
        )

    if assessment.differentials:
        lines.append("\n🎯 <b>Вероятные состояния:</b>\n")
        for index, item in enumerate(assessment.differentials, start=1):
            lines.append(_format_differential(index, item))
            lines.append("")
    else:
        lines.append(
            "\nПо отмеченным данным не удалось выделить вероятные состояния. "
            "Отметьте больше признаков через меню «Симптомы по зонам»."
        )

    lines.append(f"📊 <b>Полнота данных:</b> {_esc(assessment.completeness.value)}")

    if assessment.diagnostics:
        lines.append("\n🔬 <b>Что обычно назначают в клинике:</b>")
        for entry in assessment.diagnostics[:6]:
            lines.append(f"• {_esc(entry)}")

    if assessment.home_care:
        lines.append("\n🏠 <b>Что можно сделать до приёма:</b>")
        for entry in assessment.home_care[:6]:
            lines.append(f"• {_esc(entry)}")

    if assessment.medication_codes:
        med_names = [
            MEDICATIONS[code].name for code in assessment.medication_codes if code in MEDICATIONS
        ]
        lines.append("\n💊 <b>Препараты, которые обсуждают при таких состояниях:</b>")
        lines.append(_esc(", ".join(med_names[:8])))
        lines.append(
            "<i>Это справочный список для разговора с врачом, а не назначение. "
            "Карточки препаратов с дозировками из литературы доступны в разделе «Справочник лекарств».</i>"
        )

    if assessment.zoonotic_warning:
        lines.append(
            "\n🧑‍⚕️ <b>Среди вероятных состояний есть заразное для человека.</b> "
            "Мойте руки после контакта, ограничьте контакт детей с питомцем до осмотра."
        )

    if assessment.media_notes:
        lines.append("\n📷 <b>Замечания по качеству медиа:</b>")
        for note in assessment.media_notes[:4]:
            lines.append(f"• {_esc(note)}")

    if assessment.next_questions:
        lines.append("\n❓ <b>Уточните ещё это, оценка станет точнее:</b>")
        for sign in assessment.next_questions:
            lines.append(f"• {_esc(sign.question)}")

    lines.append("\n" + DISCLAIMER)
    return "\n".join(lines)


def format_session_summary_html(session: CaseSession) -> str:
    lines = ["🗂 <b>ТЕКУЩИЙ РАЗБОР</b>"]
    patient = session.patient
    if patient.name or patient.age_years or patient.weight_kg or patient.is_male is not None:
        details: List[str] = []
        if patient.name:
            details.append(f"имя {_esc(patient.name)}")
        if patient.age_years is not None:
            details.append(f"возраст {patient.age_years:g} лет")
        if patient.is_male is not None:
            details.append("кот" if patient.is_male else "кошка")
        if patient.weight_kg is not None:
            details.append(f"вес {patient.weight_kg:g} кг")
        lines.append("Пациент: " + ", ".join(details))

    if session.media:
        photos = sum(1 for item in session.media if item.kind == "photo")
        videos = len(session.media) - photos
        lines.append(f"\n📎 Загружено: фото {photos}, видео {videos}")

    if session.confirmed_signs:
        lines.append("\n✅ <b>Подтверждённые признаки:</b>")
        for code in sorted(session.confirmed_signs):
            if code in SIGNS:
                lines.append(f"• {_esc(SIGNS[code].label)}")
    else:
        lines.append("\nПризнаки пока не отмечены.")

    if session.rejected_signs:
        lines.append(f"\n❌ Отмечено как отсутствующие: {len(session.rejected_signs)}")

    pending = session.suggested_signs
    if pending:
        lines.append("\n🔎 <b>Ждут вашего подтверждения по медиа:</b>")
        for code in pending[:6]:
            lines.append(f"• {_esc(SIGNS[code].question)}")

    return "\n".join(lines)


def format_zone_intro_html(zone: BodyZone) -> str:
    label = ZONE_LABELS[zone]
    signs = signs_by_zone(zone)
    lines = [
        f"{label}: отметьте всё, что видите у вашей кошки.",
        f"Доступно признаков: {len(signs)}.",
        "",
        "Нажатие переключает отметку: ⬜ не отмечено, ✅ подтверждено.",
    ]
    video_signs = [sign for sign in signs if sign.video_only]
    if video_signs:
        lines.append("")
        lines.append("🎬 Эти признаки лучше видны на видео:")
        for sign in video_signs:
            lines.append(f"• {_esc(sign.label)}")
    return "\n".join(lines)


def format_sign_card_html(sign_code: str) -> str:
    sign = SIGNS.get(sign_code)
    if sign is None:
        return "Признак не найден."
    lines = [
        f"🩺 <b>{_esc(sign.label)}</b>",
        f"Зона: {ZONE_LABELS[sign.zone]}",
        "",
        f"<b>Вопрос:</b> {_esc(sign.question)}",
        f"<b>Как снять:</b> {_esc(sign.media_hint)}",
    ]
    if sign.is_red_flag:
        lines.append("\n🚨 Это тревожный признак, при его наличии не откладывайте визит к врачу.")
    return "\n".join(lines)


def format_medication_card_html(med: Medication) -> str:
    lines = [
        f"💊 <b>{_esc(med.name)}</b>",
        f"<i>{_esc(med.group)}</i>",
        "",
        f"<b>Формы:</b> {_esc(', '.join(med.forms))}",
        f"<b>Торговые названия:</b> {_esc(', '.join(med.brands))}",
        "",
        "<b>Применяют при:</b>",
    ]
    for item in med.indications:
        lines.append(f"• {_esc(item)}")

    lines.append("")
    lines.append(f"<b>Дозировка (справочно):</b>\n{_esc(med.dose_reference)}")

    if med.cautions:
        lines.append("\n<b>Особенности у кошек:</b>")
        for item in med.cautions:
            lines.append(f"• {_esc(item)}")

    if med.contraindications:
        lines.append("\n<b>Противопоказания:</b>")
        for item in med.contraindications:
            lines.append(f"• {_esc(item)}")

    lines.append("")
    if med.prescription_only:
        lines.append("🔒 <b>Только по назначению ветеринарного врача.</b>")
    else:
        lines.append("🟢 Отпускается без рецепта, но применять стоит после консультации.")

    lines.append(
        "\n⚠️ Дозы приведены как литературная справка для разговора с врачом. "
        "Самостоятельный подбор дозы у кошек опасен: их метаболизм отличается от собак и людей."
    )
    return "\n".join(lines)


def format_medication_index_html() -> str:
    groups = medication_groups()
    lines = [
        "💊 <b>СПРАВОЧНИК ПРЕПАРАТОВ</b>",
        f"В базе {len(MEDICATIONS)} препаратов в {len(groups)} группах.",
        "",
        "Выберите группу в меню ниже. В карточке будут показания, формы выпуска, "
        "литературные дозировки, особенности у кошек и противопоказания.",
        "",
        "⚠️ Справочник не заменяет назначение врача.",
    ]
    return "\n".join(lines)


def format_toxic_html() -> str:
    lines = [
        "☠️ <b>ЧТО НЕЛЬЗЯ ДАВАТЬ КОШКАМ</b>",
        "",
        "Кошки лишены части ферментов печени, поэтому обычные для людей лекарства "
        "для них смертельны.",
        "",
    ]
    for item in TOXIC_FOR_CATS:
        lines.append(f"🚫 <b>{_esc(item.name)}</b>")
        lines.append(f"   {_esc(item.why_dangerous)}")
        lines.append(f"   <i>{_esc(item.note)}</i>")
        lines.append("")
    lines.append(
        "При подозрении на отравление сразу в клинику, возьмите упаковку вещества с собой."
    )
    return "\n".join(lines)


def format_emergency_html() -> str:
    lines = [
        "🚨 <b>ЭКСТРЕННЫЕ ПРИЗНАКИ: ЕХАТЬ НЕМЕДЛЕННО</b>",
        "",
    ]
    for item in EMERGENCY_CHECKLIST:
        lines.append(f"🔴 {_esc(item)}")
    lines.append("")
    lines.append(
        "Если есть хотя бы один пункт, не тратьте время на фото и опросы: "
        "звоните в круглосуточную клинику и выезжайте."
    )
    lines.append("")
    lines.append(
        "Отдельно про котов: натуживание в лотке без выделения мочи это угроза жизни "
        "в течение 24-48 часов."
    )
    return "\n".join(lines)


def format_first_aid_html() -> str:
    lines = ["🧰 <b>ПЕРВАЯ ПОМОЩЬ ДО КЛИНИКИ</b>", ""]
    for index, rule in enumerate(FIRST_AID_RULES, start=1):
        lines.append(f"{index}. {_esc(rule)}")
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def format_help_html() -> str:
    return (
        "ℹ️ <b>КАК ПОЛЬЗОВАТЬСЯ БОТОМ</b>\n\n"
        "Бот помогает разобраться, насколько срочно кошке нужен врач, по визуальным "
        "признакам с фото и коротких видео.\n\n"
        "<b>Порядок работы:</b>\n"
        "1. Отправьте фото проблемной зоны или короткое видео (можно альбомом).\n"
        "2. Бот оценит качество кадра и предложит визуальные подсказки.\n"
        "3. Подтвердите кнопками, какие признаки вы действительно видите.\n"
        "4. Добавьте симптомы через раздел «Симптомы по зонам».\n"
        "5. Получите оценку срочности, список вероятных состояний и вопросы для врача.\n\n"
        "<b>Команды:</b>\n"
        "• <code>/start</code> — главное меню\n"
        "• <code>/analyze</code> — как снимать фото и видео\n"
        "• <code>/signs</code> — отметить симптомы по зонам тела\n"
        "• <code>/report</code> — показать оценку по текущему разбору\n"
        "• <code>/drugs</code> — справочник препаратов\n"
        "• <code>/toxic</code> — что кошкам давать нельзя\n"
        "• <code>/emergency</code> — экстренные признаки\n"
        "• <code>/firstaid</code> — первая помощь\n"
        "• <code>/patient кот 5 4.2</code> — пол, возраст в годах, вес в кг\n"
        "• <code>/reset</code> — очистить текущий разбор\n\n"
        + DISCLAIMER
    )


def format_start_html() -> str:
    return (
        "👋 <b>Ветеринарный визуальный триаж для кошек</b>\n\n"
        "Пришлите фото проблемной зоны или короткое видео, и бот подскажет, "
        "насколько срочно нужен врач, какие состояния наиболее вероятны и о чём "
        "спросить на приёме.\n\n"
        "🔎 Что умеет бот:\n"
        f"• разбор фото и видео до {MAX_VIDEO_SECONDS} секунд с проверкой качества кадра;\n"
        "• опросник по визуальным признакам по 10 зонам тела;\n"
        "• оценка срочности от планового визита до экстренной поездки;\n"
        "• справочник препаратов и список опасных для кошек веществ.\n\n"
        + DISCLAIMER
    )


def format_assessment_text(assessment: Assessment) -> str:
    """Простой текстовый вариант отчёта для консоли."""
    lines = [
        "ПРЕДВАРИТЕЛЬНАЯ ОЦЕНКА",
        f"Срочность: {assessment.urgency.value}",
        f"Полнота данных: {assessment.completeness.value}",
    ]
    if assessment.red_flags:
        lines.append("Тревожные признаки: " + ", ".join(assessment.red_flags))
    lines.append("")
    if assessment.differentials:
        lines.append("Вероятные состояния:")
        for index, item in enumerate(assessment.differentials, start=1):
            lines.append(f"{index}. {item.disease.name} — {item.probability}%")
            if item.matched_labels:
                lines.append("   совпало: " + ", ".join(item.matched_labels))
    else:
        lines.append("Недостаточно данных для формирования списка состояний.")
    if assessment.next_questions:
        lines.append("")
        lines.append("Уточняющие вопросы:")
        for sign in assessment.next_questions:
            lines.append(f"- {sign.question}")
    lines.append("")
    lines.append("Бот не ставит диагноз. Обратитесь к ветеринарному врачу.")
    return "\n".join(lines)
