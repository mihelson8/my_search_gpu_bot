"""
Feline Visual Triage Knowledge Base.
База знаний по визуальным признакам, вероятным заболеваниям кошек,
справочным данным о лекарственных препаратах и опасных для кошек веществах.

ВАЖНО: данные носят справочный характер и не являются постановкой диагноза
или назначением лечения. Диагноз и дозировки определяет только ветеринарный врач.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class BodyZone(str, Enum):
    EYES = "eyes"
    EARS = "ears"
    SKIN = "skin"
    MOUTH = "mouth"
    RESPIRATORY = "respiratory"
    GI = "gi"
    URINARY = "urinary"
    NEURO = "neuro"
    LOCOMOTION = "locomotion"
    GENERAL = "general"


ZONE_LABELS: Dict[BodyZone, str] = {
    BodyZone.EYES: "👁 Глаза",
    BodyZone.EARS: "👂 Уши",
    BodyZone.SKIN: "🐾 Кожа и шерсть",
    BodyZone.MOUTH: "🦷 Рот, зубы, слюна",
    BodyZone.RESPIRATORY: "🫁 Нос и дыхание",
    BodyZone.GI: "🍽 Аппетит и ЖКТ",
    BodyZone.URINARY: "🚽 Мочеиспускание",
    BodyZone.NEURO: "🧠 Неврология и поведение",
    BodyZone.LOCOMOTION: "🦵 Опора и движение",
    BodyZone.GENERAL: "🌡 Общее состояние",
}


class Urgency(str, Enum):
    ROUTINE = "Плановый визит (в течение недели)"
    SOON = "Визит в течение 24-48 часов"
    URGENT = "Срочно к врачу сегодня"
    EMERGENCY = "Экстренно, немедленно в клинику"


URGENCY_ORDER: Dict[Urgency, int] = {
    Urgency.ROUTINE: 0,
    Urgency.SOON: 1,
    Urgency.URGENT: 2,
    Urgency.EMERGENCY: 3,
}

URGENCY_EMOJI: Dict[Urgency, str] = {
    Urgency.ROUTINE: "🟢",
    Urgency.SOON: "🟡",
    Urgency.URGENT: "🟠",
    Urgency.EMERGENCY: "🔴",
}


@dataclass(frozen=True)
class VisualSign:
    """Визуальный признак, который владелец может увидеть на фото или видео."""

    code: str
    zone: BodyZone
    label: str
    question: str
    media_hint: str
    is_red_flag: bool = False
    video_only: bool = False


SIGNS: Dict[str, VisualSign] = {
    # --- Глаза ---
    "eye_redness": VisualSign(
        code="eye_redness",
        zone=BodyZone.EYES,
        label="Покраснение глаза или белка",
        question="Виден ли красный, налитый кровью белок глаза или красная слизистая век?",
        media_hint="Фото головы анфас с близкого расстояния, без вспышки.",
    ),
    "eye_discharge": VisualSign(
        code="eye_discharge",
        zone=BodyZone.EYES,
        label="Выделения из глаз (гной, слизь, слёзы)",
        question="Есть ли выделения из глаз: прозрачные, зелёные или коричневые корочки?",
        media_hint="Фото обоих глаз крупно, чтобы был виден внутренний угол глаза.",
    ),
    "eye_squint": VisualSign(
        code="eye_squint",
        zone=BodyZone.EYES,
        label="Прищуривание, зажмуривание глаза",
        question="Кошка держит один глаз прикрытым, часто моргает или боится света?",
        media_hint="Фото анфас и видео 5-10 секунд, где видно моргание.",
    ),
    "eye_cornea_cloudy": VisualSign(
        code="eye_cornea_cloudy",
        zone=BodyZone.EYES,
        label="Мутность или белесое пятно на роговице",
        question="Появилось ли на поверхности глаза мутное, голубоватое или белое пятно?",
        media_hint="Фото сбоку и анфас при боковом освещении.",
        is_red_flag=True,
    ),
    "eye_third_eyelid": VisualSign(
        code="eye_third_eyelid",
        zone=BodyZone.EYES,
        label="Выступает третье веко (белая плёнка)",
        question="Видно ли, как из внутреннего угла глаза выдвигается белая плёнка?",
        media_hint="Фото анфас крупно.",
    ),
    "eye_pupil_asymmetry": VisualSign(
        code="eye_pupil_asymmetry",
        zone=BodyZone.EYES,
        label="Разный размер зрачков",
        question="Зрачки разного размера при одинаковом освещении?",
        media_hint="Фото анфас при ровном освещении, без вспышки.",
        is_red_flag=True,
    ),
    # --- Уши ---
    "ear_dark_debris": VisualSign(
        code="ear_dark_debris",
        zone=BodyZone.EARS,
        label="Тёмный налёт, похожий на кофейную крошку, в ушах",
        question="В ушной раковине есть тёмно-коричневый или чёрный сухой налёт?",
        media_hint="Фото внутренней поверхности уха, отогнув ушную раковину.",
    ),
    "ear_redness_swelling": VisualSign(
        code="ear_redness_swelling",
        zone=BodyZone.EARS,
        label="Покраснение, отёк ушной раковины",
        question="Кожа внутри уха красная, горячая, утолщённая?",
        media_hint="Фото обоих ушей для сравнения.",
    ),
    "ear_head_shaking": VisualSign(
        code="ear_head_shaking",
        zone=BodyZone.EARS,
        label="Трясёт головой, чешет уши",
        question="Кошка часто трясёт головой или расчёсывает уши до ранок?",
        media_hint="Видео 10-15 секунд с моментом тряски головой.",
        video_only=True,
    ),
    "ear_smell_discharge": VisualSign(
        code="ear_smell_discharge",
        zone=BodyZone.EARS,
        label="Влажные выделения и неприятный запах из уха",
        question="Из уха идёт неприятный запах или влажные, гнойные выделения?",
        media_hint="Фото уха крупно.",
    ),
    # --- Кожа и шерсть ---
    "skin_hair_loss_patch": VisualSign(
        code="skin_hair_loss_patch",
        zone=BodyZone.SKIN,
        label="Залысины, участки без шерсти",
        question="Есть ли участки кожи без шерсти, округлые проплешины?",
        media_hint="Фото очага при хорошем свете, рядом монета или палец для масштаба.",
    ),
    "skin_scaling_crust": VisualSign(
        code="skin_scaling_crust",
        zone=BodyZone.SKIN,
        label="Шелушение, корочки, перхоть",
        question="На коже видно шелушение, серые чешуйки, сухие корочки?",
        media_hint="Фото очага крупно, раздвинув шерсть.",
    ),
    "skin_itching": VisualSign(
        code="skin_itching",
        zone=BodyZone.SKIN,
        label="Сильный зуд, расчёсы, вылизывание до кожи",
        question="Кошка постоянно чешется, вылизывает или выкусывает шерсть?",
        media_hint="Видео 15-20 секунд, где видно, как она чешется.",
    ),
    "skin_black_specks": VisualSign(
        code="skin_black_specks",
        zone=BodyZone.SKIN,
        label="Чёрные крупинки у корней шерсти",
        question="У корней шерсти есть чёрные точки, похожие на молотый перец?",
        media_hint="Фото основания хвоста и спины, раздвинув шерсть.",
    ),
    "skin_wound_swelling": VisualSign(
        code="skin_wound_swelling",
        zone=BodyZone.SKIN,
        label="Рана, шишка или горячая припухлость",
        question="Есть ли на теле рана, плотная шишка или горячая болезненная припухлость?",
        media_hint="Фото с двух ракурсов, аккуратно, не надавливая.",
        is_red_flag=True,
    ),
    "skin_miliary_bumps": VisualSign(
        code="skin_miliary_bumps",
        zone=BodyZone.SKIN,
        label="Мелкие плотные узелки по спине",
        question="При поглаживании по спине чувствуются мелкие узелки, как крупинки?",
        media_hint="Фото спины и области у основания хвоста.",
    ),
    "skin_chin_blackheads": VisualSign(
        code="skin_chin_blackheads",
        zone=BodyZone.SKIN,
        label="Чёрные точки на подбородке",
        question="На подбородке или у губ есть чёрные точки и уплотнения?",
        media_hint="Фото подбородка снизу крупно.",
    ),
    # --- Рот и зубы ---
    "mouth_gum_redness": VisualSign(
        code="mouth_gum_redness",
        zone=BodyZone.MOUTH,
        label="Красная кайма дёсен, воспаление",
        question="Дёсны у края зубов яркокрасные, кровят?",
        media_hint="Фото с приподнятой губой, лучше вдвоём и при ярком свете.",
    ),
    "mouth_drooling": VisualSign(
        code="mouth_drooling",
        zone=BodyZone.MOUTH,
        label="Слюнотечение",
        question="Течёт слюна, шерсть на груди и подбородке мокрая?",
        media_hint="Видео 10 секунд и фото подбородка.",
    ),
    "mouth_tartar": VisualSign(
        code="mouth_tartar",
        zone=BodyZone.MOUTH,
        label="Зубной камень, коричневый налёт",
        question="На зубах есть плотный коричневый или жёлтый налёт?",
        media_hint="Фото боковых зубов с приподнятой губой.",
    ),
    "mouth_ulcers": VisualSign(
        code="mouth_ulcers",
        zone=BodyZone.MOUTH,
        label="Язвы на языке, губах или нёбе",
        question="Видны ли язвочки или эрозии на языке, губах, нёбе?",
        media_hint="Фото при широком открытии рта, если кошка позволяет.",
        is_red_flag=True,
    ),
    "mouth_pale_gums": VisualSign(
        code="mouth_pale_gums",
        zone=BodyZone.MOUTH,
        label="Бледные, почти белые дёсны",
        question="Дёсны и слизистые бледные, серые или белые?",
        media_hint="Фото дёсен с приподнятой губой при белом свете.",
        is_red_flag=True,
    ),
    "mucosa_yellow": VisualSign(
        code="mucosa_yellow",
        zone=BodyZone.MOUTH,
        label="Желтушность слизистых, кожи, белков глаз",
        question="Слизистые, белки глаз или кожа в ушах приобрели жёлтый оттенок?",
        media_hint="Фото дёсен и белков глаз при естественном свете, без фильтров.",
        is_red_flag=True,
    ),
    # --- Нос и дыхание ---
    "nose_discharge": VisualSign(
        code="nose_discharge",
        zone=BodyZone.RESPIRATORY,
        label="Выделения из носа, чихание",
        question="Есть ли выделения из носа, чихание, забитый нос?",
        media_hint="Фото носа крупно и видео 10-15 секунд с чиханием.",
    ),
    "breathing_open_mouth": VisualSign(
        code="breathing_open_mouth",
        zone=BodyZone.RESPIRATORY,
        label="Дыхание открытым ртом в покое",
        question="Кошка дышит с открытым ртом в состоянии покоя?",
        media_hint="Видео 15-20 секунд в покое, видно грудную клетку и морду.",
        is_red_flag=True,
    ),
    "breathing_abdominal": VisualSign(
        code="breathing_abdominal",
        zone=BodyZone.RESPIRATORY,
        label="Учащённое, тяжёлое дыхание животом",
        question="Более 40 вдохов в минуту в покое, живот заметно ходит при дыхании?",
        media_hint="Видео 20-30 секунд сбоку, кошка лежит спокойно.",
        is_red_flag=True,
        video_only=True,
    ),
    "cough": VisualSign(
        code="cough",
        zone=BodyZone.RESPIRATORY,
        label="Кашель, приступы с вытянутой шеей",
        question="Бывают приступы кашля, кошка вытягивает шею и приседает?",
        media_hint="Видео приступа, звук обязательно включён.",
    ),
    # --- ЖКТ ---
    "appetite_loss": VisualSign(
        code="appetite_loss",
        zone=BodyZone.GI,
        label="Отказ от еды более суток",
        question="Кошка не ест больше 24 часов?",
        media_hint="Фото нетронутой порции корма, отметьте время.",
        is_red_flag=True,
    ),
    "vomiting": VisualSign(
        code="vomiting",
        zone=BodyZone.GI,
        label="Рвота",
        question="Была ли рвота за последние 24 часа, сколько раз?",
        media_hint="Фото содержимого рвоты на светлой салфетке.",
    ),
    "diarrhea": VisualSign(
        code="diarrhea",
        zone=BodyZone.GI,
        label="Жидкий стул или стул с кровью",
        question="Стул жидкий, со слизью или кровью?",
        media_hint="Фото лотка при хорошем освещении.",
    ),
    "weight_loss": VisualSign(
        code="weight_loss",
        zone=BodyZone.GI,
        label="Похудание, выступающий позвоночник",
        question="Стали заметны позвонки, рёбра, кости таза?",
        media_hint="Фото сверху и сбоку в полный рост.",
    ),
    "abdomen_distended": VisualSign(
        code="abdomen_distended",
        zone=BodyZone.GI,
        label="Раздутый, напряжённый живот",
        question="Живот увеличен, натянут, кошка не даёт его трогать?",
        media_hint="Фото сбоку и сверху стоя.",
        is_red_flag=True,
    ),
    # --- Моча ---
    "urine_straining": VisualSign(
        code="urine_straining",
        zone=BodyZone.URINARY,
        label="Долго сидит в лотке, тужится без результата",
        question="Кошка часто заходит в лоток, тужится, но моча не выходит?",
        media_hint="Видео поведения в лотке, отметьте, сколько мочи получилось.",
        is_red_flag=True,
    ),
    "urine_blood": VisualSign(
        code="urine_blood",
        zone=BodyZone.URINARY,
        label="Кровь в моче, розовая моча",
        question="Моча розовая, красная или с кровяными сгустками?",
        media_hint="Фото наполнителя или салфетки с мочой при белом свете.",
        is_red_flag=True,
    ),
    "urine_crying": VisualSign(
        code="urine_crying",
        zone=BodyZone.URINARY,
        label="Кричит при мочеиспускании",
        question="Кошка мяукает, кричит или замирает при попытке помочиться?",
        media_hint="Видео с включённым звуком.",
        is_red_flag=True,
    ),
    "urine_increased": VisualSign(
        code="urine_increased",
        zone=BodyZone.URINARY,
        label="Много пьёт и много мочится",
        question="Заметно выросли объёмы питья и мочи, комки в лотке крупнее?",
        media_hint="Фото лотка и записи объёма выпитой воды за сутки.",
    ),
    # --- Неврология и поведение ---
    "neuro_head_tilt": VisualSign(
        code="neuro_head_tilt",
        zone=BodyZone.NEURO,
        label="Наклон головы в сторону",
        question="Голова постоянно наклонена в одну сторону?",
        media_hint="Видео 15 секунд, где кошка стоит и идёт.",
        is_red_flag=True,
    ),
    "neuro_ataxia": VisualSign(
        code="neuro_ataxia",
        zone=BodyZone.NEURO,
        label="Шаткая походка, заносит в сторону",
        question="Кошка ходит шатко, падает, заносит в сторону?",
        media_hint="Видео 20-30 секунд по прямой на нескользком полу.",
        is_red_flag=True,
        video_only=True,
    ),
    "neuro_seizure": VisualSign(
        code="neuro_seizure",
        zone=BodyZone.NEURO,
        label="Судороги, подёргивания, обмороки",
        question="Были судороги, подёргивания мышц, потеря сознания?",
        media_hint="Видео приступа целиком, если это безопасно.",
        is_red_flag=True,
        video_only=True,
    ),
    "neuro_hiding": VisualSign(
        code="neuro_hiding",
        zone=BodyZone.NEURO,
        label="Прячется, вялость, апатия",
        question="Кошка забилась в укрытие, не реагирует на игру и еду?",
        media_hint="Видео 15 секунд с попыткой привлечь внимание игрушкой.",
    ),
    "neuro_hyperactive": VisualSign(
        code="neuro_hyperactive",
        zone=BodyZone.NEURO,
        label="Беспокойство, ночные крики, гиперактивность",
        question="Кошка стала беспокойной, громко кричит ночью, не может усидеть?",
        media_hint="Видео 20 секунд активного поведения.",
    ),
    # --- Опора и движение ---
    "limping": VisualSign(
        code="limping",
        zone=BodyZone.LOCOMOTION,
        label="Хромота, не опирается на лапу",
        question="Кошка щадит лапу, хромает или совсем не опирается?",
        media_hint="Видео 20-30 секунд, как кошка идёт по прямой, лапы в кадре.",
        video_only=True,
    ),
    "joint_swelling": VisualSign(
        code="joint_swelling",
        zone=BodyZone.LOCOMOTION,
        label="Отёк сустава или лапы",
        question="Есть ли отёк, утолщение сустава или лапы по сравнению с другой?",
        media_hint="Фото обеих лап рядом для сравнения.",
        is_red_flag=True,
    ),
    "jump_refusal": VisualSign(
        code="jump_refusal",
        zone=BodyZone.LOCOMOTION,
        label="Перестала прыгать, тяжело встаёт",
        question="Кошка перестала прыгать на привычные поверхности, скованно встаёт?",
        media_hint="Видео подъёма с лежанки и походки.",
    ),
    # --- Общее состояние ---
    "coat_dull": VisualSign(
        code="coat_dull",
        zone=BodyZone.GENERAL,
        label="Тусклая, свалявшаяся шерсть",
        question="Шерсть потускнела, сбивается в колтуны, кошка не умывается?",
        media_hint="Фото в полный рост при дневном свете.",
    ),
    "dehydration": VisualSign(
        code="dehydration",
        zone=BodyZone.GENERAL,
        label="Признаки обезвоживания, запавшие глаза",
        question="Кожа на загривке медленно расправляется, глаза выглядят запавшими?",
        media_hint="Видео проверки складки кожи на загривке.",
        is_red_flag=True,
    ),
    "obesity": VisualSign(
        code="obesity",
        zone=BodyZone.GENERAL,
        label="Избыточный вес, рёбра не прощупываются",
        question="Живот отвисает, талии не видно сверху, рёбра не прощупываются?",
        media_hint="Фото сверху и строго сбоку стоя.",
    ),
    "hypothermia_collapse": VisualSign(
        code="hypothermia_collapse",
        zone=BodyZone.GENERAL,
        label="Холодные лапы, слабость, не встаёт",
        question="Лапы и уши холодные, кошка не может встать?",
        media_hint="Немедленно в клинику, фото не нужно.",
        is_red_flag=True,
    ),
}


@dataclass(frozen=True)
class Medication:
    """Справочная карточка препарата. Не является назначением."""

    code: str
    name: str
    group: str
    brands: List[str]
    forms: List[str]
    indications: List[str]
    dose_reference: str
    cautions: List[str]
    contraindications: List[str]
    prescription_only: bool = True
    withdrawal_note: str = ""


MEDICATIONS: Dict[str, Medication] = {
    "meloxicam": Medication(
        code="meloxicam",
        name="Мелоксикам",
        group="НПВС, противовоспалительное и обезболивающее",
        brands=["Локсиком", "Мелоксидил", "Мелоксивет"],
        forms=["суспензия для орального применения", "раствор для инъекций"],
        indications=[
            "боль и воспаление при травмах",
            "послеоперационная анальгезия",
            "остеоартрит, боль в суставах",
        ],
        dose_reference=(
            "Литературная справка для кошек: 0,05-0,1 мг/кг один раз в сутки, "
            "коротким курсом. Точную дозу и длительность назначает только врач."
        ),
        cautions=[
            "нельзя при обезвоживании, до восстановления объёма жидкости",
            "требует контроля почек и печени при курсе более 3-5 дней",
            "не комбинировать с другими НПВС и кортикостероидами",
        ],
        contraindications=[
            "болезни почек и печени",
            "язвы желудка, рвота с кровью",
            "беременность, лактация, котята до 6 недель",
        ],
    ),
    "gabapentin": Medication(
        code="gabapentin",
        name="Габапентин",
        group="Анальгетик при нейропатической боли, седация",
        brands=["Габапентин (человеческие капсулы по назначению врача)"],
        forms=["капсулы", "раствор без ксилита"],
        indications=[
            "хроническая и нейропатическая боль",
            "снижение стресса перед визитом в клинику",
        ],
        dose_reference=(
            "Литературная справка: 5-10 мг/кг внутрь, схема подбирается врачом. "
            "Растворы с ксилитом кошкам не подходят."
        ),
        cautions=[
            "вызывает сонливость и шаткость походки",
            "дозу снижают при болезни почек",
        ],
        contraindications=["индивидуальная непереносимость"],
    ),
    "amoxiclav": Medication(
        code="amoxiclav",
        name="Амоксициллин с клавулановой кислотой",
        group="Антибиотик пенициллинового ряда",
        brands=["Синулокс", "Амоксиклав по назначению врача"],
        forms=["таблетки", "суспензия", "инъекции"],
        indications=[
            "инфицированные раны, абсцессы после укусов",
            "инфекции кожи и мягких тканей",
            "инфекции мочевыводящих путей",
        ],
        dose_reference=(
            "Литературная справка: 12,5 мг/кг два раза в сутки. Курс и препарат "
            "выбирает врач, желательно после посева на чувствительность."
        ),
        cautions=[
            "нельзя прерывать курс досрочно",
            "возможны рвота и жидкий стул",
        ],
        contraindications=["аллергия на пенициллины"],
    ),
    "doxycycline": Medication(
        code="doxycycline",
        name="Доксициклин",
        group="Антибиотик тетрациклинового ряда",
        brands=["Доксициклин", "Юнидокс по назначению врача"],
        forms=["таблетки", "суспензия"],
        indications=[
            "хламидийный конъюнктивит",
            "инфекции верхних дыхательных путей",
            "микоплазмоз, гемоплазмоз",
        ],
        dose_reference=(
            "Литературная справка: 5-10 мг/кг в сутки по назначению врача. Обязательно "
            "запивать водой или давать с едой, иначе возможен ожог пищевода."
        ),
        cautions=[
            "после таблетки дать 5-6 мл воды из шприца без иглы",
            "может окрашивать зубы у котят",
        ],
        contraindications=["котята в период смены зубов", "беременность"],
    ),
    "tetracycline_eye": Medication(
        code="tetracycline_eye",
        name="Тетрациклиновая глазная мазь 1%",
        group="Местный антибиотик для глаз",
        brands=["Тетрациклиновая мазь глазная 1%"],
        forms=["глазная мазь"],
        indications=["бактериальный конъюнктивит", "хламидийный конъюнктивит"],
        dose_reference=(
            "Литературная справка: полоска мази за нижнее веко 2-3 раза в сутки. "
            "Только глазная форма 1%, кожная 3% для глаз запрещена."
        ),
        cautions=[
            "нельзя применять при подозрении на язву роговицы без осмотра врача",
            "перед закладыванием мази промыть глаз физраствором",
        ],
        contraindications=["повреждение роговицы без назначения врача"],
        prescription_only=False,
    ),
    "saline_rinse": Medication(
        code="saline_rinse",
        name="Физиологический раствор 0,9%",
        group="Средство гигиены глаз и ран",
        brands=["Натрия хлорид 0,9%"],
        forms=["раствор в ампулах и флаконах"],
        indications=[
            "промывание глаз от выделений",
            "первичное промывание свежих ран",
            "размягчение корочек на носу",
        ],
        dose_reference=(
            "Промывать комнатной температурой, отдельным тампоном для каждого глаза, "
            "движением от внешнего угла к внутреннему."
        ),
        cautions=["не использовать спиртовые и перекисные растворы для глаз"],
        contraindications=[],
        prescription_only=False,
    ),
    "selamectin": Medication(
        code="selamectin",
        name="Селамектин",
        group="Наружное противопаразитарное средство",
        brands=["Стронгхолд", "Селафорт"],
        forms=["капли на кожу в области холки"],
        indications=[
            "блохи",
            "ушной клещ Otodectes cynotis",
            "нотоэдроз, профилактика гельминтов",
        ],
        dose_reference=(
            "Литературная справка: 6 мг/кг однократно на кожу холки, "
            "повтор по схеме, подобранной врачом по весу питомца."
        ),
        cautions=[
            "наносить строго на кожу, не на шерсть",
            "не мыть кошку 2 суток после нанесения",
            "не давать животным слизывать препарат друг у друга",
        ],
        contraindications=["котята младше 6 недель", "истощённые и больные животные"],
        prescription_only=False,
    ),
    "fipronil": Medication(
        code="fipronil",
        name="Фипронил",
        group="Наружное средство от блох и клещей",
        brands=["Фронтлайн", "Фиприст"],
        forms=["капли на кожу", "спрей"],
        indications=["блохи", "иксодовые клещи", "власоеды"],
        dose_reference="По весу животного согласно инструкции к конкретной пипетке.",
        cautions=[
            "обработать всех животных в доме и подстилки",
            "избегать контакта с глазами и слизистыми",
        ],
        contraindications=["котята младше 8 недель", "кормящие кошки без назначения врача"],
        prescription_only=False,
    ),
    "itraconazole": Medication(
        code="itraconazole",
        name="Итраконазол",
        group="Системный противогрибковый препарат",
        brands=["Итраконазол", "Ирунин по назначению врача"],
        forms=["капсулы", "суспензия"],
        indications=["дерматофития, стригущий лишай"],
        dose_reference=(
            "Литературная справка: 5 мг/кг по пульс-схеме, обычно неделя приёма "
            "и неделя перерыва. Схему определяет врач по результатам культуры."
        ),
        cautions=[
            "контроль печёночных показателей при длительном курсе",
            "требуется обработка помещения от спор",
        ],
        contraindications=["болезни печени", "беременность"],
    ),
    "miconazole_chlorhexidine": Medication(
        code="miconazole_chlorhexidine",
        name="Миконазол с хлоргексидином",
        group="Наружное противогрибковое и антисептическое средство",
        brands=["Маласеб", "Клинзол"],
        forms=["шампунь", "лосьон"],
        indications=["дерматофития", "малассезиозный дерматит", "поверхностная пиодермия"],
        dose_reference=(
            "Купание 2 раза в неделю, экспозиция 10 минут, затем тщательное смывание. "
            "Курс назначает врач."
        ),
        cautions=[
            "не допускать попадания в глаза и уши",
            "полностью высушить кошку после купания",
        ],
        contraindications=["открытые обширные раны"],
        prescription_only=False,
    ),
    "maropitant": Medication(
        code="maropitant",
        name="Маропитант",
        group="Противорвотное средство",
        brands=["Церениа"],
        forms=["раствор для инъекций", "таблетки"],
        indications=["рвота различного происхождения", "тошнота при укачивании"],
        dose_reference=(
            "Литературная справка: 1 мг/кг подкожно один раз в сутки, курс до 5 дней. "
            "Назначение только врачом, важно исключить непроходимость."
        ),
        cautions=[
            "нельзя применять как замену диагностике при повторной рвоте",
            "болезненность при подкожном введении, раствор хранят в холоде",
        ],
        contraindications=["подозрение на инородное тело и непроходимость"],
    ),
    "famotidine": Medication(
        code="famotidine",
        name="Фамотидин",
        group="Блокатор H2-рецепторов, снижение кислотности",
        brands=["Фамотидин"],
        forms=["таблетки", "раствор для инъекций"],
        indications=["гастрит", "поддержка при болезни почек", "эзофагит"],
        dose_reference="Литературная справка: 0,5-1 мг/кг один раз в сутки по назначению врача.",
        cautions=["эффект снижается при длительном непрерывном применении"],
        contraindications=["тяжёлая болезнь почек без коррекции дозы"],
    ),
    "lactulose": Medication(
        code="lactulose",
        name="Лактулоза",
        group="Осмотическое слабительное",
        brands=["Дюфалак", "Нормазе"],
        forms=["сироп"],
        indications=["запор", "поддержка при мегаколоне"],
        dose_reference=(
            "Литературная справка: 0,5 мл на кошку 2-3 раза в сутки, доза "
            "подбирается по консистенции стула вместе с врачом."
        ),
        cautions=["обязателен свободный доступ к воде", "при передозировке возможен понос"],
        contraindications=["подозрение на непроходимость", "обезвоживание"],
        prescription_only=False,
    ),
    "prazosin_alt": Medication(
        code="prazosin_alt",
        name="Празозин",
        group="Спазмолитик для мочевыводящих путей",
        brands=["Празозин по назначению врача"],
        forms=["капсулы"],
        indications=["расслабление уретры после устранения обструкции", "цистит с уретроспазмом"],
        dose_reference=(
            "Литературная справка: 0,25-0,5 мг на кошку 1-2 раза в сутки. "
            "Применяется исключительно по назначению врача после катетеризации."
        ),
        cautions=[
            "может снижать давление и вызывать слабость",
            "не заменяет экстренную помощь при закупорке уретры",
        ],
        contraindications=["обезвоживание", "низкое артериальное давление"],
    ),
    "prednisolone": Medication(
        code="prednisolone",
        name="Преднизолон",
        group="Кортикостероид, противовоспалительное и иммуносупрессивное",
        brands=["Преднизолон"],
        forms=["таблетки", "раствор для инъекций"],
        indications=["аллергический дерматит", "астма", "аутоиммунные состояния"],
        dose_reference=(
            "Литературная справка: 0,5-2 мг/кг в сутки со снижением дозы. "
            "Кошкам назначают именно преднизолон, а не преднизон."
        ),
        cautions=[
            "нельзя отменять резко после длительного курса",
            "риск диабета и обострения инфекций",
            "не комбинировать с НПВС",
        ],
        contraindications=["инфекция без антибиотикотерапии", "диабет", "беременность"],
    ),
    "l_lysine": Medication(
        code="l_lysine",
        name="L-лизин",
        group="Аминокислотная добавка поддержки при герпесвирусе",
        brands=["Виралис", "L-Lysine для кошек"],
        forms=["паста", "порошок", "таблетки"],
        indications=["поддержка при рецидивах герпесвируса FHV-1"],
        dose_reference=(
            "Литературная справка: 250-500 мг на кошку в сутки. Доказательная база "
            "ограничена, не заменяет основное лечение."
        ),
        cautions=["не отменяет необходимость обследования при рецидивах"],
        contraindications=[],
        prescription_only=False,
    ),
    "methimazole": Medication(
        code="methimazole",
        name="Тиамазол (метимазол)",
        group="Антитиреоидный препарат",
        brands=["Фелимазол", "Тирозол по назначению врача"],
        forms=["таблетки", "трансдермальный гель"],
        indications=["гипертиреоз кошек"],
        dose_reference=(
            "Литературная справка: 1,25-2,5 мг на кошку 1-2 раза в сутки с контролем "
            "T4 через 2-3 недели. Назначает только врач по анализам."
        ),
        cautions=[
            "нужен контроль крови и гормонов на курсе",
            "возможен зуд лица, снижение аппетита",
        ],
        contraindications=["выраженные болезни печени и крови"],
    ),
    "renal_diet": Medication(
        code="renal_diet",
        name="Ренальная диета",
        group="Лечебное питание",
        brands=["Royal Canin Renal", "Hill's k/d", "Purina NF"],
        forms=["влажный рацион", "сухой рацион"],
        indications=["хроническая болезнь почек", "поддержка после обострений"],
        dose_reference=(
            "Норма по весу и стадии болезни, обязательно повышенное потребление воды. "
            "Диету и стадию определяет врач по анализам."
        ),
        cautions=["перевод на диету плавный, 7-10 дней", "не подходит котятам и беременным"],
        contraindications=["период роста", "беременность и лактация"],
        prescription_only=False,
    ),
}


@dataclass(frozen=True)
class ToxicSubstance:
    name: str
    why_dangerous: str
    note: str


TOXIC_FOR_CATS: List[ToxicSubstance] = [
    ToxicSubstance(
        name="Парацетамол (ацетаминофен)",
        why_dangerous="Разрушает гемоглобин и клетки печени, смертелен в дозе одной таблетки.",
        note="Даже четверть таблетки опасна. Немедленно в клинику при подозрении.",
    ),
    ToxicSubstance(
        name="Ибупрофен и другие человеческие НПВС",
        why_dangerous="Вызывает язвы желудка и острую почечную недостаточность.",
        note="У кошек нет безопасной домашней дозы.",
    ),
    ToxicSubstance(
        name="Аспирин без назначения врача",
        why_dangerous="Метаболизируется у кошек в 5-6 раз медленнее, легко накапливается.",
        note="Применяется только по расчёту врача в особых случаях.",
    ),
    ToxicSubstance(
        name="Перметрин и средства для собак",
        why_dangerous="Вызывает тремор и судороги, кошки не выводят пиретроиды.",
        note="Никогда не применять собачьи капли на кошках, смывать при попадании.",
    ),
    ToxicSubstance(
        name="Эфирные масла, масло чайного дерева",
        why_dangerous="Токсичны для печени и нервной системы, всасываются через кожу.",
        note="Опасны и в диффузорах, и в шампунях.",
    ),
    ToxicSubstance(
        name="Лилии и их пыльца",
        why_dangerous="Острая почечная недостаточность даже от нескольких пылинок.",
        note="Убрать растение из дома полностью.",
    ),
    ToxicSubstance(
        name="Антифриз (этиленгликоль)",
        why_dangerous="Смертельное поражение почек, сладкий вкус привлекает животных.",
        note="Счёт идёт на часы, нужна экстренная помощь.",
    ),
    ToxicSubstance(
        name="Лук, чеснок, шоколад",
        why_dangerous="Гемолиз, поражение сердца и нервной системы.",
        note="Исключить из рациона в любом виде, включая порошки и соусы.",
    ),
    ToxicSubstance(
        name="Хлорофос, изониазид, крысиный яд",
        why_dangerous="Судороги, кровотечения, отравление часто без ранних симптомов.",
        note="При подозрении взять упаковку и ехать в клинику.",
    ),
]


@dataclass(frozen=True)
class DiseaseProfile:
    """Профиль вероятного состояния и связанные с ним справочные данные."""

    code: str
    name: str
    latin: str
    zones: List[BodyZone]
    sign_weights: Dict[str, float]
    key_signs: List[str]
    urgency: Urgency
    description: str
    diagnostics: List[str]
    home_care: List[str]
    medication_codes: List[str]
    zoonotic: bool = False
    notes: str = ""
    supporting_signs: Dict[str, float] = field(default_factory=dict)


DISEASES: Dict[str, DiseaseProfile] = {
    "conjunctivitis_fhv": DiseaseProfile(
        code="conjunctivitis_fhv",
        name="Конъюнктивит, часто герпесвирусный",
        latin="Conjunctivitis, FHV-1",
        zones=[BodyZone.EYES, BodyZone.RESPIRATORY],
        sign_weights={
            "eye_redness": 3.0,
            "eye_discharge": 3.0,
            "eye_squint": 2.0,
            "nose_discharge": 1.5,
            "eye_third_eyelid": 1.0,
            "appetite_loss": 0.5,
        },
        key_signs=["eye_redness", "eye_discharge"],
        urgency=Urgency.SOON,
        description=(
            "Воспаление слизистой глаза. У кошек чаще связано с герпесвирусом FHV-1, "
            "хламидиями или микоплазмой, нередко сочетается с чиханием."
        ),
        diagnostics=[
            "осмотр глаза с окраской флуоресцеином для исключения язвы роговицы",
            "тест Ширмера при сухости глаза",
            "ПЦР смыва на герпесвирус, хламидии, микоплазму",
        ],
        home_care=[
            "промывать глаза физраствором отдельным тампоном для каждого глаза",
            "снизить стресс, изолировать от других кошек до осмотра",
            "не применять капли с кортикостероидами без осмотра врача",
        ],
        medication_codes=["saline_rinse", "tetracycline_eye", "doxycycline", "l_lysine"],
        notes="Капли с гормонами при язве роговицы могут привести к потере глаза.",
    ),
    "corneal_ulcer": DiseaseProfile(
        code="corneal_ulcer",
        name="Язва или травма роговицы",
        latin="Ulcus corneae",
        zones=[BodyZone.EYES],
        sign_weights={
            "eye_cornea_cloudy": 3.5,
            "eye_squint": 3.0,
            "eye_discharge": 1.5,
            "eye_redness": 1.5,
            "eye_third_eyelid": 1.0,
        },
        key_signs=["eye_squint", "eye_cornea_cloudy"],
        urgency=Urgency.URGENT,
        description=(
            "Повреждение поверхности глаза после травмы или на фоне вирусной инфекции. "
            "Может быстро прогрессировать до перфорации."
        ),
        diagnostics=[
            "окраска флуоресцеином",
            "измерение внутриглазного давления",
            "осмотр щелевой лампой",
        ],
        home_care=[
            "надеть защитный воротник, чтобы кошка не травмировала глаз",
            "не тереть глаз, не капать препараты с гормонами",
            "показать врачу в течение суток",
        ],
        medication_codes=["saline_rinse", "tetracycline_eye", "meloxicam"],
        notes="Мутность роговицы и зажмуренный глаз это показание к срочному осмотру.",
    ),
    "otodectosis": DiseaseProfile(
        code="otodectosis",
        name="Ушной клещ, отодектоз",
        latin="Otodectes cynotis",
        zones=[BodyZone.EARS],
        sign_weights={
            "ear_dark_debris": 3.5,
            "ear_head_shaking": 3.0,
            "ear_redness_swelling": 1.5,
            "skin_itching": 1.0,
        },
        key_signs=["ear_dark_debris"],
        urgency=Urgency.SOON,
        description=(
            "Паразитарное поражение наружного слухового прохода. Характерен сухой "
            "тёмный налёт, похожий на кофейную крошку, и сильный зуд."
        ),
        diagnostics=[
            "микроскопия ушного соскоба",
            "отоскопия для оценки целостности барабанной перепонки",
        ],
        home_care=[
            "не чистить ухо палочками глубоко, только видимую часть",
            "обработать всех животных в доме",
        ],
        medication_codes=["selamectin", "miconazole_chlorhexidine"],
        notes="Часто заражаются все животные в доме, лечить нужно всех одновременно.",
    ),
    "otitis_externa": DiseaseProfile(
        code="otitis_externa",
        name="Наружный отит",
        latin="Otitis externa",
        zones=[BodyZone.EARS],
        sign_weights={
            "ear_redness_swelling": 3.0,
            "ear_smell_discharge": 3.0,
            "ear_head_shaking": 2.0,
            "neuro_head_tilt": 1.5,
        },
        key_signs=["ear_redness_swelling", "ear_smell_discharge"],
        urgency=Urgency.SOON,
        description=(
            "Воспаление наружного слухового прохода бактериальной или грибковой природы, "
            "часто вторично к аллергии или паразитам."
        ),
        diagnostics=[
            "цитология выделений из уха",
            "отоскопия",
            "посев при рецидивах",
        ],
        home_care=[
            "не капать спиртовые растворы",
            "не назначать капли самостоятельно при наклоне головы",
        ],
        medication_codes=["miconazole_chlorhexidine", "amoxiclav", "meloxicam"],
        notes="При повреждённой перепонке многие ушные капли противопоказаны.",
    ),
    "dermatophytosis": DiseaseProfile(
        code="dermatophytosis",
        name="Дерматофития, стригущий лишай",
        latin="Microsporum canis",
        zones=[BodyZone.SKIN],
        sign_weights={
            "skin_hair_loss_patch": 3.5,
            "skin_scaling_crust": 2.5,
            "skin_itching": 1.0,
            "coat_dull": 1.0,
        },
        key_signs=["skin_hair_loss_patch"],
        urgency=Urgency.SOON,
        description=(
            "Грибковое поражение кожи и шерсти. Типичны округлые очаги с обломанным "
            "волосом и шелушением, часто на морде, ушах и лапах."
        ),
        diagnostics=[
            "осмотр лампой Вуда",
            "трихограмма, микроскопия волоса",
            "посев на среду для дерматофитов, это основной метод",
        ],
        home_care=[
            "ограничить контакт с детьми и другими животными",
            "обрабатывать поверхности, убрать текстиль и когтеточки",
            "мыть руки после контакта",
        ],
        medication_codes=["itraconazole", "miconazole_chlorhexidine"],
        zoonotic=True,
        notes="Заразно для человека, обязательна обработка помещения от спор.",
    ),
    "flea_allergy_dermatitis": DiseaseProfile(
        code="flea_allergy_dermatitis",
        name="Блошиный аллергический дерматит",
        latin="Flea allergy dermatitis",
        zones=[BodyZone.SKIN],
        sign_weights={
            "skin_black_specks": 3.5,
            "skin_itching": 3.0,
            "skin_miliary_bumps": 2.5,
            "skin_hair_loss_patch": 1.5,
            "skin_scaling_crust": 1.0,
        },
        key_signs=["skin_itching"],
        urgency=Urgency.ROUTINE,
        description=(
            "Аллергия на слюну блох. Достаточно единичных укусов, чтобы вызвать "
            "сильный зуд, узелковую сыпь и вылизывание шерсти на спине и бёдрах."
        ),
        diagnostics=[
            "вычёсывание частым гребнем, тест с влажной салфеткой на экскременты блох",
            "исключение дерматофитии и пищевой аллергии",
        ],
        home_care=[
            "обработать всех животных в доме и подстилки",
            "пропылесосить и вымыть места отдыха",
        ],
        medication_codes=["selamectin", "fipronil", "prednisolone"],
        notes="Гормоны только по назначению врача и только после обработки от блох.",
    ),
    "abscess_bite_wound": DiseaseProfile(
        code="abscess_bite_wound",
        name="Абсцесс или инфицированная рана после укуса",
        latin="Abscessus",
        zones=[BodyZone.SKIN, BodyZone.GENERAL],
        sign_weights={
            "skin_wound_swelling": 3.5,
            "appetite_loss": 1.5,
            "neuro_hiding": 1.5,
            "limping": 1.0,
            "coat_dull": 0.5,
        },
        key_signs=["skin_wound_swelling"],
        urgency=Urgency.URGENT,
        description=(
            "Гнойное скопление под кожей, обычно после драки. Горячая болезненная "
            "припухлость, иногда со свищом и повышением температуры."
        ),
        diagnostics=[
            "осмотр и пункция очага",
            "оценка температуры тела",
            "тесты на вирусы иммунодефицита и лейкоза при драках",
        ],
        home_care=[
            "не выдавливать и не греть очаг",
            "промыть поверхность физраствором, надеть воротник",
        ],
        medication_codes=["amoxiclav", "meloxicam", "saline_rinse"],
        notes="Абсцесс требует хирургического дренирования, антибиотик один не решает проблему.",
    ),
    "stomatitis_dental": DiseaseProfile(
        code="stomatitis_dental",
        name="Стоматит и болезни зубов",
        latin="Gingivostomatitis",
        zones=[BodyZone.MOUTH],
        sign_weights={
            "mouth_gum_redness": 3.0,
            "mouth_drooling": 2.5,
            "mouth_tartar": 2.0,
            "mouth_ulcers": 2.5,
            "appetite_loss": 1.5,
            "weight_loss": 1.0,
        },
        key_signs=["mouth_gum_redness", "mouth_ulcers", "mouth_drooling"],
        urgency=Urgency.SOON,
        description=(
            "Воспаление дёсен и слизистой рта, зубной камень, резорбтивные поражения зубов. "
            "Частая причина боли, отказа от твёрдого корма и слюнотечения."
        ),
        diagnostics=[
            "осмотр рта под седацией",
            "дентальные рентгеновские снимки",
            "тесты на вирусы иммунодефицита и лейкоза, кальцивирус",
        ],
        home_care=[
            "перевести на влажный корм до осмотра",
            "не пытаться чистить воспалённые дёсны щёткой",
        ],
        medication_codes=["meloxicam", "amoxiclav", "prednisolone"],
        notes="Основное лечение это санация рта у стоматолога, препараты снимают боль.",
    ),
    "urinary_obstruction": DiseaseProfile(
        code="urinary_obstruction",
        name="Закупорка уретры и болезни нижних мочевых путей",
        latin="FLUTD, urethral obstruction",
        zones=[BodyZone.URINARY],
        sign_weights={
            "urine_straining": 4.0,
            "urine_crying": 3.5,
            "urine_blood": 3.0,
            "appetite_loss": 1.5,
            "vomiting": 1.5,
            "abdomen_distended": 2.0,
        },
        key_signs=["urine_straining", "urine_crying", "urine_blood"],
        urgency=Urgency.EMERGENCY,
        description=(
            "Кристаллы, пробка или спазм перекрывают отток мочи. У котов состояние "
            "смертельно опасно и приводит к отравлению организма за 24-48 часов."
        ),
        diagnostics=[
            "осмотр и пальпация мочевого пузыря",
            "УЗИ мочевого пузыря и почек",
            "анализ мочи, биохимия, калий крови",
        ],
        home_care=[
            "немедленно в клинику, дома помочь нельзя",
            "не давать спазмолитики и обезболивающие без врача",
            "не задерживать поездку из-за отсутствия анализов",
        ],
        medication_codes=["prazosin_alt", "meloxicam", "renal_diet"],
        notes="Если кот тужится и моча не идёт, это счёт на часы, а не на дни.",
    ),
    "ckd": DiseaseProfile(
        code="ckd",
        name="Хроническая болезнь почек",
        latin="Chronic kidney disease",
        zones=[BodyZone.URINARY, BodyZone.GENERAL],
        sign_weights={
            "urine_increased": 3.0,
            "weight_loss": 2.5,
            "coat_dull": 2.0,
            "appetite_loss": 2.0,
            "vomiting": 1.5,
            "dehydration": 2.0,
            "mouth_ulcers": 1.0,
        },
        key_signs=["urine_increased", "weight_loss"],
        urgency=Urgency.SOON,
        description=(
            "Постепенная утрата функции почек, чаще у кошек старше 8 лет. Типичны "
            "жажда, увеличенный объём мочи, похудание и тусклая шерсть."
        ),
        diagnostics=[
            "биохимия крови с креатинином и SDMA",
            "анализ мочи с плотностью и соотношением белок-креатинин",
            "измерение давления, УЗИ почек",
        ],
        home_care=[
            "обеспечить свободный доступ к воде, добавить фонтанчик",
            "перейти на влажные рационы",
            "взвешивать кошку раз в 2 недели и записывать вес",
        ],
        medication_codes=["renal_diet", "famotidine", "maropitant"],
        notes="НПВС при болезни почек назначают крайне осторожно и только врачом.",
    ),
    "hyperthyroidism": DiseaseProfile(
        code="hyperthyroidism",
        name="Гипертиреоз",
        latin="Hyperthyroidismus felinum",
        zones=[BodyZone.GENERAL],
        sign_weights={
            "weight_loss": 3.0,
            "neuro_hyperactive": 3.0,
            "coat_dull": 2.0,
            "vomiting": 1.5,
            "urine_increased": 1.5,
            "diarrhea": 1.0,
        },
        key_signs=["weight_loss", "neuro_hyperactive"],
        urgency=Urgency.SOON,
        description=(
            "Избыток тиреоидных гормонов у кошек среднего и старшего возраста. "
            "Кошка много ест, но худеет, становится крикливой и беспокойной."
        ),
        diagnostics=[
            "общий T4 и свободный T4",
            "биохимия, оценка функции почек",
            "давление, эхокардиография",
        ],
        home_care=[
            "калорийное питание до визита к врачу",
            "снизить стресс, обеспечить тишину и тепло",
        ],
        medication_codes=["methimazole"],
        notes="Похудание при хорошем аппетите это повод сдать гормоны щитовидной железы.",
    ),
    "respiratory_distress": DiseaseProfile(
        code="respiratory_distress",
        name="Дыхательная недостаточность, выпот или астма",
        latin="Dyspnoea, pleural effusion, asthma",
        zones=[BodyZone.RESPIRATORY],
        sign_weights={
            "breathing_open_mouth": 4.0,
            "breathing_abdominal": 3.5,
            "cough": 2.0,
            "mouth_pale_gums": 2.0,
            "neuro_hiding": 1.0,
            "appetite_loss": 1.0,
        },
        key_signs=["breathing_open_mouth", "breathing_abdominal"],
        urgency=Urgency.EMERGENCY,
        description=(
            "Кошки почти никогда не дышат ртом без причины. Это признак жидкости в "
            "грудной клетке, отёка лёгких, астмы или анемии."
        ),
        diagnostics=[
            "оксигенация и осмотр в кислороде",
            "УЗИ грудной клетки и сердца",
            "рентген после стабилизации",
        ],
        home_care=[
            "немедленно в клинику, транспортировка в переноске без стресса",
            "не открывать рот, не давать воду насильно",
            "по возможности предупредить клинику звонком заранее",
        ],
        medication_codes=["prednisolone"],
        notes="Любые манипуляции могут ухудшить состояние, минимизируйте стресс.",
    ),
    "upper_respiratory_infection": DiseaseProfile(
        code="upper_respiratory_infection",
        name="Инфекция верхних дыхательных путей",
        latin="Feline upper respiratory infection",
        zones=[BodyZone.RESPIRATORY, BodyZone.EYES],
        sign_weights={
            "nose_discharge": 3.5,
            "eye_discharge": 2.5,
            "appetite_loss": 2.0,
            "mouth_ulcers": 1.5,
            "eye_redness": 1.5,
            "mouth_drooling": 1.0,
        },
        key_signs=["nose_discharge"],
        urgency=Urgency.SOON,
        description=(
            "Комплекс инфекций с герпесвирусом, кальцивирусом, хламидиями. Чихание, "
            "выделения из носа и глаз, иногда язвы в рту."
        ),
        diagnostics=[
            "клинический осмотр и оценка дыхания",
            "ПЦР смывов из носа и глаз",
            "рентген при затяжном течении",
        ],
        home_care=[
            "промывать нос и глаза физраствором",
            "увлажнять воздух, подогревать пахучий влажный корм",
            "изолировать от других кошек",
        ],
        medication_codes=["saline_rinse", "doxycycline", "l_lysine", "amoxiclav"],
        notes="Полный отказ от еды более суток у кошки требует срочного визита.",
    ),
    "jaundice_liver": DiseaseProfile(
        code="jaundice_liver",
        name="Желтуха, поражение печени или гемолиз",
        latin="Icterus",
        zones=[BodyZone.GENERAL, BodyZone.MOUTH],
        sign_weights={
            "mucosa_yellow": 4.0,
            "appetite_loss": 2.5,
            "vomiting": 2.0,
            "weight_loss": 1.5,
            "neuro_hiding": 1.5,
            "dehydration": 1.5,
        },
        key_signs=["mucosa_yellow"],
        urgency=Urgency.EMERGENCY,
        description=(
            "Жёлтый оттенок слизистых и кожи говорит о накоплении билирубина при болезни "
            "печени, желчных путей или разрушении эритроцитов."
        ),
        diagnostics=[
            "биохимия с билирубином и печёночными ферментами",
            "общий анализ крови",
            "УЗИ брюшной полости",
        ],
        home_care=[
            "срочно в клинику, кошка не должна голодать",
            "не давать никаких препаратов до осмотра",
        ],
        medication_codes=["maropitant", "famotidine"],
        notes="Отказ от еды при желтухе быстро приводит к липидозу печени.",
    ),
    "anemia": DiseaseProfile(
        code="anemia",
        name="Анемия",
        latin="Anaemia",
        zones=[BodyZone.GENERAL],
        sign_weights={
            "mouth_pale_gums": 4.0,
            "neuro_hiding": 2.0,
            "appetite_loss": 2.0,
            "breathing_abdominal": 2.0,
            "coat_dull": 1.0,
            "hypothermia_collapse": 2.5,
        },
        key_signs=["mouth_pale_gums"],
        urgency=Urgency.EMERGENCY,
        description=(
            "Снижение количества эритроцитов при кровопотере, гемолизе, болезни почек "
            "или инфекциях. Слизистые становятся бледными, появляется слабость."
        ),
        diagnostics=[
            "общий анализ крови с ретикулоцитами",
            "мазок крови на гемопаразитов",
            "тесты на вирусы лейкоза и иммунодефицита",
        ],
        home_care=[
            "минимум движения, тепло и покой, срочно в клинику",
            "не давать препараты железа без назначения",
        ],
        medication_codes=["doxycycline", "prednisolone"],
        notes="Бледные дёсны плюс слабость это показание к экстренному приёму.",
    ),
    "trauma_lameness": DiseaseProfile(
        code="trauma_lameness",
        name="Травма конечности, хромота",
        latin="Trauma, lameness",
        zones=[BodyZone.LOCOMOTION],
        sign_weights={
            "limping": 3.5,
            "joint_swelling": 3.0,
            "jump_refusal": 2.0,
            "neuro_hiding": 1.0,
            "skin_wound_swelling": 1.5,
        },
        key_signs=["limping", "joint_swelling"],
        urgency=Urgency.URGENT,
        description=(
            "Ушиб, вывих, перелом или повреждение когтя. Кошки хорошо скрывают боль, "
            "поэтому даже лёгкая хромота требует осмотра."
        ),
        diagnostics=[
            "ортопедический осмотр",
            "рентген конечности в двух проекциях",
            "осмотр подушечек и когтей",
        ],
        home_care=[
            "ограничить прыжки, закрыть доступ на высоту",
            "не давать человеческие обезболивающие",
            "приложить прохладу к отёку на 5-10 минут, без льда напрямую",
        ],
        medication_codes=["meloxicam", "gabapentin"],
        notes="После падения с высоты нужен осмотр даже при отсутствии видимых травм.",
    ),
    "vestibular_neuro": DiseaseProfile(
        code="vestibular_neuro",
        name="Вестибулярный синдром или неврологическое расстройство",
        latin="Vestibular syndrome",
        zones=[BodyZone.NEURO],
        sign_weights={
            "neuro_head_tilt": 3.5,
            "neuro_ataxia": 3.5,
            "neuro_seizure": 3.0,
            "eye_pupil_asymmetry": 2.0,
            "vomiting": 1.0,
            "ear_smell_discharge": 1.0,
        },
        key_signs=["neuro_head_tilt", "neuro_ataxia", "neuro_seizure"],
        urgency=Urgency.EMERGENCY,
        description=(
            "Нарушение равновесия и координации при поражении внутреннего уха или мозга. "
            "Возможны наклон головы, шаткость, подёргивание глаз, судороги."
        ),
        diagnostics=[
            "неврологический осмотр",
            "отоскопия и оценка среднего уха",
            "давление, анализы крови, при необходимости МРТ",
        ],
        home_care=[
            "убрать доступ к высоте и лестницам, застелить пол",
            "снять видео приступа для врача",
            "не кормить насильно при шаткости, риск аспирации",
        ],
        medication_codes=["maropitant", "gabapentin", "prednisolone"],
        notes="Судороги дольше 2-3 минут или серия приступов это экстренное состояние.",
    ),
    "constipation": DiseaseProfile(
        code="constipation",
        name="Запор, риск мегаколона",
        latin="Constipation, megacolon",
        zones=[BodyZone.GI],
        sign_weights={
            "abdomen_distended": 2.5,
            "appetite_loss": 2.0,
            "vomiting": 1.5,
            "urine_straining": 1.5,
            "dehydration": 1.5,
            "weight_loss": 1.0,
        },
        key_signs=["abdomen_distended"],
        urgency=Urgency.URGENT,
        description=(
            "Отсутствие стула более 48 часов с натуживанием. Важно отличить от закупорки "
            "уретры, при которой натуживание тоже выглядит похоже."
        ),
        diagnostics=[
            "пальпация живота",
            "рентген или УЗИ брюшной полости",
            "оценка обезвоживания и электролитов",
        ],
        home_care=[
            "увеличить потребление воды, добавить влажный корм",
            "не давать человеческие слабительные и клизмы без врача",
        ],
        medication_codes=["lactulose", "renal_diet", "maropitant"],
        notes="Если кошка тужится в лотке, сначала исключают закупорку мочевых путей.",
    ),
    "obesity_metabolic": DiseaseProfile(
        code="obesity_metabolic",
        name="Избыточный вес и метаболические риски",
        latin="Obesitas",
        zones=[BodyZone.GENERAL],
        sign_weights={
            "obesity": 3.5,
            "jump_refusal": 2.0,
            "coat_dull": 1.5,
            "urine_increased": 1.0,
        },
        key_signs=["obesity"],
        urgency=Urgency.ROUTINE,
        description=(
            "Избыточная масса повышает риск диабета, болезней суставов и печени. "
            "Оценивается по шкале упитанности от 1 до 9."
        ),
        diagnostics=[
            "оценка упитанности и взвешивание",
            "глюкоза и фруктозамин крови",
            "расчёт суточной калорийности",
        ],
        home_care=[
            "перейти на порционное кормление по весу, убрать корм в свободном доступе",
            "добавить игровую активность и кормушки-головоломки",
            "снижать вес плавно, не более 1 процента массы в неделю",
        ],
        medication_codes=["renal_diet"],
        notes="Резкое голодание у кошек опасно и может вызвать липидоз печени.",
    ),
    "feline_acne": DiseaseProfile(
        code="feline_acne",
        name="Акне подбородка",
        latin="Acne felinae",
        zones=[BodyZone.SKIN],
        sign_weights={
            "skin_chin_blackheads": 3.5,
            "skin_scaling_crust": 1.5,
            "skin_itching": 1.0,
        },
        key_signs=["skin_chin_blackheads"],
        urgency=Urgency.ROUTINE,
        description=(
            "Закупорка волосяных фолликулов на подбородке с чёрными точками, иногда с "
            "воспалением. Часто связано с пластиковыми мисками."
        ),
        diagnostics=[
            "цитология и микроскопия соскоба",
            "исключение дерматофитии и демодекоза",
        ],
        home_care=[
            "заменить пластиковые миски на стекло или сталь, мыть их ежедневно",
            "аккуратно обрабатывать подбородок по назначению врача",
        ],
        medication_codes=["miconazole_chlorhexidine", "amoxiclav"],
        notes="Не выдавливать элементы, это усиливает воспаление.",
    ),
}


RED_FLAG_SIGNS: List[str] = [code for code, sign in SIGNS.items() if sign.is_red_flag]

EMERGENCY_CHECKLIST: List[str] = [
    "дыхание открытым ртом, тяжёлое дыхание животом",
    "кот тужится в лотке, а моча не выходит",
    "судороги, потеря сознания, шаткая походка",
    "бледные или жёлтые слизистые",
    "отказ от еды более 24 часов",
    "непрекращающаяся рвота, раздутый напряжённый живот",
    "травма после падения с высоты или удара",
    "подозрение на отравление, доступ к лилиям или бытовой химии",
    "температура ниже 37 или выше 39,5 градусов",
    "обильное кровотечение, которое не останавливается 5 минут",
]

FIRST_AID_RULES: List[str] = [
    "Первое правило: никаких человеческих обезболивающих. Парацетамол и ибупрофен смертельны для кошек.",
    "Кровотечение: чистая марля и давление на рану 5 минут, не снимая для проверки, затем в клинику.",
    "Рана: промыть физраствором, надеть воротник, не заливать спирт, перекись и зелёнку в глубокие раны.",
    "Тепловой удар: убрать в прохладу, обтереть лапы и живот водой комнатной температуры, не льдом.",
    "Отравление: не вызывать рвоту самостоятельно, взять упаковку вещества и ехать в клинику.",
    "Судороги: убрать предметы вокруг, ничего не вкладывать в рот, засечь время и снять видео.",
    "Проблемы с дыханием: минимум манипуляций, переноска, открытая вентиляция, срочно в клинику.",
    "Перевозка при травме: жёсткая основа, коробка или переноска, минимум движений и шума.",
    "Отказ от еды: не кормить насильно, если есть рвота или шаткость, риск аспирации.",
    "Всегда держите под рукой адрес круглосуточной клиники и вес питомца, они нужны для расчёта дозы.",
]


def signs_by_zone(zone: BodyZone) -> List[VisualSign]:
    """Возвращает список признаков конкретной зоны в порядке объявления."""
    return [sign for sign in SIGNS.values() if sign.zone == zone]


def get_sign(code: str) -> Optional[VisualSign]:
    return SIGNS.get(code)


def get_disease(code: str) -> Optional[DiseaseProfile]:
    return DISEASES.get(code)


def get_medication(code: str) -> Optional[Medication]:
    return MEDICATIONS.get(code)


def medication_groups() -> Dict[str, List[Medication]]:
    """Группирует препараты по фармакологической группе для меню справочника."""
    groups: Dict[str, List[Medication]] = {}
    for med in MEDICATIONS.values():
        groups.setdefault(med.group, []).append(med)
    return groups
