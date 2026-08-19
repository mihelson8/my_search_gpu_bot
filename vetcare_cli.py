"""
Консольный интерфейс ветеринарного визуального триажа кошек.
Позволяет проверить работу движка и разбора медиа без Telegram-токена.

Примеры:
    python3 vetcare_cli.py photo eye.jpg
    python3 vetcare_cli.py video gait.mp4
    python3 vetcare_cli.py signs --zone eyes
    python3 vetcare_cli.py assess eye_redness eye_discharge --male --age 5
    python3 vetcare_cli.py drug meloxicam
    python3 vetcare_cli.py interactive
"""

import argparse
import html
import re
import sys
from typing import List, Optional

from vetcare.engine import CaseSession, PatientInfo, VisualTriageEngine
from vetcare.knowledge import (
    MEDICATIONS,
    SIGNS,
    ZONE_LABELS,
    BodyZone,
    signs_by_zone,
)
from vetcare.media import extract_frames, ffmpeg_path
from vetcare.report import (
    format_assessment_text,
    format_medication_card_html,
    format_toxic_html,
)
from vetcare.vision import analyze_frames, analyze_image

ENGINE = VisualTriageEngine()


def plain(text: str) -> str:
    """Убирает HTML-разметку из готовых отчётов для вывода в терминал."""
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def print_media_analysis(analysis) -> None:
    if analysis.quality is not None:
        quality = analysis.quality
        print(
            f"Кадр: {quality.width}x{quality.height}, яркость {quality.brightness:.2f}, "
            f"резкость {quality.sharpness:.4f}"
        )
        for problem in quality.problems:
            print(f"  ! {problem}")
    if analysis.frames_analyzed > 1:
        print(f"Кадров проанализировано: {analysis.frames_analyzed}")
    if analysis.motion is not None:
        motion = analysis.motion
        print(
            f"Движение: среднее {motion.mean_motion:.4f}, пик {motion.peak_motion:.4f}, "
            f"ритмичность {motion.periodicity:.2f}"
        )
    if analysis.cues:
        print("\nВизуальные подсказки:")
        for cue in analysis.cues:
            signs = ", ".join(cue.suggested_signs)
            print(f"  - {cue.label} ({cue.confidence_percent}%) -> {signs}")
    else:
        print("\nЦветовых отклонений не найдено.")
    for note in analysis.notes:
        print(f"\n{note}")


def build_patient(args) -> PatientInfo:
    is_male: Optional[bool] = None
    if getattr(args, "male", False):
        is_male = True
    elif getattr(args, "female", False):
        is_male = False
    return PatientInfo(
        name=getattr(args, "name", "") or "",
        age_years=getattr(args, "age", None),
        is_male=is_male,
        weight_kg=getattr(args, "weight", None),
    )


def cmd_photo(args) -> int:
    with open(args.path, "rb") as handle:
        analysis = analyze_image(handle.read())
    print_media_analysis(analysis)

    session = CaseSession(patient=build_patient(args))
    session.add_media(analysis)
    for code in args.sign or []:
        session.confirm(code)
    print("\n" + format_assessment_text(ENGINE.assess(session)))
    return 0


def cmd_video(args) -> int:
    if ffmpeg_path() is None:
        print("ffmpeg не найден, установите его: apt install ffmpeg")
        return 1
    frames = extract_frames(args.path, max_frames=args.frames)
    if not frames:
        print("Не удалось извлечь кадры из видео.")
        return 1
    analysis = analyze_frames(frames, kind="video")
    print_media_analysis(analysis)

    session = CaseSession(patient=build_patient(args))
    session.add_media(analysis)
    for code in args.sign or []:
        session.confirm(code)
    print("\n" + format_assessment_text(ENGINE.assess(session)))
    return 0


def cmd_signs(args) -> int:
    zones: List[BodyZone]
    if args.zone:
        try:
            zones = [BodyZone(args.zone)]
        except ValueError:
            print(f"Неизвестная зона: {args.zone}")
            print("Доступные зоны: " + ", ".join(zone.value for zone in BodyZone))
            return 1
    else:
        zones = list(BodyZone)

    for zone in zones:
        print(f"\n{ZONE_LABELS[zone]} [{zone.value}]")
        for sign in signs_by_zone(zone):
            marks = []
            if sign.is_red_flag:
                marks.append("тревожный")
            if sign.video_only:
                marks.append("видео")
            suffix = f" ({', '.join(marks)})" if marks else ""
            print(f"  {sign.code:<24} {sign.label}{suffix}")
    return 0


def cmd_assess(args) -> int:
    session = CaseSession(patient=build_patient(args))
    unknown = [code for code in args.signs if code not in SIGNS]
    if unknown:
        print("Неизвестные коды признаков: " + ", ".join(unknown))
        print("Список кодов: python3 vetcare_cli.py signs")
        return 1
    for code in args.signs:
        session.confirm(code)
    print(format_assessment_text(ENGINE.assess(session)))
    return 0


def cmd_drug(args) -> int:
    if args.code is None:
        print("Препараты в базе:")
        for code, med in MEDICATIONS.items():
            print(f"  {code:<26} {med.name} — {med.group}")
        return 0
    med = MEDICATIONS.get(args.code)
    if med is None:
        print(f"Препарат {args.code} не найден.")
        return 1
    print(plain(format_medication_card_html(med)))
    return 0


def cmd_toxic(_args) -> int:
    print(plain(format_toxic_html()))
    return 0


def cmd_interactive(args) -> int:
    session = CaseSession(patient=build_patient(args))
    print("Отметьте признаки: y - да, n - нет, s - пропустить, q - закончить опрос.\n")

    for zone in BodyZone:
        print(f"--- {ZONE_LABELS[zone]} ---")
        for sign in signs_by_zone(zone):
            answer = input(f"{sign.question} [y/n/s/q]: ").strip().lower()
            if answer == "q":
                print()
                print(format_assessment_text(ENGINE.assess(session)))
                return 0
            if answer == "y":
                session.confirm(sign.code)
            elif answer == "n":
                session.reject(sign.code)
        print()

    print(format_assessment_text(ENGINE.assess(session)))
    return 0


def add_patient_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", help="кличка питомца")
    parser.add_argument("--age", type=float, help="возраст в годах")
    parser.add_argument("--weight", type=float, help="вес в килограммах")
    parser.add_argument("--male", action="store_true", help="кот")
    parser.add_argument("--female", action="store_true", help="кошка")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ветеринарный визуальный триаж кошек по фото и видео.",
    )
    subparsers = parser.add_subparsers(dest="command")

    photo = subparsers.add_parser("photo", help="разобрать фотографию")
    photo.add_argument("path")
    photo.add_argument("--sign", action="append", help="дополнительно подтвердить признак")
    add_patient_arguments(photo)
    photo.set_defaults(func=cmd_photo)

    video = subparsers.add_parser("video", help="разобрать короткое видео")
    video.add_argument("path")
    video.add_argument("--frames", type=int, default=8, help="сколько кадров извлечь")
    video.add_argument("--sign", action="append", help="дополнительно подтвердить признак")
    add_patient_arguments(video)
    video.set_defaults(func=cmd_video)

    signs = subparsers.add_parser("signs", help="показать признаки и их коды")
    signs.add_argument("--zone", help="фильтр по зоне тела")
    signs.set_defaults(func=cmd_signs)

    assess = subparsers.add_parser("assess", help="оценка по списку кодов признаков")
    assess.add_argument("signs", nargs="+")
    add_patient_arguments(assess)
    assess.set_defaults(func=cmd_assess)

    drug = subparsers.add_parser("drug", help="карточка препарата")
    drug.add_argument("code", nargs="?")
    drug.set_defaults(func=cmd_drug)

    toxic = subparsers.add_parser("toxic", help="опасные для кошек вещества")
    toxic.set_defaults(func=cmd_toxic)

    interactive = subparsers.add_parser("interactive", help="пошаговый опросник")
    add_patient_arguments(interactive)
    interactive.set_defaults(func=cmd_interactive)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
