"""Tests for license-plate ANPR: Russian plates, own/foreign DB, capture crop."""

import os
import tempfile

import pytest

from anpr.config import DEFAULTS, load_config, save_config, side_window_geometry
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


def test_camera_urls():
    from anpr.camera import build_http_url, build_rtsp_url

    http_url = build_http_url("192.168.0.123", "admin", "123456")
    assert http_url.startswith("http://admin:123456@192.168.0.123/")
    assert "snapshot.cgi" in http_url
    rtsp_url = build_rtsp_url("192.168.1.50", "admin", "123456")
    assert rtsp_url == "rtsp://admin:123456@192.168.1.50:554/mpeg4"


def test_overlay_text_is_not_a_plate():
    from anpr.plates import is_osd_text

    assert extract_plates("HD IPCAM 2880X1620") == []
    assert extract_plates("HDIPCAM 2560X1440") == []
    assert extract_plates("2560X1440") == []
    assert extract_plates("H001PC AM") == []
    assert extract_plates("2880X1 620") == []
    assert format_plate("2880X1620") == "—"
    assert not plate_is_valid(normalize_plate("HDIPCAM"))
    assert is_osd_text("HD IPCAM 2880X1620")
    assert is_osd_text("HDIPCAM 2560X1440")
    assert is_osd_text("2560 X 1440")
    assert extract_plates("C 292 HT 01") == ["С292НТ01"]
    # Sliding window must not invent М256ОХ144 from the resolution string.
    assert "М256ОХ144" not in extract_plates("НDIРСАМ2560Х1440")
    assert "М256ОХ144" not in extract_plates("HDIPCAM2560X1440")
    assert "А560ХН40" not in extract_plates("A560XH40 HDIPCAM")


def test_format_and_labels():
    assert format_plate("А123ВС777") == "А 123 ВС | 777"
    assert format_plate("А123ВС77") == "А 123 ВС | 77"
    assert format_plate("С292НТ01") == "С 292 НТ | 01"
    assert format_plate("А000АА00") == "А 000 АА | 00"
    assert category_label("own") == "СВОЙ"
    assert category_label("foreign") == "ЧУЖОЙ"
    assert parse_category("свой") == "own"
    assert parse_category("чужой") == "foreign"


def test_type1_split_ocr_parts():
    from anpr.plates import combine_type1_parts, type1_body, type1_region

    assert type1_body("А 000 АА") == "А000АА"
    assert type1_body("C292HT") == "С292НТ"
    assert type1_region("00 RUS") == "00"
    assert type1_region("01") == "01"
    assert type1_region("А 000 АА") == ""
    assert "С292НТ01" in combine_type1_parts(["С292НТ", "01"])
    assert "А000АА00" in combine_type1_parts(["А 000 АА", "00 RUS"])
    assert combine_type1_parts(["HD IPCAM", "2880"]) == []
    from anpr.plates import format_plate_parts

    assert format_plate_parts("С292НТ01") == ("С 292 НТ", "01")


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


def test_side_window_geometry_keeps_seetong_visible():
    assert side_window_geometry(1920, 1080, win_w=980, win_h=720, margin=16) == "980x720+924+64"
    assert side_window_geometry(800, 600, win_w=980, win_h=720, margin=16) == "768x568+16+16"


def test_sanitize_drops_leftover_extract_folders():
    from anpr.config import OFFICIAL_SEETONG_SHOTS_DIR, is_leftover_extract_path, sanitize_shots_dir

    leftover = r"D:\my_search_gpu_bot-cursor-anpr-seetong-plates-6b83\pi"
    assert is_leftover_extract_path(leftover)
    assert sanitize_shots_dir(leftover) == OFFICIAL_SEETONG_SHOTS_DIR
    assert sanitize_shots_dir("") == OFFICIAL_SEETONG_SHOTS_DIR
    assert sanitize_shots_dir(OFFICIAL_SEETONG_SHOTS_DIR) == OFFICIAL_SEETONG_SHOTS_DIR


def test_config_roundtrip(tmp_path):
    path = str(tmp_path / "config.json")
    save_config({"interval_sec": 2.5, "source": "rtsp"}, path)
    loaded = load_config(path)
    assert loaded["interval_sec"] == 2.5
    assert loaded["source"] == "rtsp"
    assert loaded["rtsp_url"] == DEFAULTS["rtsp_url"]


def test_newest_image_path(tmp_path):
    from anpr.capture import newest_image_path

    older = tmp_path / "old.jpg"
    newer = tmp_path / "new.jpg"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))
    assert newest_image_path(str(tmp_path)).endswith("new.jpg")


def test_newest_image_path_ignores_other_folders(tmp_path, monkeypatch):
    from anpr import capture
    from anpr.config import OFFICIAL_SEETONG_SHOTS_DIR

    monkeypatch.setenv("USERPROFILE", str(tmp_path / "nouser"))
    monkeypatch.setenv("HOME", str(tmp_path / "nouser"))
    missing = tmp_path / "missing-pi"
    other = tmp_path / "other-pi"
    other.mkdir()
    (other / "cam.jpg").write_bytes(b"x")
    with pytest.raises(RuntimeError) as exc:
        capture.newest_image_path(str(missing))
    assert "снимков" in str(exc.value)
    assert capture.seetong_shot_candidates(r"D:\my_search_gpu_bot-old\pi") == [OFFICIAL_SEETONG_SHOTS_DIR]


def test_seetong_shot_candidates_include_requested_folder():
    from anpr.capture import seetong_shot_candidates

    paths = seetong_shot_candidates(r"C:\Program Files (x86)\Seetong\pi")
    assert len(paths) == 1
    assert "seetong" in paths[0].lower()


def test_folder_source_falls_back_to_window(monkeypatch):
    from anpr.capture import WindowInfo, grab_frame

    class FakeFrame:
        size = 12

        def mean(self):
            return 80.0

    fake = FakeFrame()
    monkeypatch.setattr(
        "anpr.capture.grab_newest_in_folder",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("Нет папки снимков Seetong: C:\\x")),
    )
    monkeypatch.setattr(
        "anpr.capture.find_seetong_window",
        lambda *_a, **_k: WindowInfo(1, "Seetong Lite Client", 0, 0, 100, 80),
    )
    monkeypatch.setattr("anpr.capture.grab_window", lambda *_a, **_k: fake)
    frame, title = grab_frame("seetong_folder", shots_dir=r"C:\Program Files (x86)\Seetong\pi")
    assert frame is fake
    assert "Seetong" in title


def test_folder_and_window_failure_has_clear_hint(monkeypatch):
    from anpr.capture import grab_frame

    monkeypatch.setattr(
        "anpr.capture.grab_newest_in_folder",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("Нет папки снимков Seetong: C:\\x")),
    )
    monkeypatch.setattr("anpr.capture.find_seetong_window", lambda *_a, **_k: None)
    with pytest.raises(RuntimeError) as exc:
        grab_frame("seetong_folder", shots_dir=r"C:\Program Files (x86)\Seetong\pi")
    message = str(exc.value)
    assert "Нет папки снимков Seetong:" not in message
    assert "Main View" in message
    assert "фотоаппарата" in message


def test_crop_roi():
    numpy = pytest.importorskip("numpy")
    from anpr.capture import crop_roi

    image = numpy.zeros((100, 200, 3), dtype=numpy.uint8)
    image[10:90, 20:180] = 255
    cropped = crop_roi(image, left=0.1, top=0.1, right=0.1, bottom=0.1)
    assert cropped.shape[0] == 80
    assert cropped.shape[1] == 160


def test_crop_skips_distant_road():
    numpy = pytest.importorskip("numpy")
    from anpr.capture import crop_roi

    image = numpy.zeros((100, 100, 3), dtype=numpy.uint8)
    cropped = crop_roi(image, skip_top=0.3)
    assert cropped.shape[0] == 70
    assert cropped.shape[1] == 100


def test_mostly_black_frame():
    numpy = pytest.importorskip("numpy")
    from anpr.capture import _is_mostly_black, _is_useless_frame

    black = numpy.zeros((40, 40, 3), dtype=numpy.uint8)
    white = numpy.full((40, 40, 3), 200, dtype=numpy.uint8)
    green = numpy.zeros((40, 40, 3), dtype=numpy.uint8)
    green[:, :] = (40, 180, 40)
    noisy = numpy.random.randint(0, 255, (40, 40, 3), dtype=numpy.uint8)
    assert _is_mostly_black(black)
    assert not _is_mostly_black(white)
    assert _is_useless_frame(black)
    assert _is_useless_frame(green)
    assert not _is_useless_frame(noisy)


def test_mask_osd_keeps_center_plate():
    numpy = pytest.importorskip("numpy")
    from anpr.recognizer import mask_osd

    frame = numpy.full((240, 320, 3), 90, dtype=numpy.uint8)
    # White Type-1 plate in the lower-center bumper zone.
    frame[170:188, 110:210] = 230
    # Corner OSD badge.
    frame[220:238, 240:318] = 250
    masked = mask_osd(frame)
    assert int(masked[179, 160].mean()) > 200, "plate pixels must survive OSD wipe"
    assert int(masked[230, 280].mean()) == 0, "corner resolution badge must be wiped"


def test_extract_from_recognizer_without_ocr():
    from anpr.recognizer import recognize_image, recognize_scene

    numpy = pytest.importorskip("numpy")
    blank = numpy.zeros((240, 320, 3), dtype=numpy.uint8)
    assert recognize_image(blank) == []
    hits, vehicles, vis, zoom = recognize_scene(blank)
    assert hits == []
    assert vehicles == []
    assert vis is not None
    # Focus-band zoom may still be built so the side panel is never empty.


def test_vehicle_box_from_plate_and_downscale():
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.vehicles import downscale_for_anpr, vehicle_box_from_plate

    box = vehicle_box_from_plate((100, 140, 160, 160), (240, 320, 3))
    assert box[0] < 100 and box[2] > 160
    assert box[1] < 140 and box[3] >= 160
    big = numpy.zeros((1440, 2560, 3), dtype=numpy.uint8)
    small = downscale_for_anpr(big, max_w=1280)
    assert small.shape[1] == 1280
    assert small.shape[0] == 720


def test_direct_ocr_bbox_is_bound_to_exact_plate_region():
    numpy = pytest.importorskip("numpy")
    from anpr.recognizer import (
        PlateHit,
        _bind_hits_to_plate_regions,
        _plate_is_meaningful,
    )
    from anpr.vehicles import vehicle_box_from_plate

    image_shape = (400, 720, 3)
    exact = (310, 175, 380, 190)
    broad = (120, 100, 600, 280)
    hit = PlateHit(
        plate="А123ВС77",
        confidence=0.9,
        raw_text="A123BC77",
        bbox=broad,
        engine="test",
    )
    crop = numpy.zeros((15, 70, 3), dtype=numpy.uint8)
    result = _bind_hits_to_plate_regions([hit], [(exact, crop)], image_shape)
    assert result[0].bbox == exact, "recognized text must use the exact plate rectangle"

    car = vehicle_box_from_plate(exact, image_shape)
    assert car[2] - car[0] < 220, f"plate-derived car frame is too wide: {car}"
    assert car[0] < exact[0] and car[2] > exact[2]
    assert car[1] < exact[1] and car[3] > exact[3]
    assert not _plate_is_meaningful("А000АА00")
    assert not _plate_is_meaningful("А000АА77")
    assert _plate_is_meaningful("А123ВС77")


def test_plate_region_keeps_exact_box_but_expands_ocr_context(monkeypatch):
    numpy = pytest.importorskip("numpy")
    from anpr import recognizer

    frame = numpy.zeros((120, 240, 3), dtype=numpy.uint8)
    exact = (90, 70, 150, 82)
    monkeypatch.setattr(
        recognizer, "_iter_search_views", lambda image, origin, inside: [((0, 0), image)]
    )
    monkeypatch.setattr(
        recognizer,
        "find_plate_regions",
        lambda view, max_candidates=3: [(exact, view[70:82, 90:150])],
    )

    regions = recognizer._collect_plate_regions(frame)
    assert regions[0][0] == exact
    assert regions[0][1].shape[0] > 12
    assert regions[0][1].shape[1] > 60


def test_tiny_plate_ocr_retries_high_contrast_view(monkeypatch):
    numpy = pytest.importorskip("numpy")
    from anpr import recognizer

    crop = numpy.full((10, 55, 3), 180, dtype=numpy.uint8)
    calls = []

    def fake_run(view):
        calls.append(view)
        return ("test", [("не номер", 0.9)]) if len(calls) == 1 else (
            "test",
            [("А123ВС77", 0.91)],
        )

    monkeypatch.setattr(recognizer, "_run_ocr", fake_run)
    hits = recognizer._ocr_regions([((10, 20, 65, 30), crop)], 0.3)
    assert len(calls) == 2
    assert hits and hits[0].plate == "А123ВС77"


def test_recognized_plate_trims_car_box_glued_to_bins():
    from anpr.recognizer import (
        PlateHit,
        _tighten_silhouettes_to_recognized_plates,
    )
    from anpr.vehicles import VehicleSilhouette

    plate = PlateHit(
        plate="У120НО05",
        confidence=0.9,
        raw_text="У120НО05",
        bbox=(220, 200, 280, 215),
        engine="test",
    )
    glued = VehicleSilhouette(box=(100, 50, 560, 250), contour=None, score=0.8)
    result = _tighten_silhouettes_to_recognized_plates(
        [glued], [plate], (400, 720, 3)
    )
    assert len(result) == 1
    assert result[0].box[1:] != glued.box[1:]
    assert result[0].box[2] < 400, "right-side bins must be outside the car frame"
    assert result[0].box[0] < 220 < result[0].box[2]
    assert result[0].box[1] == glued.box[1]
    assert result[0].box[3] == glued.box[3]


def test_recognize_scene_draws_frame_without_silhouette(monkeypatch):
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr import recognizer
    from anpr.recognizer import PlateHit, recognize_scene

    frame = numpy.full((240, 320, 3), 95, dtype=numpy.uint8)
    frame[170:190, 120:200] = 230

    def fake_ocr_crop(crop, origin_box, min_confidence):
        return [
            PlateHit(
                plate="К900НН03",
                confidence=0.9,
                raw_text="K900HH03",
                bbox=(120, 170, 200, 190),
                engine="test",
            )
        ]

    monkeypatch.setattr(recognizer, "_ocr_crop_direct", fake_ocr_crop)
    monkeypatch.setattr("anpr.vehicles.find_vehicle_silhouettes", lambda *a, **k: [])
    hits, vehicles, annotated, zoom = recognize_scene(frame, min_confidence=0.1)
    assert hits and hits[0].plate == "К900НН03"
    assert vehicles, "plate-based car frame must be created"
    assert zoom is not None
    assert annotated is not None
    assert int(abs(annotated.astype("int16") - frame.astype("int16")).mean()) > 0


def test_upper_parking_row_plate_search_drives_frame_and_ocr(monkeypatch):
    """A missed silhouette must not hide plates in the real upper car row."""
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr import recognizer
    from anpr.recognizer import PlateHit, plate_focus_band, parking_band, recognize_scene

    frame = numpy.full((400, 720, 3), 105, dtype=numpy.uint8)
    frame[80:220, 250:430] = (38, 40, 45)
    frame[190:208, 305:390] = 225
    frame[194:204, 320:324] = 25
    frame[194:204, 340:344] = 25
    frame[194:204, 360:364] = 25
    frame[240:390, :] = (190, 195, 200)  # puddle below the parked car

    focus_box, _focus = plate_focus_band(frame)
    parking_box, _parking = parking_band(frame)
    assert focus_box[1] < 80 and focus_box[3] < 280
    assert parking_box[1] < 80 and parking_box[3] < 280

    plate_box = (305, 190, 390, 208)
    monkeypatch.setattr("anpr.vehicles.find_vehicle_silhouettes", lambda *a, **k: [])
    monkeypatch.setattr(
        recognizer,
        "_collect_plate_regions",
        lambda *a, **k: [(plate_box, frame[190:208, 305:390])],
    )
    monkeypatch.setattr(
        recognizer,
        "_ocr_regions",
        lambda *a, **k: [
            PlateHit(
                plate="А123ВС77",
                confidence=0.92,
                raw_text="A123BC77",
                bbox=plate_box,
                engine="test",
            )
        ],
    )

    hits, vehicles, annotated, zoom = recognize_scene(frame, min_confidence=0.1)
    assert hits and hits[0].plate == "А123ВС77"
    assert vehicles, "plate proposal must create a car frame without a silhouette"
    assert vehicles[0][3] < int(frame.shape[0] * 0.70), "frame must stay above puddle"
    assert annotated is not None
    assert zoom is not None


def test_annotate_scene_draws_shape_and_frame():
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.vehicles import VehicleSilhouette, annotate_scene, draw_corner_frame, draw_vehicle_shape

    frame = numpy.full((240, 320, 3), 90, dtype=numpy.uint8)
    frame[120:200, 80:240] = (40, 42, 48)
    silhouette = VehicleSilhouette(box=(80, 120, 240, 200), contour=None, score=1.0)
    annotated = annotate_scene(frame, [silhouette], [])
    assert annotated is not None
    assert annotated.shape == frame.shape
    # Tight blue reference frame: B channel dominates on the box edge.
    corner = annotated[120, 80]
    assert int(corner[0]) > int(corner[1])  # B > G for azure frame
    draw_corner_frame(frame.copy(), (10, 10, 100, 80))
    draw_vehicle_shape(frame.copy(), silhouette, label="АВТО")


def test_light_and_dark_cars_get_frame():
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.vehicles import find_vehicle_silhouettes

    asphalt = numpy.full((240, 320, 3), 105, dtype=numpy.uint8)

    dark = asphalt.copy()
    dark[110:200, 60:250] = (28, 30, 32)
    dark[120:155, 90:220] = (55, 58, 60)
    dark_cars = find_vehicle_silhouettes(dark, max_cars=3)
    assert dark_cars, "dark car on asphalt must get a frame"

    light = asphalt.copy()
    light[110:200, 60:250] = (210, 212, 215)
    light[120:155, 90:220] = (185, 188, 190)
    light_cars = find_vehicle_silhouettes(light, max_cars=3)
    assert light_cars, "white/silver car on asphalt must get a frame"


def test_wet_lot_finds_silver_and_dark_cars_separately():
    """Regression: wet asphalt texture used to yield 0 cars / one giant blob."""
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.vehicles import find_vehicle_silhouettes

    rs = numpy.random.RandomState(1)
    frame = numpy.full((400, 720, 3), 110, dtype=numpy.uint8)
    frame = numpy.clip(frame.astype(numpy.int16) + rs.randint(-25, 25, frame.shape), 0, 255).astype(
        numpy.uint8
    )
    # Silver SUV left
    frame[150:290, 50:260] = (145, 148, 152)
    frame[165:210, 80:230] = (120, 125, 130)
    # Dark sedan right
    frame[160:300, 320:560] = (35, 36, 40)
    frame[180:230, 360:520] = (55, 58, 60)

    cars = find_vehicle_silhouettes(frame, max_cars=5)
    assert len(cars) >= 2, f"expected silver + dark, got {cars}"
    centers = sorted((c.box[0] + c.box[2]) / 2 for c in cars)
    assert centers[0] < 250, "silver SUV should be on the left"
    assert centers[-1] > 350, "dark sedan should be on the right"


def test_packed_parking_row_finds_multiple_cars():
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.vehicles import find_vehicle_silhouettes

    h, w = 400, 720
    frame = numpy.full((h, w, 3), 130, dtype=numpy.uint8)
    frame[300:400, :] = (70, 72, 75)
    colors = [
        (210, 210, 210),
        (170, 170, 175),
        (230, 230, 230),
        (40, 45, 90),
        (25, 25, 28),
        (220, 220, 225),
        (35, 38, 42),
        (200, 200, 205),
    ]
    x = 15
    for color in colors:
        bw, bh = 82, 70
        y0 = 160
        frame[y0 : y0 + bh, x : x + bw] = color
        frame[y0 + 8 : y0 + 28, x + 8 : x + bw - 8] = tuple(max(0, v - 25) for v in color)
        frame[y0 + bh : y0 + bh + 25, x : x + bw] = (55, 55, 55)
        x += bw + 6
    cars = find_vehicle_silhouettes(frame, max_cars=6)
    assert len(cars) >= 3, f"packed row must yield multiple car frames, got {cars}"
    for car in cars:
        bw = car.box[2] - car.box[0]
        bh = car.box[3] - car.box[1]
        assert bw < w * 0.28, f"must not frame a car group as one car: {car.box}"
        assert bw < 200, f"box too wide for one packed-row car: {car.box}"
        # Frame must hug the body — not stretch deep into asphalt/puddles.
        assert bh <= int(bw * 1.25) + 12, f"box too tall vs car width: {car.box}"
        assert car.box[3] < 280, f"box extends too far into foreground: {car.box}"
    centers = sorted((c.box[0] + c.box[2]) / 2 for c in cars)
    assert centers[-1] - centers[0] > w * 0.35, f"cars should span the row, centers={centers}"


def test_dark_and_white_pair_get_separate_tight_frames():
    """Regression: black+white neighbours must not share one tall group box."""
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.vehicles import find_vehicle_silhouettes

    frame = numpy.full((400, 720, 3), 120, dtype=numpy.uint8)
    frame[300:400, :] = (60, 62, 65)
    frame[150:270, 200:340] = (30, 32, 35)
    frame[165:220, 220:320] = (50, 52, 55)
    frame[150:270, 350:500] = (210, 212, 215)
    frame[165:220, 370:480] = (180, 182, 185)
    frame[270:295, 200:500] = (45, 45, 48)
    cars = find_vehicle_silhouettes(frame, max_cars=4)
    assert len(cars) >= 2, f"expected separate dark+white frames, got {cars}"
    for car in cars:
        bw = car.box[2] - car.box[0]
        bh = car.box[3] - car.box[1]
        assert bw < 220, f"pair must not stay glued: {car.box}"
        assert bh <= int(bw * 1.35) + 16, f"frame must hug car body: {car.box}"
    centers = sorted((c.box[0] + c.box[2]) / 2 for c in cars)
    assert centers[0] < 320 < centers[-1]


def test_wet_puddle_alone_is_not_a_car():
    """Regression: АВТО must not frame a bright puddle with no car body."""
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.vehicles import find_vehicle_silhouettes

    h, w = 400, 640
    frame = numpy.full((h, w, 3), 110, dtype=numpy.uint8)
    # Bright wet sheet on the right — the false АВТО from operator screenshots.
    frame[220:380, 380:620] = (195, 200, 205)
    frame[250:360, 400:600] = (210, 215, 220)
    assert find_vehicle_silhouettes(frame, max_cars=5) == []

    # Same puddle plus a real dark car on the left — only the car remains.
    frame[140:250, 60:220] = (35, 38, 42)
    frame[155:195, 85:195] = (60, 62, 68)
    cars = find_vehicle_silhouettes(frame, max_cars=5)
    assert cars, "real car must still be found beside the puddle"
    cx = (cars[0].box[0] + cars[0].box[2]) / 2
    assert cx < 280, f"top detection should be the car, not the puddle: {cars[0].box}"
    assert cars[0].box[3] < int(h * 0.72)


def test_wet_reflections_do_not_inflate_or_glue_cars():
    """Regression: puddle glare must not become tall multi-car frames."""
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.vehicles import find_vehicle_silhouettes

    h, w = 480, 800
    frame = numpy.full((h, w, 3), 115, dtype=numpy.uint8)
    frame[340:460, 50:750] = (200, 205, 210)
    tones = [
        (200, 200, 205),
        (35, 38, 42),
        (220, 220, 225),
        (30, 32, 36),
        (180, 185, 190),
        (45, 48, 55),
    ]
    x = 40
    for col in tones:
        y0 = 200
        frame[y0 : y0 + 95, x : x + 95] = col
        frame[y0 + 100 : y0 + 160, x : x + 95] = tuple(min(255, v + 20) for v in col)
        x += 110
    cars = find_vehicle_silhouettes(frame, max_cars=6)
    assert len(cars) >= 3, f"expected several cars above the puddle, got {cars}"
    for car in cars:
        bw = car.box[2] - car.box[0]
        bh = car.box[3] - car.box[1]
        assert bw < w * 0.28, f"must not glue cars via reflections: {car.box}"
        assert car.box[3] < int(h * 0.70), f"frame must not dive into puddle: {car.box}"
        assert bh <= int(bw * 1.35) + 16, f"frame must hug car body: {car.box}"
        assert (car.box[1] + car.box[3]) / 2 < h * 0.62


def test_night_scene_zoom_shows_bumper_when_plate_unread(monkeypatch):
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr import recognizer
    from anpr.recognizer import recognize_scene
    from anpr.vehicles import VehicleSilhouette

    frame = numpy.full((360, 640, 3), 25, dtype=numpy.uint8)
    frame[140:280, 160:480] = (18, 18, 20)
    frame[250:270, 260:400] = (200, 200, 200)  # white plate on dark bumper

    monkeypatch.setattr(
        "anpr.vehicles.find_vehicle_silhouettes",
        lambda *a, **k: [VehicleSilhouette(box=(160, 140, 480, 280), contour=None, score=1.0)],
    )
    monkeypatch.setattr(recognizer, "_ocr_crop_direct", lambda *a, **k: [])
    monkeypatch.setattr(recognizer, "_ocr_regions", lambda *a, **k: [])
    monkeypatch.setattr(recognizer, "_collect_plate_regions", lambda *a, **k: [])
    hits, vehicles, annotated, zoom = recognize_scene(frame, min_confidence=0.1)
    assert not hits
    assert vehicles
    assert zoom is not None
    assert float(zoom.mean()) > 30.0


def test_recognize_scene_keeps_detection_frame_on_preview():
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.recognizer import recognize_scene

    frame = numpy.full((240, 320, 3), 95, dtype=numpy.uint8)
    frame[0:40, :] = 200
    frame[120:200, 70:250] = (35, 38, 42)
    frame[128:155, 95:225] = (70, 72, 78)
    frame[178:194, 110:210] = 230  # plate-like band on bumper
    hits, vehicles, annotated, zoom = recognize_scene(frame, min_confidence=0.1)
    assert vehicles, "car silhouette should be detected"
    assert annotated is not None
    assert annotated.shape == frame.shape, "preview must keep full scene with shape/frame, not only zoom crop"
    assert zoom is not None
    assert int(abs(annotated.astype("int16") - frame.astype("int16")).mean()) > 0


def test_find_vehicle_silhouette_on_parking_lot():
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.vehicles import apply_silhouette_mask, cut_away_background, find_vehicle_rois, find_vehicle_silhouettes

    frame = numpy.full((240, 320, 3), 95, dtype=numpy.uint8)
    frame[0:40, :] = 200  # sky / OSD
    frame[120:200, 70:250] = (35, 38, 42)  # dark car
    frame[128:155, 95:225] = (70, 72, 78)  # windshield
    boxes = find_vehicle_rois(frame)
    assert boxes, "car blob on asphalt should be found"
    x0, y0, x1, y1 = boxes[0]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    assert 70 < cx < 250
    assert 120 < cy < 210
    silhouettes = find_vehicle_silhouettes(frame)
    assert silhouettes and silhouettes[0].contour is not None
    masked = apply_silhouette_mask(frame, silhouettes)
    assert int(masked[10, 160].mean()) == 0  # sky / OSD cut away
    assert int(masked[160, 160].mean()) > 20  # car kept
    cut = cut_away_background(frame, silhouettes)
    assert cut.shape[0] < frame.shape[0] or cut.shape[1] < frame.shape[1]


def test_dumpsters_are_not_marked_as_cars():
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.vehicles import find_vehicle_silhouettes

    frame = numpy.full((240, 320, 3), 110, dtype=numpy.uint8)
    # Blue / yellow / green garbage bins — must not become АВТО.
    frame[100:185, 250:305] = (210, 90, 35)
    frame[100:185, 190:240] = (35, 210, 230)
    frame[95:175, 130:175] = (40, 180, 60)
    assert find_vehicle_silhouettes(frame, max_cars=5) == []

    # Same bins plus a dark car on the left — only the car should remain.
    frame[115:195, 20:115] = (40, 42, 48)
    frame[125:150, 35:100] = (70, 72, 78)
    cars = find_vehicle_silhouettes(frame, max_cars=5)
    assert cars, "real car must still be found"
    cx = (cars[0].box[0] + cars[0].box[2]) / 2
    assert cx < 160, "top detection should be the car, not the bins"

    # Close-up blue + green plastic bins can be car-sized in the camera crop.
    large = numpy.full((360, 640, 3), 105, dtype=numpy.uint8)
    large[115:285, 330:470] = (215, 125, 35)  # blue plastic
    large[120:290, 475:600] = (45, 175, 65)  # green plastic
    assert find_vehicle_silhouettes(large, max_cars=5) == []


def test_wide_textured_asphalt_is_not_marked_as_car():
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.vehicles import _is_non_vehicle, find_vehicle_silhouettes

    rs = numpy.random.RandomState(23)
    frame = numpy.full((400, 720, 3), 72, dtype=numpy.uint8)
    asphalt = rs.randint(65, 175, (100, 350, 1), dtype=numpy.uint8)
    frame[140:240, 180:530] = numpy.repeat(asphalt, 3, axis=2)
    bad_box = (180, 140, 530, 240)

    assert _is_non_vehicle(frame, bad_box), "wide shallow asphalt sheet is not a car"
    cars = find_vehicle_silhouettes(frame, max_cars=5)
    assert all(car.box != bad_box for car in cars)
    assert all(
        (car.box[2] - car.box[0]) / max(1, car.box[3] - car.box[1]) < 3.05
        for car in cars
    )


def test_hdipcam_osd_is_not_marked_as_car():
    """Regression: HDIPCAM 2560X1440 was framed as АВТО and the lot went black."""
    numpy = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")
    from anpr.vehicles import annotate_scene, find_vehicle_silhouettes

    frame = numpy.full((360, 640, 3), 28, dtype=numpy.uint8)
    # Bright OSD badge bottom-right — looks like a pale blob to the FG mask.
    cv2.putText(
        frame,
        "HDIPCAM 2560X1440",
        (360, 340),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (240, 240, 240),
        2,
    )
    assert find_vehicle_silhouettes(frame, max_cars=5) == []

    # Even if a bad box is passed in, annotate must not black out the scene.
    annotated = annotate_scene(frame, [(380, 300, 620, 350)], [])
    assert float(annotated.mean()) > 15.0


def test_type1_plate_region_aspect():
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.recognizer import find_plate_regions

    frame = numpy.full((120, 200, 3), 80, dtype=numpy.uint8)
    # White Type-1 plate ~4.6–5.5 aspect inside a car-like crop
    frame[74:92, 48:148] = 230
    regions = find_plate_regions(frame)
    assert regions, "white Type-1 rectangle should be a plate candidate"
    (x0, y0, x1, y1), _crop = regions[0]
    aspect = (x1 - x0) / float(max(y1 - y0, 1))
    assert 2.5 <= aspect <= 8.5


def test_seetong_window_keywords():
    from anpr.capture import WindowInfo, find_seetong_window, list_windows

    info = WindowInfo(hwnd=1, title="Seetong Lite Client", left=0, top=0, right=800, bottom=600)
    assert info.matches_seetong()
    assert info.is_lite_client()
    assert WindowInfo(1, "Seetong PC Client", 0, 0, 800, 600).matches_seetong()
    assert not WindowInfo(1, "Notepad", 0, 0, 100, 100).matches_seetong()
    # On Linux CI there is no Win32 window list.
    assert list_windows() == []
    assert find_seetong_window() is None


def test_cli_add_and_list(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "anpr.db")
    monkeypatch.setattr("anpr.database.DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr("anpr.database.DATA_DIR", str(tmp_path))

    from anpr.__main__ import main

    assert main(["add", "A123BC777", "--name", "Гараж", "--category", "свой"]) == 0
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "Гараж" in out
    assert "СВОЙ" in out


def test_user_type1_sample_plates():
    from anpr.plates import combine_type1_parts, extract_plates, format_plate, normalize_plate, plate_is_valid
    from anpr.type1_samples import TYPE1_SAMPLES

    assert TYPE1_SAMPLES
    for raw, compact, shown in TYPE1_SAMPLES:
        assert plate_is_valid(compact), compact
        assert compact in extract_plates(raw), raw
        assert normalize_plate(raw) == compact or compact in extract_plates(raw)
        assert format_plate(compact) == shown
        body, region = shown.split(" | ")
        assert compact in combine_type1_parts([body, f"{region} RUS"])


def test_oo_are_letters_not_zeros():
    from anpr.plates import format_plate, normalize_plate

    # «E 441 OO 61» — OO in letter slots are О, not 0
    assert normalize_plate("E441OO61") == "Е441ОО61"
    assert format_plate("E441OO61") == "Е 441 ОО | 61"
    assert normalize_plate("E4410061") == "Е441ОО61"


def test_three_digit_region_799():
    from anpr.plates import format_plate, extract_plates

    assert extract_plates("H 778 EM 799 RUS") == ["Н778ЕМ799"]
    assert format_plate("Н778ЕМ799") == "Н 778 ЕМ | 799"


def test_rendered_type1_plate_on_car_silhouette():
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.recognizer import find_plate_regions
    from anpr.type1_render import scene_with_car_and_plate
    from anpr.vehicles import apply_silhouette_mask, find_vehicle_silhouettes

    frame = scene_with_car_and_plate("Е999КХ70")
    silhouettes = find_vehicle_silhouettes(frame)
    assert silhouettes, "car under the sample plate should be found"
    masked = apply_silhouette_mask(frame, silhouettes)
    assert int(masked[10, 240].mean()) == 0
    crop = masked[silhouettes[0].box[1] : silhouettes[0].box[3], silhouettes[0].box[0] : silhouettes[0].box[2]]
    regions = find_plate_regions(crop)
    assert regions, "Type-1 plate on the bumper should be a candidate"


def test_zoom_box_enlarges_plate():
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.vehicles import zoom_box

    frame = numpy.full((200, 300, 3), 40, dtype=numpy.uint8)
    frame[80:100, 40:160] = 220
    zoomed = zoom_box(frame, (40, 80, 160, 100))
    assert zoomed.shape[1] > 160
    assert zoomed.shape[0] > 20


def test_rtsp_session_reuses_open_capture(monkeypatch):
    """Regression: opening RTSP every tick made wall-clock ~10s while OCR showed ~1s."""
    numpy = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")
    from anpr import capture as capture_mod

    opens = {"n": 0}

    class FakeCap:
        def __init__(self, url, *args, **kwargs):
            opens["n"] += 1
            self.url = url

        def isOpened(self):
            return True

        def set(self, *_a, **_k):
            return True

        def grab(self):
            return True

        def retrieve(self):
            return True, numpy.zeros((40, 60, 3), dtype=numpy.uint8)

        def read(self):
            return True, numpy.zeros((40, 60, 3), dtype=numpy.uint8)

        def release(self):
            return None

    monkeypatch.setattr(cv2, "VideoCapture", FakeCap)
    capture_mod.release_rtsp()
    frame1 = capture_mod.grab_rtsp("rtsp://cam/test")
    frame2 = capture_mod.grab_rtsp("rtsp://cam/test")
    assert frame1 is not None and frame2 is not None
    assert opens["n"] == 1
    capture_mod.release_rtsp()
    frame3 = capture_mod.grab_rtsp("rtsp://cam/test")
    assert frame3 is not None
    assert opens["n"] == 2
    capture_mod.release_rtsp()


def test_annotate_zoom_plate_is_bright_and_large():
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from anpr.recognizer import PlateHit
    from anpr.vehicles import annotate_zoom

    frame = numpy.full((360, 640, 3), 35, dtype=numpy.uint8)
    frame[220:250, 240:420] = (230, 230, 230)
    hit = PlateHit(
        plate="К900НН93",
        confidence=0.8,
        raw_text="К900НН93",
        bbox=(240, 220, 420, 250),
        engine="test",
    )
    zoom = annotate_zoom(frame, hit.bbox, [], [hit])
    assert zoom is not None
    assert zoom.shape[1] >= 900
    assert float(zoom.mean()) > 40.0

