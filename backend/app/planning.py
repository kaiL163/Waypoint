from __future__ import annotations

import math

from .models import Dataset, EngineerRoute, Plan, PlanMetrics, Point, RouteStop, Strategy, UnassignedItem

SPEED = {"car": 28, "walk": 4, "bike": 12, "transit": 18}


def minutes(time: str) -> int:
    hours, mins = map(int, time.split(":"))
    return hours * 60 + mins


def clock(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def distance(a: Point, b: Point) -> float:
    r = math.pi / 180
    x = (b.lng - a.lng) * r * math.cos((a.lat + b.lat) * r / 2)
    y = (b.lat - a.lat) * r
    return 6371 * math.sqrt(x * x + y * y) * 1.3


def make_plan(data: Dataset, strategy: Strategy = "optimized") -> Plan:
    states: dict[str, dict] = {}
    for engineer in data.engineers:
        if not engineer.available:
            continue
        states[engineer.id] = {
            "point": engineer.startLocation,
            "time": minutes(engineer.shiftStart),
            "route": EngineerRoute(engineerId=engineer.id, stops=[], distanceKm=0),
        }

    unassigned: list[UnassignedItem] = []
    requests = sorted(
        [r for r in data.requests if r.status != "cancelled"],
        key=lambda r: (minutes(r.windowStart), 0 if r.priority == "urgent" else 1),
    )

    for request in requests:
        skilled = [e for e in data.engineers if e.available and request.requiredSkill in e.skills]
        capable = [
            e
            for e in skilled
            if not request.requiredTransport or e.transport == request.requiredTransport
        ]
        choices = []
        for engineer in capable:
            state = states[engineer.id]
            km = distance(state["point"], request.location)
            arrival = state["time"] + math.ceil(km / SPEED[engineer.transport] * 60)
            start = max(
                arrival,
                minutes(request.windowStart),
                minutes(request.eventTime) if request.eventTime else 0,
            )
            end = start + int(request.durationMinutes)
            if (
                arrival <= minutes(request.windowEnd)
                and end <= minutes(request.windowEnd)
                and end <= minutes(engineer.shiftEnd)
            ):
                choices.append(
                    {
                        "engineer": engineer,
                        "state": state,
                        "km": km,
                        "arrival": arrival,
                        "start": start,
                        "end": end,
                    }
                )

        if strategy == "optimized":
            choices.sort(
                key=lambda c: (
                    0 if c["state"]["route"].stops else 1,
                    c["km"],
                    c["start"],
                )
            )
            choice = choices[0] if choices else None
        else:
            choice = choices[0] if choices else None

        if not choice:
            if not skilled:
                reason = f"Нет доступного инженера с навыком «{request.requiredSkill}»."
            elif not capable:
                reason = "Нет доступного инженера с требуемым типом транспорта."
            else:
                reason = (
                    "Подходящие инженеры не успевают выполнить работу "
                    "в заданное временное окно или до конца смены."
                )
            unassigned.append(UnassignedItem(requestId=request.id, reason=reason))
            continue

        state = choice["state"]
        km = choice["km"]
        state["route"].distanceKm += km
        state["route"].stops.append(
            RouteStop(
                requestId=request.id,
                order=len(state["route"].stops) + 1,
                plannedArrival=clock(choice["arrival"]),
                plannedStart=clock(choice["start"]),
                plannedEnd=clock(choice["end"]),
            )
        )
        state["point"] = request.location
        state["time"] = choice["end"]

    routes = [
        EngineerRoute(
            engineerId=s["route"].engineerId,
            stops=s["route"].stops,
            distanceKm=round(s["route"].distanceKm * 10) / 10,
        )
        for s in states.values()
        if s["route"].stops
    ]
    return Plan(
        routes=routes,
        unassigned=unassigned,
        metrics=PlanMetrics(
            usedEngineers=len(routes),
            totalDistanceKm=round(sum(r.distanceKm for r in routes) * 10) / 10,
            assignedRequests=sum(len(r.stops) for r in routes),
            unassignedRequests=len(unassigned),
        ),
    )


def changes_between(old_plan: Plan, new_plan: Plan, data: Dataset) -> list[str]:
    old_stops = {
        stop.requestId: (route.engineerId, stop.plannedStart)
        for route in old_plan.routes
        for stop in route.stops
    }
    new_stop_ids = {stop.requestId for route in new_plan.routes for stop in route.stops}
    messages: list[str] = []
    engineers = {e.id: e for e in data.engineers}
    requests = {r.id: r for r in data.requests}

    for route in new_plan.routes:
        for stop in route.stops:
            old = old_stops.get(stop.requestId)
            job = requests.get(stop.requestId)
            if not old:
                label = "Срочная заявка" if job and job.priority == "urgent" else "Заявка"
                name = engineers[route.engineerId].name if route.engineerId in engineers else route.engineerId
                messages.append(f"{label} #{stop.requestId} добавлена в маршрут {name}")
            elif old[0] != route.engineerId:
                name = engineers[route.engineerId].name if route.engineerId in engineers else route.engineerId
                messages.append(f"Заявка #{stop.requestId} передана {name}")
            elif old[1] != stop.plannedStart:
                messages.append(f"Заявка #{stop.requestId} перенесена на {stop.plannedStart}")

    for request_id in old_stops:
        if request_id not in new_stop_ids:
            job = requests.get(request_id)
            if job and job.status == "cancelled":
                messages.append(f"Заявка #{request_id} отменена и снята с маршрута.")
            else:
                messages.append(f"Заявка #{request_id} снята с маршрута после перепланирования.")
    return messages


def create_urgent(
    payload: dict,
    existing_ids: list[str],
) -> dict:
    numeric = [int(x) for x in existing_ids if str(x).isdigit()]
    next_id = str(max([240, *numeric]) + 1)
    return {
        "id": next_id,
        "location": {
            "address": payload["address"],
            "lat": payload["lat"],
            "lng": payload["lng"],
        },
        "durationMinutes": payload["durationMinutes"],
        "eventTime": payload["eventTime"],
        "windowStart": payload["windowStart"],
        "windowEnd": payload["windowEnd"],
        "priority": "urgent",
        "requiredSkill": payload["requiredSkill"],
        "requiredTransport": payload["requiredTransport"],
    }
