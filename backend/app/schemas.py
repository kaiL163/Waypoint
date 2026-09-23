from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def camel(name: str) -> str:
    first, *rest = name.split('_')
    return first + ''.join(part.title() for part in rest)


class WireModel(BaseModel):
    model_config = ConfigDict(alias_generator=camel, populate_by_name=True)


class Point(WireModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class Location(Point):
    address: str = Field(min_length=1)


Transport = Literal['car', 'walk', 'bike', 'transit']


class Engineer(WireModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    start_location: Point
    shift_start: str
    shift_end: str
    skills: list[str]
    transport: Transport = 'car'
    available: bool = True

    @model_validator(mode='after')
    def valid_shift(self):
        if minutes(self.shift_start) >= minutes(self.shift_end):
            raise ValueError('Shift end must be after start')
        return self


class ServiceRequest(WireModel):
    id: str = Field(min_length=1)
    location: Location
    duration_minutes: int = Field(gt=0, le=1440)
    event_time: str | None = None
    window_start: str
    window_end: str
    priority: Literal['normal', 'urgent'] = 'normal'
    required_skill: str = Field(min_length=1)
    required_transport: Transport | None = None
    status: Literal['unplanned', 'planned', 'unassigned', 'cancelled'] | None = None

    @model_validator(mode='after')
    def valid_window(self):
        if minutes(self.window_start) >= minutes(self.window_end):
            raise ValueError('Window end must be after start')
        if self.event_time is not None:
            minutes(self.event_time)
        return self


class Dataset(WireModel):
    engineers: list[Engineer]
    requests: list[ServiceRequest]

    @model_validator(mode='after')
    def unique_ids(self):
        for label, values in [('engineer', self.engineers), ('request', self.requests)]:
            ids = [value.id for value in values]
            if len(ids) != len(set(ids)):
                raise ValueError(f'Duplicate {label} ID')
        return self


class RouteStop(WireModel):
    request_id: str
    order: int
    planned_arrival: str
    planned_start: str
    planned_end: str


class EngineerRoute(WireModel):
    engineer_id: str
    stops: list[RouteStop]
    distance_km: float
    geometry: list[Point] | None = None


class Unassigned(WireModel):
    request_id: str
    reason: str


class Metrics(WireModel):
    used_engineers: int
    total_distance_km: float
    assigned_requests: int
    unassigned_requests: int


class Plan(WireModel):
    routes: list[EngineerRoute]
    unassigned: list[Unassigned]
    metrics: Metrics


class PlanningEvent(WireModel):
    type: Literal['urgent_request', 'cancel_request', 'engineer_unavailable']
    request: ServiceRequest | None = None
    request_id: str | None = None
    engineer_id: str | None = None


class ReplanInput(WireModel):
    event: PlanningEvent


def minutes(value: str) -> int:
    try:
        hour, minute = map(int, value.split(':'))
        if len(value) != 5 or not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError
    except ValueError as exc:
        raise ValueError(f'Invalid HH:MM time: {value}') from exc
    return hour * 60 + minute


def clock(value: int) -> str:
    return f'{value // 60:02d}:{value % 60:02d}'
