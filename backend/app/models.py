from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Time = Annotated[str, Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')]
SKILLS = {'Локальные работы', 'Работы на подключение и дозаказы', 'Аварийные работы'}


def normalize_skill(value: str) -> str:
    value = value.strip()
    if value == 'Подключение':
        value = 'Работы на подключение и дозаказы'
    if value not in SKILLS:
        raise ValueError(f'Неизвестный навык: {value}')
    return value

Transport = Literal["car", "walk", "bike", "transit"]
Priority = Literal["normal", "urgent"]
RequestStatus = Literal["unplanned", "planned", "unassigned", "cancelled"]
Strategy = Literal["optimized", "baseline"]


class Point(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class RequestLocation(Point):
    address: str = ""
    estimated: bool = False

    @model_validator(mode='before')
    @classmethod
    def address_without_coordinates(cls, value):
        if isinstance(value,dict) and ('lat' not in value or 'lng' not in value) and value.get('address'):
            from .geocode import resolve_point
            lat,lng=resolve_point(value['address'],use_network=False)
            return {**value,'lat':lat,'lng':lng,'estimated':True}
        return value


class Engineer(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1)
    startLocation: Point
    shiftStart: Time
    shiftEnd: Time
    skills: list[str] = Field(min_length=1, max_length=3)
    transport: Transport = "car"
    available: bool = True

    @field_validator('skills')
    @classmethod
    def valid_skills(cls, values):
        return list(dict.fromkeys(normalize_skill(value) for value in values))

    @model_validator(mode='after')
    def valid_shift(self):
        if self.shiftStart >= self.shiftEnd:
            raise ValueError('Конец смены должен быть позже начала в пределах одного дня.')
        return self


class ServiceRequest(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    location: RequestLocation
    durationMinutes: int = Field(gt=0, le=1440)
    windowStart: Time
    windowEnd: Time
    requiredSkill: str
    eventTime: Time | None = None
    priority: Priority = "normal"
    requiredTransport: Transport | None = None
    status: RequestStatus | None = None

    @field_validator('requiredSkill')
    @classmethod
    def valid_skill(cls, value):
        return normalize_skill(value)

    @model_validator(mode='after')
    def valid_window(self):
        if self.windowStart > self.windowEnd:
            raise ValueError('Конец окна начала работ должен быть не раньше начала.')
        return self


class Dataset(BaseModel):
    engineers: list[Engineer] = Field(max_length=30)
    requests: list[ServiceRequest] = Field(max_length=300)
    importWarnings: list[str] = Field(default_factory=list)
    revision: int | None = None

    @model_validator(mode='after')
    def unique_ids(self):
        for label, items in [('инженеров', self.engineers), ('заявок', self.requests)]:
            ids = [item.id for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f'Повторяющиеся ID в списке {label}.')
        return self


class RouteStop(BaseModel):
    requestId: str
    order: int
    plannedArrival: str
    plannedStart: str
    plannedEnd: str
    travelMinutes: int = 0
    distanceKm: float = 0
    explanation: str = ''
    frozen: bool = False


class EngineerRoute(BaseModel):
    engineerId: str
    stops: list[RouteStop]
    distanceKm: float
    geometry: list[Point] | None = None
    explanation: str = ''


class PlanMetrics(BaseModel):
    usedEngineers: int
    totalDistanceKm: float
    assignedRequests: int
    unassignedRequests: int


class UnassignedItem(BaseModel):
    requestId: str
    reason: str


class Plan(BaseModel):
    routes: list[EngineerRoute]
    unassigned: list[UnassignedItem]
    metrics: PlanMetrics
    warnings: list[str] = Field(default_factory=list)
    replannedAt: Time | None = None


class UrgentInput(Point):
    address: str
    eventTime: Time
    windowStart: Time
    windowEnd: Time
    durationMinutes: int = Field(gt=0, le=1440)
    requiredSkill: str
    requiredTransport: Transport | None = None

    @field_validator('requiredSkill')
    @classmethod
    def valid_skill(cls,value):
        return normalize_skill(value)

    @model_validator(mode='after')
    def valid_window(self):
        if self.windowStart>self.windowEnd:
            raise ValueError('Конец окна должен быть не раньше начала.')
        return self


class ReplanEvent(BaseModel):
    type: Literal["urgent_request", "cancel_request", "engineer_unavailable"]
    eventTime: Time
    request: ServiceRequest | None = None
    input: UrgentInput | None = None
    requestId: str | None = None
    engineerId: str | None = None


class ReplanBody(BaseModel):
    dataset: Dataset
    event: ReplanEvent
    previousPlan: Plan | None = None


class ReplanResponse(BaseModel):
    dataset: Dataset
    plan: Plan
    changes: list[str] = Field(default_factory=list)
    baseline: Plan


class DemoScenarioInfo(BaseModel):
    id: str
    title: str
    description: str
