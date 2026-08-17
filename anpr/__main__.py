"""CLI: one-shot capture, plate lookup, and vehicle list management."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Распознавание автономеров с окна Seetong / RTSP и база Свой/Чужой"
    )
    sub = parser.add_subparsers(dest="command")

    once = sub.add_parser("once", help="Сделать один скриншот и попытаться распознать номер")
    once.add_argument("--source", default="seetong_window", choices=["seetong_window", "monitor", "rtsp", "http", "file"])
    once.add_argument("--window", default="", help="Часть заголовка окна Seetong")
    once.add_argument("--rtsp", default="")
    once.add_argument("--http", default="")
    once.add_argument("--file", dest="file_path", default="")
    once.add_argument("--save", action="store_true", help="Сохранить скриншот в anpr_data/shots")

    add = sub.add_parser("add", help="Добавить номер в базу")
    add.add_argument("plate")
    add.add_argument("--name", default="")
    add.add_argument("--category", default="own", choices=["own", "foreign", "свой", "чужой"])
    add.add_argument("--notes", default="")

    sub.add_parser("list", help="Показать базу Свой/Чужой")
    sub.add_parser("gui", help="Открыть графическую программу")
    return parser


def cmd_once(args: argparse.Namespace) -> int:
    from anpr.capture import crop_roi, grab_frame, save_screenshot
    from anpr.config import load_config
    from anpr.database import AnprDB
    from anpr.plates import category_label, format_plate
    from anpr.recognizer import available_engines, recognize_image

    cfg = load_config()
    try:
        frame, source_name = grab_frame(
            source=args.source,
            window_title=args.window or cfg.get("window_title", ""),
            rtsp_url=args.rtsp or cfg.get("rtsp_url", ""),
            http_url=args.http or cfg.get("http_url", ""),
            file_path=args.file_path or cfg.get("file_path", ""),
        )
    except Exception as exc:
        print(f"Ошибка захвата: {exc}", file=sys.stderr)
        return 1

    frame = crop_roi(
        frame,
        left=cfg.get("crop_left", 0),
        top=cfg.get("crop_top", 0),
        right=cfg.get("crop_right", 0),
        bottom=cfg.get("crop_bottom", 0),
        skip_top=cfg.get("skip_top", 0),
    )
    shot = save_screenshot(frame, prefix="once") if args.save else ""
    engines = available_engines()
    print(f"Источник: {source_name}")
    print(f"OCR: {', '.join(engines) if engines else 'нет (установите rapidocr-onnxruntime или easyocr)'}")
    hits = recognize_image(frame, min_confidence=float(cfg.get("min_confidence", 0.4)))
    db = AnprDB()
    if not hits:
        print("Номер не распознан. Можно открыть GUI и ввести номер вручную по скриншоту.")
        if shot:
            print(f"Скриншот: {shot}")
        return 2
    for hit in hits:
        info = db.classify(hit.plate, unknown_as_foreign=bool(cfg.get("unknown_as_foreign")))
        owner = info["vehicle"]["owner_name"] if info["vehicle"] else "—"
        print(
            f"{format_plate(hit.plate)}  [{info['label']}]  "
            f"уверенность {hit.confidence:.0%}  OCR={hit.engine}  владелец={owner}"
        )
    if shot:
        print(f"Скриншот: {shot}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    from anpr.database import AnprDB
    from anpr.plates import parse_category

    db = AnprDB()
    vehicle_id = db.add_vehicle(
        plate=args.plate,
        category=parse_category(args.category),
        owner_name=args.name,
        notes=args.notes,
    )
    print(f"Сохранено id={vehicle_id}")
    return 0


def cmd_list() -> int:
    from anpr.database import AnprDB
    from anpr.plates import category_label, format_plate

    db = AnprDB()
    rows = db.get_vehicles()
    if not rows:
        print("База пустая. Добавьте номера: python -m anpr add А123ВС777 --name 'Моя машина'")
        return 0
    for row in rows:
        print(
            f"{row['id']:4}  {format_plate(row['plate_normalized']):16}  "
            f"{category_label(row['category']):12}  {row['owner_name'] or '—'}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "once":
        return cmd_once(args)
    if args.command == "add":
        return cmd_add(args)
    if args.command == "list":
        return cmd_list()
    if args.command == "gui" or args.command is None:
        from anpr_gui import main as gui_main

        gui_main()
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
