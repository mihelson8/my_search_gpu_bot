"""
Visual analysis of cat photos and short video frames.

Модуль решает две задачи:
1. Контроль качества медиа: слишком тёмное, размытое или мелкое изображение
   бесполезно для оценки, и об этом лучше сказать сразу.
2. Извлечение цветовых и текстурных подсказок (cues), которые сопоставляются
   с кодами визуальных признаков из базы знаний.

Эвристики дают только предварительные подсказки низкой уверенности: финальное
решение принимает владелец, подтверждая признаки, и затем ветеринарный врач.
Для подключения обученной модели (ViT, EfficientNet, ONNX) предусмотрен
интерфейс SignClassifier и функция set_classifier.
"""

from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Sequence, Tuple

logger = logging.getLogger(__name__)

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - зависит от окружения
    PIL_AVAILABLE = False


COLOR_GRID = 4
GRAY_SIZE = 96
SHARPNESS_CROP = 192
MIN_USEFUL_SIDE = 200
DARK_THRESHOLD = 0.20
BRIGHT_THRESHOLD = 0.92
BLUR_THRESHOLD = 0.010


@dataclass
class ImageQuality:
    width: int
    height: int
    brightness: float
    sharpness: float
    problems: List[str] = field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        return not self.problems

    @property
    def summary(self) -> str:
        if self.is_usable:
            return "Качество кадра достаточное для предварительной оценки."
        return "Качество кадра ограничивает оценку: " + "; ".join(self.problems) + "."


@dataclass
class VisualCue:
    """Предварительная визуальная подсказка, требующая подтверждения владельцем."""

    code: str
    label: str
    confidence: float
    suggested_signs: List[str]
    explanation: str

    @property
    def confidence_percent(self) -> int:
        return int(round(max(0.0, min(1.0, self.confidence)) * 100))


@dataclass
class MotionMetrics:
    """Метрики движения по последовательности кадров короткого видео."""

    frames: int
    mean_motion: float
    peak_motion: float
    periodicity: float


@dataclass
class MediaAnalysis:
    kind: str
    frames_analyzed: int
    quality: Optional[ImageQuality]
    cues: List[VisualCue] = field(default_factory=list)
    motion: Optional[MotionMetrics] = None
    notes: List[str] = field(default_factory=list)

    @property
    def suggested_signs(self) -> List[str]:
        ordered: List[str] = []
        for cue in sorted(self.cues, key=lambda c: c.confidence, reverse=True):
            for sign_code in cue.suggested_signs:
                if sign_code not in ordered:
                    ordered.append(sign_code)
        return ordered


class SignClassifier(Protocol):
    """Интерфейс для подключения обученной модели классификации признаков."""

    def predict(self, image_bytes: bytes) -> Sequence[Tuple[str, float]]:
        """Возвращает пары (код признака, уверенность 0..1)."""


_classifier: Optional[SignClassifier] = None


def set_classifier(classifier: Optional[SignClassifier]) -> None:
    """Подключает или отключает внешнюю модель классификации признаков."""
    global _classifier
    _classifier = classifier


def get_classifier() -> Optional[SignClassifier]:
    return _classifier


CUE_LIBRARY: Dict[str, Tuple[str, List[str], str]] = {
    "redness": (
        "Выраженное покраснение на участке кадра",
        ["eye_redness", "ear_redness_swelling", "mouth_gum_redness", "skin_wound_swelling"],
        "В кадре есть зона с сильным преобладанием красного канала.",
    ),
    "yellow_tint": (
        "Желтоватый оттенок тканей",
        ["mucosa_yellow"],
        "Найдена зона с жёлтым сдвигом цвета, это может быть желтушность или тёплый свет лампы.",
    ),
    "pallor": (
        "Бледная, слабо насыщенная слизистая",
        ["mouth_pale_gums", "dehydration"],
        "Светлая зона с низкой насыщенностью цвета, возможна бледность слизистых.",
    ),
    "dark_debris": (
        "Тёмный налёт или крупинки",
        ["ear_dark_debris", "skin_black_specks"],
        "Найдены тёмно-коричневые скопления, характерные для ушного налёта или следов блох.",
    ),
    "bare_skin_patch": (
        "Участок кожи без шерсти",
        ["skin_hair_loss_patch", "skin_scaling_crust"],
        "Зона с ровной текстурой и телесным оттенком, похоже на залысину.",
    ),
    "discharge": (
        "Светлые густые выделения",
        ["eye_discharge", "nose_discharge"],
        "Небольшая яркая зона с жёлто-зелёным сдвигом, похожая на выделения.",
    ),
    "low_activity": (
        "Очень низкая активность на видео",
        ["neuro_hiding"],
        "Кошка почти не двигается в кадре, это может быть сном или вялостью.",
    ),
    "repetitive_motion": (
        "Повторяющиеся однотипные движения",
        ["ear_head_shaking", "skin_itching"],
        "В видео заметны ритмичные движения, характерные для тряски головой или расчёсывания.",
    ),
    "unstable_gait": (
        "Неровное, рывками движение",
        ["neuro_ataxia", "limping"],
        "Движение в кадре неравномерное, стоит показать врачу видео походки.",
    ),
}


def _make_cue(code: str, confidence: float) -> VisualCue:
    label, signs, explanation = CUE_LIBRARY[code]
    return VisualCue(
        code=code,
        label=label,
        confidence=round(max(0.0, min(1.0, confidence)), 3),
        suggested_signs=list(signs),
        explanation=explanation,
    )


def _pixels(image) -> List:
    """Плоский список пикселей с поддержкой старых и новых версий Pillow."""
    getter = getattr(image, "get_flattened_data", None)
    if callable(getter):
        return list(getter())
    return list(image.getdata())


def _cell_stats(pixels: Sequence[Tuple[int, int, int]]) -> Dict[str, float]:
    count = len(pixels)
    if count == 0:
        return {"r": 0.0, "g": 0.0, "b": 0.0, "value": 0.0, "saturation": 0.0}
    r_sum = g_sum = b_sum = 0
    for r, g, b in pixels:
        r_sum += r
        g_sum += g
        b_sum += b
    r = r_sum / count / 255.0
    g = g_sum / count / 255.0
    b = b_sum / count / 255.0
    value = max(r, g, b)
    minimum = min(r, g, b)
    saturation = 0.0 if value <= 0 else (value - minimum) / value
    return {"r": r, "g": g, "b": b, "value": value, "saturation": saturation}


def _grid_cells(image) -> List[Dict[str, float]]:
    small = image.resize((COLOR_GRID * 8, COLOR_GRID * 8), Image.BILINEAR)
    data = _pixels(small)
    width = COLOR_GRID * 8
    cells: List[Dict[str, float]] = []
    step = 8
    for cy in range(COLOR_GRID):
        for cx in range(COLOR_GRID):
            block: List[Tuple[int, int, int]] = []
            for y in range(cy * step, (cy + 1) * step):
                row_start = y * width
                block.extend(data[row_start + cx * step: row_start + (cx + 1) * step])
            cells.append(_cell_stats(block))
    return cells


def _gradient_energy(image) -> float:
    """Оценка резкости по центральному фрагменту в исходном разрешении.

    Уменьшение всего кадра сглаживает расфокус, поэтому берётся кроп без ресайза:
    там сохраняются высокие частоты, по которым и видно, наведена ли резкость.
    """
    gray = image.convert("L")
    width, height = gray.size
    side = min(SHARPNESS_CROP, width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    crop = gray.crop((left, top, left + side, top + side))
    data = _pixels(crop)

    total = 0
    pairs = 0
    for y in range(side):
        row = y * side
        for x in range(side - 1):
            total += abs(data[row + x] - data[row + x + 1])
            pairs += 1
    for y in range(side - 1):
        row = y * side
        next_row = (y + 1) * side
        for x in range(side):
            total += abs(data[row + x] - data[next_row + x])
            pairs += 1
    if pairs == 0:
        return 0.0
    return total / pairs / 255.0


def _luma_profile(image) -> List[float]:
    gray = image.convert("L").resize((32, 32), Image.BILINEAR)
    return [value / 255.0 for value in _pixels(gray)]


def _assess_quality(image, brightness: float, sharpness: float) -> ImageQuality:
    width, height = image.size
    problems: List[str] = []
    if min(width, height) < MIN_USEFUL_SIDE:
        problems.append("слишком маленькое разрешение, снимите ближе и без цифрового зума")
    if brightness < DARK_THRESHOLD:
        problems.append("кадр слишком тёмный, добавьте света, но не используйте вспышку")
    elif brightness > BRIGHT_THRESHOLD:
        problems.append("кадр пересвечен, уберите прямой источник света")
    if sharpness < BLUR_THRESHOLD:
        problems.append("кадр размыт, зафиксируйте камеру и наведите резкость на нужную зону")
    return ImageQuality(
        width=width,
        height=height,
        brightness=round(brightness, 3),
        sharpness=round(sharpness, 4),
        problems=problems,
    )


def _color_cues(cells: Sequence[Dict[str, float]]) -> List[VisualCue]:
    cues: List[VisualCue] = []

    redness_scores = [
        cell["r"] - (cell["g"] + cell["b"]) / 2
        for cell in cells
        if cell["value"] > 0.18
    ]
    if redness_scores:
        top_red = max(redness_scores)
        if top_red > 0.14:
            cues.append(_make_cue("redness", min(0.75, 0.30 + (top_red - 0.14) * 2.2)))

    yellow_scores = [
        min(cell["r"], cell["g"]) - cell["b"]
        for cell in cells
        if cell["value"] > 0.30 and abs(cell["r"] - cell["g"]) < 0.12
    ]
    if yellow_scores:
        top_yellow = max(yellow_scores)
        if top_yellow > 0.20:
            cues.append(_make_cue("yellow_tint", min(0.65, 0.25 + (top_yellow - 0.20) * 1.8)))

    pale_cells = [
        cell
        for cell in cells
        if cell["value"] > 0.62 and cell["saturation"] < 0.16
    ]
    if len(pale_cells) >= 2:
        ratio = len(pale_cells) / len(cells)
        cues.append(_make_cue("pallor", min(0.55, 0.20 + ratio * 0.8)))

    debris_cells = [
        cell
        for cell in cells
        if cell["value"] < 0.34 and cell["r"] > cell["g"] > cell["b"] and cell["saturation"] > 0.20
    ]
    if debris_cells:
        ratio = len(debris_cells) / len(cells)
        cues.append(_make_cue("dark_debris", min(0.60, 0.25 + ratio * 1.2)))

    skin_cells = [
        cell
        for cell in cells
        if 0.45 < cell["value"] < 0.88
        and cell["r"] > cell["g"] > cell["b"]
        and 0.12 < cell["saturation"] < 0.40
    ]
    if len(skin_cells) >= 3:
        ratio = len(skin_cells) / len(cells)
        cues.append(_make_cue("bare_skin_patch", min(0.50, 0.18 + ratio * 0.7)))

    discharge_cells = [
        cell
        for cell in cells
        if cell["value"] > 0.55
        and cell["g"] >= cell["r"] > cell["b"]
        and cell["saturation"] > 0.18
    ]
    if discharge_cells:
        cues.append(_make_cue("discharge", min(0.45, 0.20 + len(discharge_cells) / len(cells))))

    return cues


def analyze_image(image_bytes: bytes) -> MediaAnalysis:
    """Анализирует одно изображение: качество кадра и цветовые подсказки."""
    if not PIL_AVAILABLE:
        return MediaAnalysis(
            kind="photo",
            frames_analyzed=0,
            quality=None,
            notes=[
                "Библиотека Pillow не установлена, автоматический разбор кадра недоступен. "
                "Ответьте на вопросы по признакам вручную."
            ],
        )

    try:
        with Image.open(io.BytesIO(image_bytes)) as raw:
            image = raw.convert("RGB")
            image.load()
    except Exception as exc:  # noqa: BLE001 - формат файла может быть любым
        logger.warning("Не удалось открыть изображение: %s", exc)
        return MediaAnalysis(
            kind="photo",
            frames_analyzed=0,
            quality=None,
            notes=["Не удалось прочитать файл как изображение, пришлите фото ещё раз."],
        )

    cells = _grid_cells(image)
    brightness = sum(cell["value"] for cell in cells) / len(cells)
    sharpness = _gradient_energy(image)
    quality = _assess_quality(image, brightness, sharpness)

    cues = _color_cues(cells)
    cues.extend(_classifier_cues(image_bytes))

    notes: List[str] = []
    if quality.problems:
        notes.append(quality.summary)
    if not cues:
        notes.append(
            "Явных цветовых отклонений в кадре не найдено, это не исключает заболевания."
        )

    return MediaAnalysis(
        kind="photo",
        frames_analyzed=1,
        quality=quality,
        cues=_merge_cues([cues]),
        notes=notes,
    )


def merge_analyses(analyses: Sequence[MediaAnalysis], kind: str = "photo") -> MediaAnalysis:
    """Объединяет разборы нескольких файлов, например фотоальбома, в один результат."""
    usable = [item for item in analyses if item.quality is not None]
    if not usable:
        return MediaAnalysis(
            kind=kind,
            frames_analyzed=0,
            quality=None,
            notes=["Ни один из присланных файлов не удалось разобрать."],
        )

    best_quality = max(usable, key=lambda item: item.quality.sharpness).quality
    notes: List[str] = []
    for item in usable:
        for note in item.notes:
            if note not in notes:
                notes.append(note)

    return MediaAnalysis(
        kind=kind,
        frames_analyzed=sum(max(1, item.frames_analyzed) for item in usable),
        quality=best_quality,
        cues=_merge_cues([item.cues for item in usable]),
        notes=notes,
    )


def _classifier_cues(image_bytes: bytes) -> List[VisualCue]:
    """Преобразует предсказания внешней модели в подсказки."""
    classifier = get_classifier()
    if classifier is None:
        return []
    try:
        predictions = classifier.predict(image_bytes)
    except Exception as exc:  # noqa: BLE001 - внешняя модель не должна ломать бота
        logger.warning("Классификатор признаков вернул ошибку: %s", exc)
        return []

    cues: List[VisualCue] = []
    for sign_code, confidence in predictions:
        if confidence < 0.35:
            continue
        cues.append(
            VisualCue(
                code=f"model_{sign_code}",
                label=f"Модель распознала признак: {sign_code}",
                confidence=round(float(confidence), 3),
                suggested_signs=[sign_code],
                explanation="Предсказание подключённой модели классификации.",
            )
        )
    return cues


def _merge_cues(cue_groups: Sequence[Sequence[VisualCue]]) -> List[VisualCue]:
    """Объединяет подсказки из нескольких кадров, усиливая повторяющиеся."""
    total_groups = max(1, len(cue_groups))
    buckets: Dict[str, List[VisualCue]] = {}
    for group in cue_groups:
        for cue in group:
            buckets.setdefault(cue.code, []).append(cue)

    merged: List[VisualCue] = []
    for code, items in buckets.items():
        presence = len(items) / total_groups
        mean_confidence = sum(item.confidence for item in items) / len(items)
        # Подсказка, повторяющаяся на многих кадрах, надёжнее случайного блика.
        confidence = mean_confidence * (0.55 + 0.45 * presence)
        template = items[0]
        merged.append(
            VisualCue(
                code=code,
                label=template.label,
                confidence=round(min(1.0, confidence), 3),
                suggested_signs=list(template.suggested_signs),
                explanation=template.explanation,
            )
        )
    return sorted(merged, key=lambda cue: cue.confidence, reverse=True)


def _periodicity(series: Sequence[float]) -> float:
    """Оценивает ритмичность колебаний движения через автокорреляцию."""
    if len(series) < 6:
        return 0.0
    mean = sum(series) / len(series)
    centered = [value - mean for value in series]
    denominator = sum(value * value for value in centered)
    if denominator <= 1e-9:
        return 0.0
    best = 0.0
    for lag in range(2, max(3, len(series) // 2)):
        numerator = sum(
            centered[i] * centered[i + lag] for i in range(len(centered) - lag)
        )
        best = max(best, numerator / denominator)
    return max(0.0, min(1.0, best * 2))


def analyze_frames(frames: Sequence[bytes], kind: str = "video") -> MediaAnalysis:
    """Анализирует набор кадров короткого видео и агрегирует подсказки."""
    if not frames:
        return MediaAnalysis(
            kind=kind,
            frames_analyzed=0,
            quality=None,
            notes=["Не удалось извлечь кадры из видео, пришлите файл короче и меньшего размера."],
        )

    per_frame: List[MediaAnalysis] = [analyze_image(frame) for frame in frames]
    usable = [item for item in per_frame if item.quality is not None]
    if not usable:
        return MediaAnalysis(
            kind=kind,
            frames_analyzed=0,
            quality=None,
            notes=per_frame[0].notes or ["Кадры видео не удалось разобрать."],
        )

    best_quality = max(usable, key=lambda item: item.quality.sharpness).quality
    merged = _merge_cues([item.cues for item in usable])

    motion: Optional[MotionMetrics] = None
    if PIL_AVAILABLE and len(frames) >= 2:
        motion = _motion_metrics(frames)
        merged = _merge_cues([merged, _motion_cues(motion)])

    notes: List[str] = []
    if best_quality.problems:
        notes.append(best_quality.summary)
    blurry_frames = sum(1 for item in usable if item.quality.sharpness < BLUR_THRESHOLD)
    if blurry_frames and blurry_frames < len(usable):
        notes.append(
            f"Размытых кадров: {blurry_frames} из {len(usable)}. "
            "Снимайте при хорошем свете, кошка должна быть в фокусе."
        )

    return MediaAnalysis(
        kind=kind,
        frames_analyzed=len(usable),
        quality=best_quality,
        cues=merged,
        motion=motion,
        notes=notes,
    )


def _motion_metrics(frames: Sequence[bytes]) -> Optional[MotionMetrics]:
    profiles: List[List[float]] = []
    for frame in frames:
        try:
            with Image.open(io.BytesIO(frame)) as raw:
                image = raw.convert("RGB")
                profiles.append(_luma_profile(image))
        except Exception:  # noqa: BLE001 - битый кадр просто пропускаем
            continue

    if len(profiles) < 2:
        return None

    diffs: List[float] = []
    for previous, current in zip(profiles, profiles[1:]):
        diffs.append(
            sum(abs(a - b) for a, b in zip(previous, current)) / len(current)
        )

    return MotionMetrics(
        frames=len(profiles),
        mean_motion=round(sum(diffs) / len(diffs), 4),
        peak_motion=round(max(diffs), 4),
        periodicity=round(_periodicity(diffs), 3),
    )


def _motion_cues(motion: Optional[MotionMetrics]) -> List[VisualCue]:
    if motion is None:
        return []
    cues: List[VisualCue] = []
    if motion.mean_motion < 0.012:
        cues.append(_make_cue("low_activity", 0.35))
    if motion.periodicity > 0.35 and motion.mean_motion > 0.010:
        cues.append(_make_cue("repetitive_motion", min(0.60, 0.25 + motion.periodicity * 0.5)))
    if motion.peak_motion > 0.09 and motion.mean_motion > 0.03:
        irregularity = motion.peak_motion / max(motion.mean_motion, 1e-6)
        if irregularity > 2.5:
            cues.append(_make_cue("unstable_gait", min(0.45, 0.20 + math.log10(irregularity) * 0.3)))
    return cues
