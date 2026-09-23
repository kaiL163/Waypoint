from __future__ import annotations

import hashlib
import json
import math
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Approximate district centers (WGS84) for Moscow / near-Moscow areas in the dataset.
DISTRICT_COORDS: dict[str, tuple[float, float]] = {
    "академический": (55.6879, 37.5734),
    "басманный": (55.7675, 37.6685),
    "бирюлево восточное": (55.5870, 37.6610),
    "бирюлево западное": (55.5805, 37.6480),
    "братеево": (55.6345, 37.7605),
    "выхино": (55.7155, 37.8205),
    "гагаринский": (55.7075, 37.5685),
    "даниловский": (55.7105, 37.6305),
    "домодедово": (55.4415, 37.7530),
    "донской": (55.7055, 37.6105),
    "замоскворечье": (55.7365, 37.6285),
    "зюзино": (55.6555, 37.5855),
    "зябликово": (55.6205, 37.7455),
    "кашира": (54.8445, 38.1570),
    "котловка": (55.6685, 37.5985),
    "кузьминки": (55.7005, 37.7755),
    "лефортово": (55.7645, 37.7055),
    "москворечье - сабурово": (55.6425, 37.6625),
    "москворечье-сабурово": (55.6425, 37.6625),
    "нагатино - садовники": (55.6755, 37.6455),
    "нагатино-садовники": (55.6755, 37.6455),
    "нагатинский затон": (55.6855, 37.6755),
    "нагорный": (55.6655, 37.6155),
    "нижегородский": (55.7385, 37.7155),
    "орехово борисово северное": (55.6205, 37.7055),
    "орехово-борисово северное": (55.6205, 37.7055),
    "орехово борисово южное": (55.6055, 37.7255),
    "орехово-борисово южное": (55.6055, 37.7255),
    "рязанский": (55.7255, 37.7855),
    "ступино": (54.9005, 38.0805),
    "таганский": (55.7415, 37.6555),
    "текстильщики": (55.7085, 37.7355),
    "хамовники": (55.7285, 37.5755),
    "царицыно": (55.6255, 37.6555),
    "южнопортовый": (55.7055, 37.6855),
    "gpon даниловский": (55.7105, 37.6305),
}

MOSCOW_CENTER = (55.7512, 37.6184)
_CACHE_PATH = Path(__file__).resolve().parent.parent / ".geocode_cache.json"
_memory_cache: dict[str, tuple[float, float]] = {}
_last_nominatim_at = 0.0


def _load_disk_cache() -> None:
    global _memory_cache
    if _memory_cache or not _CACHE_PATH.exists():
        return
    try:
        payload = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        _memory_cache = {k: (float(v[0]), float(v[1])) for k, v in payload.items()}
    except Exception:
        _memory_cache = {}


def _save_disk_cache() -> None:
    try:
        _CACHE_PATH.write_text(
            json.dumps(_memory_cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def normalize_district(district: str) -> str:
    value = (district or "").strip().lower().replace("ё", "е")
    value = re.sub(r"^gpon\s+", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def clean_address(address: str) -> str:
    value = (address or "").strip()
    value = re.sub(r",?\s*кв\.?\s*\d+\s*$", "", value, flags=re.I)
    value = value.replace("пр-кт.", "проспект ")
    value = value.replace("проезд.", "проезд ")
    value = value.replace("пер.", "переулок ")
    value = value.replace("ул.", "улица ")
    value = value.replace("д.", "дом ")
    value = value.replace("к ", "корпус ")
    value = re.sub(r"\s+", " ", value).strip(" ,")
    if value and "москв" not in value.lower() and "домодедово" not in value.lower() and "кашир" not in value.lower() and "ступино" not in value.lower():
        value = f"Москва, {value}"
    return value


def _jitter(seed: str, radius_deg: float = 0.008) -> tuple[float, float]:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    angle = (int(digest[:8], 16) % 360) * math.pi / 180
    dist = (int(digest[8:16], 16) % 1000) / 1000 * radius_deg
    return dist * math.cos(angle), dist * math.sin(angle)


def coords_from_district(district: str, seed: str = "") -> tuple[float, float]:
    key = normalize_district(district)
    base = DISTRICT_COORDS.get(key, MOSCOW_CENTER)
    dx, dy = _jitter(seed or key)
    return base[0] + dx, base[1] + dy


def _nominatim(address: str) -> tuple[float, float] | None:
    global _last_nominatim_at
    query = clean_address(address)
    if not query:
        return None
    wait = 1.05 - (time.monotonic() - _last_nominatim_at)
    if wait > 0:
        time.sleep(wait)
    params = urlencode({"q": query, "format": "json", "limit": 1})
    request = Request(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": "WaypointPlanner/1.0 (hackathon; contact=local)"},
    )
    try:
        _last_nominatim_at = time.monotonic()
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload:
            return float(payload[0]["lat"]), float(payload[0]["lon"])
    except Exception:
        return None
    return None


def resolve_point(address: str, district: str = "", use_network: bool = True) -> tuple[float, float]:
    """Resolve WGS84 coordinates for an address. Prefer cache/network, else district estimate."""
    _load_disk_cache()
    key = clean_address(address).lower()
    if key in _memory_cache:
        return _memory_cache[key]

    point: tuple[float, float] | None = None
    if use_network and key:
        point = _nominatim(address)
        if point:
            _memory_cache[key] = point
            _save_disk_cache()
            return point

    point = coords_from_district(district, seed=key or address)
    if key:
        _memory_cache[key] = point
        _save_disk_cache()
    return point
