"""Tests for license-plate ANPR: Russian plates, own/foreign DB, capture crop."""

import os
import tempfile

import pytest

from anpr.config import DEFAULTS, load_config, save_config
from anpr.database import AnprDB
from anpr.plates import (
    category_label,
    compact_alnum,
    extract_plates,
    format_plate,
    normalize_plate,
    parse_category,
    plate_is_valid,
)


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = AnprDB(db_path=path)
    yield db
    if os.path.exists(path):
        os.remove(path)


def test_normalize_cyrillic_plate():
    assert normalize_plate("А123ВС777") == "А123ВС777"
    assert plate_is_valid("А123ВС777")
    assert plate_is_valid("А123ВС77")
    assert not plate_is_valid("A123")


def test_normalize_latin_lookalikes():
    assert normalize_plate("A123BC777") == "А123ВС777"
    assert normalize_plate("a 123 bc 777") == "А123ВС777"
    assert normalize_plate("А123ВС-77") == "А123ВС77"


def test_slot_rules_fix_ocr_confusions():
    # O in digit slots -> 0; 0 in letter slots -> О
    assert normalize_plate("A123BC77O") == "А123ВС770"
    assert plate_is_valid(normalize_plate("A123BC770"))
    assert normalize_plate("0123BC777") == "О123ВС777"


def test_extract_plates_from_noisy_ocr():
    text = "камера 1  номер A123BC 777 въезд"
    plates = extract_plates(text)
    assert "А123ВС777" in plates


def test_format_and_labels():
    assert format_plate("А123ВС777") == "А123ВС 777"
    assert format_plate("А123ВС77") == "А123ВС 77"
    assert category_label("own") == "СВОЙ"
    assert category_label("foreign") == "ЧУЖОЙ"
    assert parse_category("свой") == "own"
    assert parse_category("чужой") == "foreign"


def test_compact_alnum_strips_junk():
    assert compact_alnum("№ А-123 ВС 777") == "А123ВС777"


def test_vehicle_own_foreign_and_unknown(temp_db):
    temp_db.add_vehicle("A123BC777", category="свой", owner_name="Моя машина")
    temp_db.add_vehicle("К999КК99", category="чужой", owner_name="Чужой авто")

    own = temp_db.classify("А123ВС777")
    assert own["category"] == "own"
    assert own["vehicle"]["owner_name"] == "Моя машина"

    foreign = temp_db.classify("К999КК99")
    assert foreign["category"] == "foreign"

    unknown = temp_db.classify("М001ММ77")
    assert unknown["category"] == "unknown"
    assert unknown["vehicle"] is None

    treated = temp_db.classify("М001ММ77", unknown_as_foreign=True)
    assert treated["category"] == "foreign"


def test_upsert_vehicle_by_plate(temp_db):
    first = temp_db.add_vehicle("А123ВС777", category="own", owner_name="Иван")
    second = temp_db.add_vehicle("A123BC777", category="foreign", owner_name="Пётр")
    assert first == second
    vehicle = temp_db.find_vehicle("а123вс777")
    assert vehicle["category"] == "foreign"
    assert vehicle["owner_name"] == "Пётр"


def test_events_and_duplicates(temp_db):
    temp_db.add_vehicle("А123ВС777", category="own")
    event_id = temp_db.log_event("А123ВС777", "own", confidence=0.9, source="test")
    assert event_id > 0
    assert temp_db.event_is_duplicate("A123BC777", window_sec=60)
    events = temp_db.get_events()
    assert events[0]["plate_normalized"] == "А123ВС777"
    stats = temp_db.stats()
    assert stats["own"] == 1
    assert stats["events"] == 1


def test_csv_roundtrip(temp_db):
    temp_db.add_vehicle("А111АА77", category="own", owner_name="Дом", notes="ворота")
    csv_text = temp_db.export_vehicles_csv()
    other_fd, other_path = tempfile.mkstemp(suffix=".db")
    os.close(other_fd)
    try:
        other = AnprDB(db_path=other_path)
        count = other.import_vehicles_csv(csv_text)
        assert count == 1
        found = other.find_vehicle("А111АА77")
        assert found["owner_name"] == "Дом"
        assert found["category"] == "own"
    finally:
        os.remove(other_path)


def test_config_roundtrip(tmp_path):
    path = str(tmp_path / "config.json")
    save_config({"interval_sec": 2.5, "source": "rtsp"}, path)
    loaded = load_config(path)
    assert loaded["interval_sec"] == 2.5
    assert loaded["source"] == "rtsp"
    assert loaded["rtsp_url"] == DEFAULTS["rtsp_url"]


def test_crop_roi():
    numpy = pytest.importorskip("numpy")
    from anpr.capture import crop_roi

    image = numpy.zeros((100, 200, 3), dtype=numpy.uint8)
    image[10:90, 20:180] = 255
    cropped = crop_roi(image, left=0.1, top=0.1, right=0.1, bottom=0.1)
    assert cropped.shape[0] == 80
    assert cropped.shape[1] == 160


def test_extract_from_recognizer_without_ocr():
    from anpr.recognizer import recognize_image

    numpy = pytest.importorskip("numpy")
    blank = numpy.zeros((240, 320, 3), dtype=numpy.uint8)
    assert recognize_image(blank) == []


def test_seetong_window_keywords():
    from anpr.capture import WindowInfo, find_seetong_window, list_windows

    info = WindowInfo(hwnd=1, title="Seetong PC Client", left=0, top=0, right=800, bottom=600)
    assert info.matches_seetong()
    assert not WindowInfo(1, "Notepad", 0, 0, 100, 100).matches_seetong()
    # On Linux CI there is no Win32 window list.
    assert list_windows() == []
    assert find_seetong_window() is None


def test_cli_add_and_list(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "anpr.db")
    monkeypatch.setattr("anpr.database.DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr("anpr.database.DATA_DIR", str(tmp_path))

    from anpr.__main__ import main

    # Re-bind AnprDB default by constructing with patched path via add command:
    # the CLI uses AnprDB() which reads DEFAULT_DB_PATH at call time.
    import anpr.database as database_mod

    monkeypatch.setattr(database_mod, "DEFAULT_DB_PATH", db_path)

    assert main(["add", "A123BC777", "--name", "Гараж", "--category", "свой"]) == 0
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "Гараж" in out
    assert "СВОЙ" in out
