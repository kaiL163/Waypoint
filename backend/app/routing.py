from __future__ import annotations

import math
import os
from dataclasses import dataclass

import httpx

from .schemas import Point, Transport

OSRM_URLS = {
    'car': os.getenv('OSRM_URL', 'http://osrm:5000').rstrip('/'),
    'walk': os.getenv('OSRM_WALK_URL', 'http://osrm-walk:5000').rstrip('/'),
    'bike': os.getenv('OSRM_BIKE_URL', 'http://osrm-bike:5000').rstrip('/'),
}
TRANSIT_SPEED_KMH = 22.0


class RoutingUnavailable(RuntimeError):
    pass


@dataclass
class Matrix:
    minutes: list[list[int]]
    meters: list[list[int]]


def haversine(a: Point, b: Point) -> float:
    radius = 6371000
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat, dlng = lat2 - lat1, math.radians(b.lng - a.lng)
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(min(1, math.sqrt(value)))


def matrix(points: list[Point], transport: Transport) -> Matrix:
    size = len(points)
    if transport == 'transit':
        distances = [[0 if i == j else round(haversine(a, b) * 1.3) for j, b in enumerate(points)] for i, a in enumerate(points)]
        minutes = [[0 if i == j else max(1, math.ceil(distance / 1000 / TRANSIT_SPEED_KMH * 60)) for j, distance in enumerate(row)] for i, row in enumerate(distances)]
        return Matrix(minutes, distances)

    durations = [[0] * size for _ in points]
    distances = [[0] * size for _ in points]
    # Keep each OSRM table request under 100 coordinates, including both axes.
    with httpx.Client(timeout=120) as client:
        for source_start in range(0, size, 40):
            sources = list(range(source_start, min(source_start + 40, size)))
            for dest_start in range(0, size, 40):
                destinations = list(range(dest_start, min(dest_start + 40, size)))
                indices = list(dict.fromkeys(sources + destinations))
                local = {global_id: index for index, global_id in enumerate(indices)}
                coordinates = ';'.join(f'{points[i].lng:.6f},{points[i].lat:.6f}' for i in indices)
                # OSRM's path says "driving" for every server; its preprocessed graph selects the mode.
                url = f'{OSRM_URLS[transport]}/table/v1/driving/{coordinates}'
                try:
                    response = client.get(url, params={'sources': ';'.join(str(local[i]) for i in sources), 'destinations': ';'.join(str(local[i]) for i in destinations), 'annotations': 'duration,distance'})
                    response.raise_for_status()
                    body = response.json()
                    if body.get('code') != 'Ok':
                        raise RoutingUnavailable(body.get('message', 'OSRM table error'))
                except (httpx.HTTPError, ValueError) as exc:
                    raise RoutingUnavailable(f'OSRM недоступен: {exc}') from exc
                for row, source in enumerate(sources):
                    for col, dest in enumerate(destinations):
                        duration = body['durations'][row][col]
                        distance = body['distances'][row][col]
                        # Disconnected locations are deliberately infeasible in the solver.
                        durations[source][dest] = 1_000_000 if duration is None else math.ceil(duration / 60)
                        distances[source][dest] = 1_000_000_000 if distance is None else round(distance)
    return Matrix(durations, distances)


def route_geometry(points: list[Point], transport: Transport = 'car') -> list[Point] | None:
    if len(points) < 2:
        return None
    coordinates = ';'.join(f'{point.lng:.6f},{point.lat:.6f}' for point in points)
    try:
        response = httpx.get(f'{OSRM_URLS[transport]}/route/v1/driving/{coordinates}', params={'overview': 'full', 'geometries': 'geojson', 'steps': 'false'}, timeout=45)
        response.raise_for_status()
        body = response.json()
        if body.get('code') != 'Ok':
            return None
        return [Point(lat=lat, lng=lng) for lng, lat in body['routes'][0]['geometry']['coordinates']]
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None
