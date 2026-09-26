from __future__ import annotations

import csv
import io
import json
import math
import re
from typing import Any

from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from .geocode import resolve_point
from .models import Dataset, Engineer, Point, RequestLocation, ServiceRequest, Transport
from .norms import norm_for_work_type

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TIME_FIND = re.compile(r"(?:^|\s)([01]\d|2[0-3]):[0-5]\d")


def _transport(value: str) -> Transport:
    aliases={'Автомобиль':'car','Пешеход':'walk','Пешком':'walk','Велосипед':'bike','Общественный транспорт':'transit'}
    value=aliases.get(value,value) or 'car'
    if value not in {'car','walk','bike','transit'}:
        raise ValueError(f'Неизвестный транспорт: {value}')
    return value


def _valid_time(value: str) -> bool:
    return bool(TIME_RE.match(value))


def _time_from(value: str) -> str:
    match = TIME_FIND.search(value or "")
    return match.group(0).strip() if match else ""


def validate_dataset(data: Dataset) -> Dataset:
    data=Dataset.model_validate(data.model_dump())
    if not data.engineers or not data.requests:
        raise HTTPException(status_code=400, detail="Список инженеров и заявок не должен быть пустым.")
    for engineer in data.engineers:
        if (
            not engineer.id
            or not engineer.name
            or not _valid_time(engineer.shiftStart)
            or not _valid_time(engineer.shiftEnd)
            or not engineer.skills
        ):
            raise HTTPException(status_code=400, detail=f"Некорректные данные инженера {engineer.id or ''}.")
    for request in data.requests:
        if (
            not request.id
            or request.durationMinutes <= 0
            or not _valid_time(request.windowStart)
            or not _valid_time(request.windowEnd)
            or request.windowStart > request.windowEnd
            or not request.requiredSkill
        ):
            raise HTTPException(status_code=400, detail=f"Некорректные данные заявки {request.id or ''}.")
    engineers = [
        engineer.model_copy(
            update={
                "available": engineer.available is not False,
                "transport": engineer.transport or "car",
            }
        )
        for engineer in data.engineers
    ]
    requests = [
        request.model_copy(
            update={
                "location": request.location.model_copy(
                    update={
                        "address": request.location.address
                        or f"{request.location.lat:.4f}, {request.location.lng:.4f}"
                    }
                ),
                "priority": request.priority or "normal",
            }
        )
        for request in data.requests
    ]
    return Dataset(engineers=engineers, requests=requests,importWarnings=data.importWarnings,revision=data.revision)


def _decode_bytes(raw: bytes) -> str:
    if not raw:
        return ""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    for encoding in ("utf-8", "cp1251", "cp866", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _parse_csv(text: str) -> list[dict[str, str]]:
    sample = text.splitlines()[0] if text else ""
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows: list[dict[str, str]] = []
    for row in reader:
        cleaned = {(k or "").strip().lstrip("\ufeff"): (v or "").strip() for k, v in row.items()}
        if any(cleaned.values()):
            rows.append(cleaned)
    return rows


def _row_get(row: dict[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        if key in row and row[key] != "":
            return row[key]
        lower = {k.lower(): v for k, v in row.items()}
        if key.lower() in lower and lower[key.lower()] != "":
            return lower[key.lower()]
    return default


def _to_engineer(row: dict[str, str]) -> Engineer:
    try:
        return Engineer(
            id=_row_get(row, "id"),
            name=_row_get(row, "name"),
            startLocation={
                "lat": float(_row_get(row, "lat", "startLat", "широта") or "nan"),
                "lng": float(_row_get(row, "lng", "startLng", "долгота") or "nan"),
            },
            shiftStart=_row_get(row, "shiftStart", default="09:00") or "09:00",
            shiftEnd=_row_get(row, "shiftEnd", default="18:00") or "18:00",
            skills=[s.strip() for s in re.split(r"[;|]", _row_get(row, "skills")) if s.strip()],
            transport=_transport(_row_get(row, "transport") or "car"),
            available=_row_get(row, "available").lower() not in {"false", "0", "нет", "no"},
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Некорректная строка инженера (id={_row_get(row, 'id') or '?'}): {exc}",
        ) from exc


def _to_request(row: dict[str, str]) -> ServiceRequest:
    try:
        lat = float(_row_get(row, "lat", "широта") or "nan")
        lng = float(_row_get(row, "lng", "долгота") or "nan")
        estimated=not math.isfinite(lat) or not math.isfinite(lng)
        if estimated:
            address=_row_get(row,'address','адрес')
            if not address:
                raise ValueError('Нужны координаты или адрес.')
            lat,lng=resolve_point(address,use_network=False)
        required_transport = _row_get(row, "requiredTransport")
        return ServiceRequest(
            id=_row_get(row, "id"),
            location=RequestLocation(
                lat=lat,
                lng=lng,
                address=_row_get(row, "address", "адрес") or f"{lat}, {lng}",
                estimated=estimated,
            ),
            durationMinutes=float(_row_get(row, "durationMinutes") or "0"),
            windowStart=_row_get(row, "windowStart"),
            windowEnd=_row_get(row, "windowEnd"),
            priority=_row_get(row, 'priority') or 'normal',
            requiredSkill=_row_get(row, "requiredSkill"),
            requiredTransport=_transport(required_transport) if required_transport else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Некорректная строка заявки (id={_row_get(row, 'id') or '?'}): {exc}",
        ) from exc


def _to_beeline_request(row: dict[str, str], *, use_network: bool = False) -> ServiceRequest | None:
    request_id = str(row.get("Заявка") or "").strip()
    if not request_id:
        return None
    work_type = row.get("Тип заявки HD") or row.get("Тип заявки BK") or ""
    norm = norm_for_work_type(work_type)
    address = (row.get("Адрес") or "").strip()
    district = (row.get("Район") or "").strip()
    lat_raw = row.get("lat") or row.get("Широта")
    lng_raw = row.get("lng") or row.get("Долгота")
    if _finite(lat_raw) and _finite(lng_raw):
        lat, lng = float(lat_raw), float(lng_raw)
    elif address or district:
        lat, lng = resolve_point(address, district, use_network=use_network)
    else:
        return None
    window_start = _time_from(row.get("Начало") or "")
    window_end = _time_from(row.get("Окончание") or "")
    if not window_start or not window_end or window_start > window_end:
        return None
    return ServiceRequest(
        id=request_id,
        location=RequestLocation(lat=lat, lng=lng, address=address or district or f"{lat:.4f}, {lng:.4f}",estimated=not (_finite(lat_raw) and _finite(lng_raw))),
        durationMinutes=norm["technicalMinutes"]+norm["documentsMinutes"],
        windowStart=window_start,
        windowEnd=window_end,
        priority="normal",
        requiredSkill=norm["skill"],
    )


def _brigade_name(raw: str) -> str:
    value = re.sub(r"^бригада\s+", "", (raw or "").strip(), flags=re.I).strip()
    return value


def _engineers_from_beeline(rows: list[dict[str, str]], requests: list[ServiceRequest]) -> list[Engineer]:
    skills = sorted({r.requiredSkill for r in requests if r.requiredSkill}) or [
        "Подключение",
        "Локальные работы",
        "Аварийные работы",
    ]
    brigades: list[str] = []
    seen: set[str] = set()
    for row in rows:
        name = _brigade_name(row.get("Бригада") or "")
        if name and name.lower() not in seen:
            seen.add(name.lower())
            brigades.append(name)

    anchors = [r.location for r in requests[: max(1, len(brigades) or 5)]]
    if not anchors:
        anchors = [RequestLocation(lat=55.7512, lng=37.6184, address="Москва")]

    engineers: list[Engineer] = []
    names = brigades or [f"Инженер {index + 1}" for index in range(max(4, min(8, max(1, len(requests) // 10))))]
    transports: list[Transport] = ["car", "car", "bike", "transit", "car", "walk", "car", "bike"]
    for index, name in enumerate(names):
        anchor = anchors[index % len(anchors)]
        engineers.append(
            Engineer(
                id=f"eng-{index + 1}",
                name=name,
                startLocation=Point(lat=anchor.lat + (index % 3) * 0.004, lng=anchor.lng + (index % 2) * 0.004),
                shiftStart="08:00",
                shiftEnd="22:00",
                skills=skills,
                transport=transports[index % len(transports)],
                available=True,
            )
        )
    return engineers


def _load_beeline_rows(rows: list[dict[str, str]]) -> Dataset:
    use_network = False
    requests = [item for item in (_to_beeline_request(row, use_network=use_network) for row in rows) if item]
    if not requests:
        raise HTTPException(
            status_code=400,
            detail=(
                "В CSV Билайн не найдено заявок с адресом/районом и временем. "
                "Нужны колонки «Заявка», «Адрес» (или «Район»), «Начало», «Окончание»."
            ),
        )
    engineers = _engineers_from_beeline(rows, requests)
    skipped=len(rows)-len(requests)
    warnings=[f'Импорт Билайн: принято {len(requests)} из {len(rows)} строк, пропущено {skipped} (нет ID, адреса или корректного окна).',
              'Параметры инженеров сгенерированы: стартовые точки, транспорт, все навыки набора и смена 08:00–22:00. Проверьте перед использованием.']
    if skipped:
        valid={r.id for r in requests}
        warnings.append('Пропущены строки: '+', '.join(str(i+2) for i,r in enumerate(rows) if str(r.get('Заявка') or '').strip() not in valid))
    return Dataset(engineers=engineers, requests=requests,importWarnings=warnings)


async def read_dataset(files: list[UploadFile]) -> Dataset:
    engineers: list[Engineer] | None = None
    requests: list[ServiceRequest] | None = None
    warnings=[]

    for upload in files:
        name = (upload.filename or "").lower()
        raw = await upload.read(10_000_001)
        if len(raw)>10_000_000:
            raise HTTPException(413,'Файл превышает 10 МБ.')
        try:
            body = _decode_bytes(raw).lstrip("\ufeff")
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Не удалось прочитать файл «{upload.filename}»: {exc}",
            ) from exc

        try:
            if name.endswith(".json"):
                payload: Any = json.loads(body)
                if isinstance(payload.get("engineers"), list):
                    engineers = [Engineer.model_validate(item) for item in payload["engineers"]]
                if isinstance(payload.get("requests"), list):
                    requests = [ServiceRequest.model_validate(item) for item in payload["requests"]]
            elif name.endswith(".csv"):
                rows = _parse_csv(body)
                if not rows:
                    continue
                tagged = [r for r in rows if _row_get(r, "entity").lower() in {"engineer", "request"}]
                if tagged:
                    es = [_to_engineer(r) for r in tagged if _row_get(r, "entity").lower() == "engineer"]
                    rs = [_to_request(r) for r in tagged if _row_get(r, "entity").lower() == "request"]
                    if es:
                        engineers = [*(engineers or []), *es]
                    if rs:
                        requests = [*(requests or []), *rs]
                elif rows[0].get("Заявка") and (rows[0].get("Тип заявки HD") or rows[0].get("Тип заявки BK")):
                    loaded = _load_beeline_rows(rows)
                    warnings.extend(loaded.importWarnings)
                    engineers = [*(engineers or []), *loaded.engineers]
                    requests = [*(requests or []), *loaded.requests]
                else:
                    if re.search(r"engineer|инженер", name, re.I):
                        engineers = [*(engineers or []), *[_to_engineer(r) for r in rows]]
                    elif re.search(r"request|заявк", name, re.I):
                        requests = [*(requests or []), *[_to_request(r) for r in rows]]
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "Для CSV укажите столбец entity (engineer/request) "
                                "или тип в имени файла (engineer/request)."
                            ),
                        )
            else:
                raise HTTPException(status_code=400, detail="Поддерживаются только JSON и CSV.")
        except HTTPException:
            raise
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Некорректный JSON в «{upload.filename}»: {exc}") from exc
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Ошибка разбора «{upload.filename}»: {exc}",
            ) from exc

    estimated=sum(r.location.estimated for r in requests or [])
    if estimated:
        warnings.append(f'Приблизительные координаты: {estimated} заявок. Оценка по району/адресу, не точное геокодирование; пробег и время ориентировочные.')
    try:
        return validate_dataset(Dataset(engineers=engineers or [], requests=requests or [],importWarnings=warnings))
    except ValidationError as exc:
        raise HTTPException(422,str(exc)) from exc


def _finite(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)
