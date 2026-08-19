"""
Feline Visual Triage Engine.
Сопоставляет подтверждённые визуальные признаки с профилями заболеваний,
определяет срочность обращения и подбирает справочные данные о препаратах.

Движок не ставит диагноз. Он даёт ранжированный список вероятных состояний,
чтобы владелец быстрее понял, насколько срочно нужен ветеринарный врач.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Set

from vetcare.knowledge import (
    DISEASES,
    SIGNS,
    URGENCY_ORDER,
    DiseaseProfile,
    Urgency,
    VisualSign,
    get_sign,
)
from vetcare.vision import MediaAnalysis

# Признаки, при которых поездка в клинику не обсуждается, независимо от диагноза.
EMERGENCY_SIGNS: Set[str] = {
    "breathing_open_mouth",
    "breathing_abdominal",
    "urine_straining",
    "urine_crying",
    "neuro_seizure",
    "neuro_ataxia",
    "mucosa_yellow",
    "mouth_pale_gums",
    "hypothermia_collapse",
}

MIN_PROBABILITY_TO_SHOW = 4.0
MAX_DIFFERENTIALS = 5
MAX_QUESTIONS = 4


@dataclass
class PatientInfo:
    """Минимальные данные о пациенте, влияющие на оценку срочности."""

    name: str = ""
    age_years: Optional[float] = None
    is_male: Optional[bool] = None
    weight_kg: Optional[float] = None

    @property
    def is_senior(self) -> bool:
        return self.age_years is not None and self.age_years >= 8

    @property
    def is_kitten(self) -> bool:
        return self.age_years is not None and self.age_years < 1


@dataclass
class CaseSession:
    """Состояние одного разбора: подтверждённые признаки и загруженные медиа."""

    patient: PatientInfo = field(default_factory=PatientInfo)
    confirmed_signs: Set[str] = field(default_factory=set)
    rejected_signs: Set[str] = field(default_factory=set)
    media: List[MediaAnalysis] = field(default_factory=list)

    def confirm(self, sign_code: str) -> bool:
        if sign_code not in SIGNS:
            return False
        self.rejected_signs.discard(sign_code)
        self.confirmed_signs.add(sign_code)
        return True

    def reject(self, sign_code: str) -> bool:
        if sign_code not in SIGNS:
            return False
        self.confirmed_signs.discard(sign_code)
        self.rejected_signs.add(sign_code)
        return True

    def toggle(self, sign_code: str) -> bool:
        """Переключает признак: подтверждён или не отмечен."""
        if sign_code not in SIGNS:
            return False
        if sign_code in self.confirmed_signs:
            self.confirmed_signs.discard(sign_code)
        else:
            self.rejected_signs.discard(sign_code)
            self.confirmed_signs.add(sign_code)
        return sign_code in self.confirmed_signs

    def add_media(self, analysis: MediaAnalysis) -> None:
        self.media.append(analysis)

    def reset(self) -> None:
        self.confirmed_signs.clear()
        self.rejected_signs.clear()
        self.media.clear()
        self.patient = PatientInfo()

    @property
    def is_empty(self) -> bool:
        return not self.confirmed_signs and not self.media

    @property
    def answered_signs(self) -> Set[str]:
        return self.confirmed_signs | self.rejected_signs

    @property
    def suggested_signs(self) -> List[str]:
        """Признаки, подсказанные анализом медиа и ещё не отмеченные владельцем."""
        ordered: List[str] = []
        for analysis in self.media:
            for sign_code in analysis.suggested_signs:
                if sign_code in SIGNS and sign_code not in self.answered_signs:
                    if sign_code not in ordered:
                        ordered.append(sign_code)
        return ordered

    @property
    def media_confidence_boost(self) -> Dict[str, float]:
        """Максимальная уверенность визуальной подсказки по каждому признаку."""
        boosts: Dict[str, float] = {}
        for analysis in self.media:
            for cue in analysis.cues:
                for sign_code in cue.suggested_signs:
                    boosts[sign_code] = max(boosts.get(sign_code, 0.0), cue.confidence)
        return boosts


@dataclass
class Differential:
    """Одно вероятное состояние с оценкой соответствия признакам."""

    disease: DiseaseProfile
    score: float
    probability: float
    matched_signs: List[str]
    missing_key_signs: List[str]

    @property
    def matched_labels(self) -> List[str]:
        return [SIGNS[code].label for code in self.matched_signs if code in SIGNS]

    @property
    def missing_key_labels(self) -> List[str]:
        return [SIGNS[code].label for code in self.missing_key_signs if code in SIGNS]


class DataCompleteness(str, Enum):
    LOW = "Данных мало, оценка очень предварительная"
    MEDIUM = "Данных достаточно для предварительной оценки"
    HIGH = "Данных много, но подтверждение всё равно за врачом"


@dataclass
class Assessment:
    """Результат разбора случая."""

    differentials: List[Differential]
    urgency: Urgency
    red_flags: List[str]
    completeness: DataCompleteness
    confirmed_signs: List[str]
    medication_codes: List[str]
    diagnostics: List[str]
    home_care: List[str]
    zoonotic_warning: bool
    media_notes: List[str]
    next_questions: List[VisualSign]

    @property
    def top(self) -> Optional[Differential]:
        return self.differentials[0] if self.differentials else None


class VisualTriageEngine:
    """Ядро сопоставления признаков с профилями заболеваний."""

    def __init__(self, diseases: Optional[Dict[str, DiseaseProfile]] = None) -> None:
        self.diseases = diseases or DISEASES

    def _disease_score(self, disease: DiseaseProfile, session: CaseSession) -> Optional[Differential]:
        total_weight = sum(disease.sign_weights.values())
        if total_weight <= 0:
            return None

        boosts = session.media_confidence_boost
        matched: List[str] = []
        matched_weight = 0.0
        for sign_code, weight in disease.sign_weights.items():
            if sign_code in session.confirmed_signs:
                matched.append(sign_code)
                matched_weight += weight
            elif sign_code in session.rejected_signs:
                # Отрицание значимого признака снижает вероятность состояния.
                matched_weight -= weight * 0.35
            elif sign_code in boosts:
                # Неподтверждённая визуальная подсказка добавляет лишь малый вклад.
                matched_weight += weight * boosts[sign_code] * 0.25

        key_hits = [code for code in disease.key_signs if code in session.confirmed_signs]
        if not key_hits and len(matched) < 2:
            return None

        coverage = max(0.0, matched_weight) / total_weight
        key_bonus = 0.20 if key_hits else 0.0
        breadth = min(1.0, len(matched) / max(2, len(disease.key_signs) + 1))
        score = coverage * (0.75 + 0.25 * breadth) + key_bonus
        if score <= 0:
            return None

        return Differential(
            disease=disease,
            score=round(min(1.5, score), 4),
            probability=0.0,
            matched_signs=matched,
            missing_key_signs=[
                code for code in disease.key_signs if code not in session.confirmed_signs
            ],
        )

    def _triage(self, session: CaseSession, differentials: List[Differential]) -> Urgency:
        urgency = Urgency.ROUTINE

        for code in session.confirmed_signs:
            sign = get_sign(code)
            if sign is None:
                continue
            if code in EMERGENCY_SIGNS:
                candidate = Urgency.EMERGENCY
            elif sign.is_red_flag:
                candidate = Urgency.URGENT
            else:
                continue
            if URGENCY_ORDER[candidate] > URGENCY_ORDER[urgency]:
                urgency = candidate

        for item in differentials:
            if item.probability < 15.0:
                continue
            if URGENCY_ORDER[item.disease.urgency] > URGENCY_ORDER[urgency]:
                urgency = item.disease.urgency

        # Закупорка уретры у котов развивается быстрее и опаснее.
        if session.patient.is_male and {"urine_straining", "urine_crying"} & session.confirmed_signs:
            urgency = Urgency.EMERGENCY
        # Котята и пожилые кошки декомпенсируются быстрее взрослых.
        if (session.patient.is_kitten or session.patient.is_senior) and URGENCY_ORDER[urgency] == URGENCY_ORDER[Urgency.SOON]:
            urgency = Urgency.URGENT

        return urgency

    def _completeness(self, session: CaseSession) -> DataCompleteness:
        confirmed = len(session.confirmed_signs)
        has_good_media = any(
            analysis.quality is not None and analysis.quality.is_usable for analysis in session.media
        )
        if confirmed >= 4 and has_good_media:
            return DataCompleteness.HIGH
        if confirmed >= 2 or has_good_media:
            return DataCompleteness.MEDIUM
        return DataCompleteness.LOW

    def next_questions(
        self,
        session: CaseSession,
        differentials: Optional[List[Differential]] = None,
        limit: int = MAX_QUESTIONS,
    ) -> List[VisualSign]:
        """Подбирает наиболее информативные неотвеченные вопросы."""
        answered = session.answered_signs
        scores: Dict[str, float] = {}

        for sign_code in session.suggested_signs:
            scores[sign_code] = scores.get(sign_code, 0.0) + 5.0

        candidates = differentials if differentials is not None else self.rank(session)
        for item in candidates:
            weight_factor = max(item.probability, 5.0) / 100.0
            for sign_code, weight in item.disease.sign_weights.items():
                if sign_code in answered:
                    continue
                scores[sign_code] = scores.get(sign_code, 0.0) + weight * weight_factor

        if not scores:
            # Пустая сессия: спрашиваем в первую очередь про угрожающие признаки.
            for sign_code in EMERGENCY_SIGNS:
                scores[sign_code] = 1.0

        ranked = sorted(
            (code for code in scores if code not in answered and code in SIGNS),
            key=lambda code: scores[code],
            reverse=True,
        )
        return [SIGNS[code] for code in ranked[:limit]]

    def rank(self, session: CaseSession) -> List[Differential]:
        """Возвращает ранжированный список вероятных состояний."""
        raw: List[Differential] = []
        for disease in self.diseases.values():
            item = self._disease_score(disease, session)
            if item is not None:
                raw.append(item)

        if not raw:
            return []

        total = sum(item.score for item in raw)
        for item in raw:
            item.probability = round(item.score / total * 100, 1) if total > 0 else 0.0

        raw.sort(key=lambda item: item.probability, reverse=True)
        filtered = [item for item in raw if item.probability >= MIN_PROBABILITY_TO_SHOW]
        return (filtered or raw)[:MAX_DIFFERENTIALS]

    def assess(self, session: CaseSession) -> Assessment:
        """Полная оценка случая: дифференциалы, срочность, рекомендации, препараты."""
        differentials = self.rank(session)
        urgency = self._triage(session, differentials)

        red_flags = [
            SIGNS[code].label
            for code in session.confirmed_signs
            if code in SIGNS and (SIGNS[code].is_red_flag or code in EMERGENCY_SIGNS)
        ]

        medication_codes: List[str] = []
        diagnostics: List[str] = []
        home_care: List[str] = []
        for item in differentials[:3]:
            for code in item.disease.medication_codes:
                if code not in medication_codes:
                    medication_codes.append(code)
            for entry in item.disease.diagnostics:
                if entry not in diagnostics:
                    diagnostics.append(entry)
            for entry in item.disease.home_care:
                if entry not in home_care:
                    home_care.append(entry)

        media_notes: List[str] = []
        for analysis in session.media:
            for note in analysis.notes:
                if note not in media_notes:
                    media_notes.append(note)

        return Assessment(
            differentials=differentials,
            urgency=urgency,
            red_flags=sorted(set(red_flags)),
            completeness=self._completeness(session),
            confirmed_signs=sorted(session.confirmed_signs),
            medication_codes=medication_codes,
            diagnostics=diagnostics,
            home_care=home_care,
            zoonotic_warning=any(item.disease.zoonotic for item in differentials[:3]),
            media_notes=media_notes,
            next_questions=self.next_questions(session, differentials),
        )


def collect_signs_from_media(analyses: Iterable[MediaAnalysis]) -> List[str]:
    """Собирает уникальные коды признаков, подсказанные анализом медиа."""
    result: List[str] = []
    for analysis in analyses:
        for sign_code in analysis.suggested_signs:
            if sign_code in SIGNS and sign_code not in result:
                result.append(sign_code)
    return result
