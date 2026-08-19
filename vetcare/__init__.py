"""
Feline Visual Triage Package.
Определение вероятных заболеваний кошек по визуальным признакам с фото и коротких видео,
оценка срочности обращения и справочные данные о лекарственных препаратах.
"""

from vetcare.engine import (
    Assessment,
    CaseSession,
    DataCompleteness,
    Differential,
    EMERGENCY_SIGNS,
    PatientInfo,
    VisualTriageEngine,
)
from vetcare.knowledge import (
    DISEASES,
    EMERGENCY_CHECKLIST,
    FIRST_AID_RULES,
    MEDICATIONS,
    SIGNS,
    TOXIC_FOR_CATS,
    ZONE_LABELS,
    BodyZone,
    DiseaseProfile,
    Medication,
    Urgency,
    VisualSign,
    medication_groups,
    signs_by_zone,
)
from vetcare.media import check_video, extract_frames_from_bytes
from vetcare.vision import MediaAnalysis, VisualCue, analyze_frames, analyze_image, set_classifier

__all__ = [
    "Assessment",
    "BodyZone",
    "CaseSession",
    "DataCompleteness",
    "DISEASES",
    "Differential",
    "DiseaseProfile",
    "EMERGENCY_CHECKLIST",
    "EMERGENCY_SIGNS",
    "FIRST_AID_RULES",
    "MEDICATIONS",
    "MediaAnalysis",
    "Medication",
    "PatientInfo",
    "SIGNS",
    "TOXIC_FOR_CATS",
    "Urgency",
    "VisualCue",
    "VisualSign",
    "VisualTriageEngine",
    "ZONE_LABELS",
    "analyze_frames",
    "analyze_image",
    "check_video",
    "extract_frames_from_bytes",
    "medication_groups",
    "set_classifier",
    "signs_by_zone",
]
