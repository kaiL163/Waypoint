from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from fastapi import HTTPException, UploadFile

from .models import Dataset, Engineer, RequestLocation, ServiceRequest, Transport
from .norms import norm_for_work_type

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TIME_FIND = re.compile(r"(?:^|\s)([01]\d|2[0-3]):[0-5]\d")


def _transport(value: str) -> Transport:
    return value if value in {"walk", "bike", "transit"} else "car"


def _valid_time(value: str) -> bool:
    return bool(TIME_RE.match(value))


def _time_from(value: str) -> str:
    match = TIME_FIND.search(value or "")
    return match.group(0).strip() if match else ""


def validate_dataset(data: Dataset) -> Dataset:
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
            or request.windowStart >= request.windowEnd
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
    return Dataset(engineers=engineers, requests=requests)


def _to_engineer(row: dict[str, str]) -> Engineer:
    return Engineer(
        id=row["id"],
        name=row["name"],
        startLocation={
            "lat": float(row.get("lat") or row.get("startLat") or 0),
            "lng": float(row.get("lng") or row.get("startLng") or 0),
        },
        shiftStart=row.get("shiftStart") or "09:00",
        shiftEnd=row.get("shiftEnd") or "18:00",
        skills=[s.strip() for s in re.split(r"[;|]", row.get("skills") or "") if s.strip()],
        transport=_transport(row.get("transport") or "car"),
        available=row.get("available") != "false",
    )


def _to_request(row: dict[str, str]) -> ServiceRequest:
    lat = float(row["lat"])
    lng = float(row["lng"])
    return ServiceRequest(
        id=row["id"],
        location=RequestLocation(
            lat=lat,
            lng=lng,
            address=row.get("address") or f"{lat}, {lng}",
        ),
        durationMinutes=float(row["durationMinutes"]),
        windowStart=row["windowStart"],
        windowEnd=row["windowEnd"],
        priority="urgent" if row.get("priority") == "urgent" else "normal",
        requiredSkill=row["requiredSkill"],
        requiredTransport=_transport(row["requiredTransport"]) if row.get("requiredTransport") else None,
    )


def _to_beeline_request(row: dict[str, str]) -> ServiceRequest:
    work_type = row.get("Тип заявки HD") or row.get("Тип заявки BK") or ""
    norm = norm_for_work_type(work_type)
    lat = float(row.get("lat") or row.get("Широта") or "nan")
    lng = float(row.get("lng") or row.get("Долгота") or "nan")
    return ServiceRequest(
        id=row["Заявка"],
        location=RequestLocation(lat=lat, lng=lng, address=row.get("Адрес") or ""),
        durationMinutes=norm["totalMinutes"],
        windowStart=_time_from(row.get("Начало") or ""),
        windowEnd=_time_from(row.get("Окончание") or ""),
        priority="normal",
        requiredSkill=norm["skill"],
    )


def _parse_csv(text: str) -> list[dict[str, str]]:
    sample = text.splitlines()[0] if text else ""
    delimiter = ";" if ";" in sample else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows: list[dict[str, str]] = []
    for row in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items()})
    return rows


def _decode_bytes(raw: bytes) -> str:
    text = raw.decode("utf-8")
    if "\ufffd" in text:
        return raw.decode("cp1251")
    return text


async def read_dataset(files: list[UploadFile]) -> Dataset:
    engineers: list[Engineer] | None = None
    requests: list[ServiceRequest] | None = None

    for upload in files:
        name = (upload.filename or "").lower()
        raw = await upload.read()
        body = _decode_bytes(raw).lstrip("\ufeff")

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
            tagged = [r for r in rows if r.get("entity") in {"engineer", "request"}]
            if tagged:
                es = [_to_engineer(r) for r in tagged if r.get("entity") == "engineer"]
                rs = [_to_request(r) for r in tagged if r.get("entity") == "request"]
                if es:
                    engineers = [*(engineers or []), *es]
                if rs:
                    requests = [*(requests or []), *rs]
            elif rows[0].get("Заявка") and rows[0].get("Тип заявки HD"):
                missing = any(
                    not _finite(r.get("lat") or r.get("Широта"))
                    or not _finite(r.get("lng") or r.get("Долгота"))
                    for r in rows
                )
                if missing:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "В CSV Билайн добавьте столбцы lat и lng "
                            "(или «Широта» и «Долгота»): адреса нужны для карты. "
                            "Норматив длительности и навык будут определены автоматически "
                            "по «Тип заявки HD»."
                        ),
                    )
                requests = [*(requests or []), *[_to_beeline_request(r) for r in rows]]
            else:
                if re.search(r"engineer|инженер", name, re.I):
                    engineers = [*(engineers or []), *[_to_engineer(r) for r in rows]]
                elif re.search(r"request|заявк", name, re.I):
                    requests = [*(requests or []), *[_to_request(r) for r in rows]]
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="Для CSV укажите столбец entity (engineer/request) или тип в имени файла.",
                    )
        else:
            raise HTTPException(status_code=400, detail="Поддерживаются только JSON и CSV.")

    return validate_dataset(Dataset(engineers=engineers or [], requests=requests or []))


def _finite(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number
