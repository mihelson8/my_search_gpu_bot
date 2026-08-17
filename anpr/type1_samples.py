"""Ground-truth Type-1 plates from the user's comparative samples.

Layout: «А 000 АА | 00 RUS» — letter, 3 digits, 2 letters, region 2–3 digits.
"""

from __future__ import annotations

from typing import List, Tuple

# (how it appears on the photo / OCR, compact expected, display «А 000 АА | 00»)
TYPE1_SAMPLES: List[Tuple[str, str, str]] = [
    ("E 999 KX 70 RUS", "Е999КХ70", "Е 999 КХ | 70"),
    ("c 047 cc 99 RUS", "С047СС99", "С 047 СС | 99"),
    ("A 177 AA 77 RUS", "А177АА77", "А 177 АА | 77"),
    ("X 969 AC 60", "Х969АС60", "Х 969 АС | 60"),
    ("E 441 OO 61", "Е441ОО61", "Е 441 ОО | 61"),
    ("O 916 AH 62", "О916АН62", "О 916 АН | 62"),
    ("B 712 EA 77", "В712ЕА77", "В 712 ЕА | 77"),
    ("С 065 МК 78 RUS", "С065МК78", "С 065 МК | 78"),
    ("H 778 EM 799 RUS", "Н778ЕМ799", "Н 778 ЕМ | 799"),
    ("C 292 HT 01", "С292НТ01", "С 292 НТ | 01"),
    ("C 292 HT 71", "С292НТ71", "С 292 НТ | 71"),
]


def sample_compacts() -> List[str]:
    return [compact for _raw, compact, _shown in TYPE1_SAMPLES]
