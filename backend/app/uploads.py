from __future__ import annotations

import csv
import io
import json
import re

from fastapi import UploadFile

from .schemas import Dataset

NORMS = [
    (('подключ', 'конвергенц', 'гбит'), 70, 'Подключение'),
    (('авари', 'нет линка', 'разрыв', 'ошибок', 'низкая скорость', 'кабел'), 80, 'Аварийные работы'),
    (('дозаказ', 'роутер', 'приставк'), 20, 'Подключение'),
    (('локальн', 'тв', 'информац', 'мониторинг'), 30, 'Локальные работы'),
]


def decode(raw: bytes) -> str:
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return raw.decode('cp1251')


def csv_rows(body: str) -> list[dict[str, str]]:
    first = body.splitlines()[0] if body.splitlines() else ''
    delimiter = ';' if first.count(';') > first.count(',') else ','
    return [{key.strip(): (value or '').strip() for key, value in row.items() if key} for row in csv.DictReader(io.StringIO(body), delimiter=delimiter)]


def time_value(value: str) -> str:
    result = re.search(r'(?<!\d)([01]\d|2[0-3]):[0-5]\d', value)
    return result.group(0) if result else ''


def engineer(row: dict[str, str]) -> dict:
    return {'id': row.get('id'), 'name': row.get('name'), 'startLocation': {'lat': row.get('lat') or row.get('startLat'), 'lng': row.get('lng') or row.get('startLng')}, 'shiftStart': row.get('shiftStart') or '09:00', 'shiftEnd': row.get('shiftEnd') or '18:00', 'skills': [value.strip() for value in re.split(r'[;|]', row.get('skills', '')) if value.strip()], 'transport': row.get('transport') or 'car', 'available': row.get('available', '').lower() != 'false'}


def request(row: dict[str, str]) -> dict:
    return {'id': row.get('id'), 'location': {'lat': row.get('lat'), 'lng': row.get('lng'), 'address': row.get('address') or f"{row.get('lat')}, {row.get('lng')}"}, 'durationMinutes': row.get('durationMinutes'), 'windowStart': row.get('windowStart'), 'windowEnd': row.get('windowEnd'), 'priority': row.get('priority') or 'normal', 'requiredSkill': row.get('requiredSkill'), 'requiredTransport': row.get('requiredTransport') or None}


def beeline_request(row: dict[str, str]) -> dict:
    work_type = (row.get('Тип заявки HD') or row.get('Тип заявки BK') or '').lower()
    duration, skill = next(((duration, skill) for keywords, duration, skill in NORMS if any(word in work_type for word in keywords)), (30, 'Локальные работы'))
    lat, lng = row.get('lat') or row.get('Широта'), row.get('lng') or row.get('Долгота')
    if not lat or not lng:
        raise ValueError('Для заявок Билайн нужны столбцы lat/lng или Широта/Долгота.')
    return {'id': row.get('Заявка'), 'location': {'lat': lat, 'lng': lng, 'address': row.get('Адрес')}, 'durationMinutes': duration, 'windowStart': time_value(row.get('Начало', '')), 'windowEnd': time_value(row.get('Окончание', '')), 'priority': 'normal', 'requiredSkill': skill}


async def parse_uploads(files: list[UploadFile]) -> Dataset:
    engineers: list[dict] = []
    requests: list[dict] = []
    for file in files:
        name = (file.filename or '').lower()
        raw = await file.read()
        if len(raw) > 10_000_000:
            raise ValueError('Файл превышает лимит 10 МБ.')
        body = decode(raw)
        if name.endswith('.json'):
            data = json.loads(body)
            engineers.extend(data.get('engineers', []))
            requests.extend(data.get('requests', []))
        elif name.endswith('.csv'):
            rows = csv_rows(body)
            if not rows:
                continue
            if 'entity' in rows[0]:
                engineers.extend(engineer(row) for row in rows if row.get('entity') == 'engineer')
                requests.extend(request(row) for row in rows if row.get('entity') == 'request')
            elif 'Заявка' in rows[0] and ('Тип заявки HD' in rows[0] or 'Тип заявки BK' in rows[0]):
                requests.extend(beeline_request(row) for row in rows)
            elif 'engineer' in name or 'инженер' in name:
                engineers.extend(engineer(row) for row in rows)
            elif 'request' in name or 'заявк' in name:
                requests.extend(request(row) for row in rows)
            else:
                raise ValueError(f'Невозможно определить тип CSV: {file.filename}')
        else:
            raise ValueError('Поддерживаются только JSON и CSV.')
    return Dataset(engineers=engineers, requests=requests)
