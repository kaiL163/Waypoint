from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Transport = Literal["car", "walk", "bike", "transit"]
Priority = Literal["normal", "urgent"]
RequestStatus = Literal["unplanned", "planned", "unassigned", "cancelled"]
Strategy = Literal["optimized", "baseline"]


class Point(BaseModel):
    lat: float
    lng: float


class RequestLocation(Point):
    address: str = ""


class Engineer(BaseModel):
    id: str
    name: str
    startLocation: Point
    shiftStart: str
    shiftEnd: str
    skills: list[str]
    transport: Transport = "car"
    available: bool = True


class ServiceRequest(BaseModel):
    id: str
    location: RequestLocation
    durationMinutes: float
    windowStart: str
    windowEnd: str
    requiredSkill: str
    eventTime: str | None = None
    priority: Priority = "normal"
    requiredTransport: Transport | None = None
    status: RequestStatus | None = None


class Dataset(BaseModel):
    engineers: list[Engineer]
    requests: list[ServiceRequest]


class RouteStop(BaseModel):
    requestId: str
    order: int
    plannedArrival: str
    plannedStart: str
    plannedEnd: str


class EngineerRoute(BaseModel):
    engineerId: str
    stops: list[RouteStop]
    distanceKm: float


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


class UrgentInput(BaseModel):
    address: str
    lat: float
    lng: float
    eventTime: str
    windowStart: str
    windowEnd: str
    durationMinutes: float
    requiredSkill: str
    requiredTransport: Transport = "car"


class ReplanEvent(BaseModel):
    type: Literal["urgent_request", "cancel_request", "engineer_unavailable"]
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


class DemoScenarioInfo(BaseModel):
    id: str
    title: str
    description: str
