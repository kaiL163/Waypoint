"""Transport-specific OSRM graphs. Estimates are explicit, never a silent failover."""
import math
import os
from dataclasses import dataclass
from functools import lru_cache

import httpx

from .models import Point

URLS = {mode: os.getenv(key, default).rstrip('/') for mode, key, default in [
    ('car', 'OSRM_URL', 'http://localhost:5000'),
    ('walk', 'OSRM_WALK_URL', 'http://localhost:5001'),
    ('bike', 'OSRM_BIKE_URL', 'http://localhost:5002'),
]}
UNREACHABLE = 1_000_000


class RoutingUnavailable(Exception):
    pass


@dataclass
class Matrix:
    minutes: list[list[int]]
    meters: list[list[int]]


def distance(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    value = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(math.radians(b.lng-a.lng)/2)**2
    return 6371 * 2 * math.asin(min(1, math.sqrt(value))) * 1.3


def estimate(points: list[Point], mode: str) -> Matrix:
    speed = {'car': 28, 'walk': 4, 'bike': 12, 'transit': 18}[mode]
    meters = [[round(distance(a, b)*1000) for b in points] for a in points]
    return Matrix([[math.ceil(d/1000/speed*60) for d in row] for row in meters], meters)


def matrix(points: list[Point], mode: str) -> Matrix:
    if mode == 'transit' or os.getenv('ROUTING_MODE') == 'estimate':
        return estimate(points, mode)
    return _matrix(tuple((p.lat, p.lng) for p in points), mode)


@lru_cache(maxsize=8)
def _matrix(points: tuple, mode: str) -> Matrix:
    n = len(points)
    times, distances = [[0]*n for _ in points], [[0]*n for _ in points]
    try:
        with httpx.Client(timeout=30) as client:
            for a in range(0, n, 40):
                sources = list(range(a, min(a+40, n)))
                for b in range(0, n, 40):
                    targets = list(range(b, min(b+40, n)))
                    indices = list(dict.fromkeys(sources+targets))
                    local = {node: i for i, node in enumerate(indices)}
                    coordinates = ';'.join(f'{points[i][1]},{points[i][0]}' for i in indices)
                    response = client.get(f'{URLS[mode]}/table/v1/driving/{coordinates}', params={
                        'sources': ';'.join(str(local[i]) for i in sources),
                        'destinations': ';'.join(str(local[i]) for i in targets),
                        'annotations': 'duration,distance',
                        'radiuses': ';'.join(['1500']*len(indices)),
                    })
                    response.raise_for_status()
                    body = response.json()
                    if body.get('code') != 'Ok':
                        raise RoutingUnavailable(f'OSRM ({mode}): {body.get("message", body.get("code"))}')
                    for i, source in enumerate(sources):
                        for j, target in enumerate(targets):
                            duration, length = body['durations'][i][j], body['distances'][i][j]
                            times[source][target] = math.ceil(duration/60) if duration is not None else UNREACHABLE
                            distances[source][target] = round(length) if length is not None else UNREACHABLE
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise RoutingUnavailable(f'Не удалось получить маршруты OSRM ({mode}). Проверьте сервис и попадание координат в дорожный граф Москвы.') from exc
    return Matrix(times, distances)


def geometry(points: list[Point], mode: str) -> list[Point] | None:
    if len(points)<2 or mode=='transit' or os.getenv('ROUTING_MODE')=='estimate':
        return None
    try:
        coords = ';'.join(f'{p.lng},{p.lat}' for p in points)
        response = httpx.get(f'{URLS[mode]}/route/v1/driving/{coords}', params={'overview': 'full', 'geometries': 'geojson','continue_straight':'false','radiuses':';'.join(['1500']*len(points))}, timeout=30)
        response.raise_for_status()
        return [Point(lat=lat,lng=lng) for lng,lat in response.json()['routes'][0]['geometry']['coordinates']]
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return None
