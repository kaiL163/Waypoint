from __future__ import annotations

WORK_NORMS = [
    {
        "id": "connection",
        "title": "Подключение клиентов · базовая",
        "travelMinutes": 20,
        "technicalMinutes": 60,
        "documentsMinutes": 10,
        "totalMinutes": 90,
        "skill": "Подключение",
        "keywords": ["подключ", "конвергенц", "гбит"],
    },
    {
        "id": "tkd-incident",
        "title": "Авария на ТКД",
        "travelMinutes": 20,
        "technicalMinutes": 80,
        "documentsMinutes": 0,
        "totalMinutes": 100,
        "skill": "Аварийные работы",
        "keywords": ["авари", "нет линка", "разрыв", "ошибок", "низкая скорость", "кабел"],
    },
    {
        "id": "equipment",
        "title": "Дозаказ оборудования",
        "travelMinutes": 20,
        "technicalMinutes": 10,
        "documentsMinutes": 10,
        "totalMinutes": 40,
        "skill": "Подключение",
        "keywords": ["дозаказ", "роутер", "приставк"],
    },
    {
        "id": "local",
        "title": "Локальная заявка / ремонт у клиента",
        "travelMinutes": 20,
        "technicalMinutes": 30,
        "documentsMinutes": 0,
        "totalMinutes": 50,
        "skill": "Локальные работы",
        "keywords": ["локальн", "тв", "информац", "мониторинг"],
    },
]


def norm_for_work_type(work_type: str) -> dict:
    value = work_type.lower()
    for norm in WORK_NORMS:
        if any(keyword in value for keyword in norm["keywords"]):
            return norm
    return WORK_NORMS[3]
