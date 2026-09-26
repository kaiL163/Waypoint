from __future__ import annotations

from .models import Dataset, Plan
from .solver import make_plan, minutes, clock
from .routing import distance


def changes_between(old_plan: Plan, new_plan: Plan, data: Dataset) -> list[str]:
    old_stops = {
        stop.requestId: (route.engineerId, stop.plannedStart, stop.order)
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
                old_name=engineers[old[0]].name if old[0] in engineers else old[0]
                messages.append(f"Заявка #{stop.requestId}: инженер {old_name} → {name}")
            if old and old[1] != stop.plannedStart:
                messages.append(f"Заявка #{stop.requestId}: начало {old[1]} → {stop.plannedStart}")
            if old and old[2] != stop.order:
                messages.append(f"Заявка #{stop.requestId}: позиция {old[2]} → {stop.order}")

    for request_id in old_stops:
        if request_id not in new_stop_ids:
            job = requests.get(request_id)
            if job and job.status == "cancelled":
                messages.append(f"Заявка #{request_id} отменена и снята с маршрута.")
            else:
                messages.append(f"Заявка #{request_id} снята с маршрута после перепланирования.")
    old_unassigned={item.requestId:item.reason for item in old_plan.unassigned}
    for item in new_plan.unassigned:
        if old_unassigned.get(item.requestId)!=item.reason:
            messages.append(f'Заявка #{item.requestId} не назначена: {item.reason}')
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
