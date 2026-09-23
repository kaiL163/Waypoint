from __future__ import annotations

import os
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .routing import Matrix, matrix, route_geometry
from .schemas import Dataset, EngineerRoute, Metrics, Plan, RouteStop, Unassigned, clock, minutes

MAX_SOLVE_SECONDS = int(os.getenv('MAX_SOLVE_SECONDS', '15'))


def reason_for(request, engineers) -> str:
    available = [engineer for engineer in engineers if engineer.available]
    if not available:
        return 'Нет доступных инженеров.'
    skilled = [engineer for engineer in available if request.required_skill in engineer.skills]
    if not skilled:
        return 'Нет доступного инженера с нужным навыком.'
    suitable = [engineer for engineer in skilled if request.required_transport is None or engineer.transport == request.required_transport]
    if not suitable:
        return 'Нет инженера с требуемым транспортом.'
    return 'Не помещается во временное окно или смену при текущих маршрутах.'


def empty_plan(data: Dataset) -> Plan:
    unassigned = [Unassigned(request_id=req.id, reason=reason_for(req, data.engineers)) for req in data.requests if req.status != 'cancelled']
    return Plan(routes=[EngineerRoute(engineer_id=e.id, stops=[], distance_km=0) for e in data.engineers], unassigned=unassigned, metrics=Metrics(used_engineers=0, total_distance_km=0, assigned_requests=0, unassigned_requests=len(unassigned)))


def plan_dataset(data: Dataset, baseline: bool = False) -> Plan:
    requests = [request for request in data.requests if request.status != 'cancelled']
    engineers = [engineer for engineer in data.engineers if engineer.available]
    if not requests or not engineers:
        return empty_plan(data)
    n, v = len(requests), len(engineers)
    # Node order: requests, engineer starts, engineer ends. Ends are zero-cost open-route sinks.
    points = [request.location for request in requests] + [engineer.start_location for engineer in engineers]
    matrices: dict[str, Matrix] = {mode: matrix(points, mode) for mode in set(engineer.transport for engineer in engineers)}
    starts = list(range(n, n + v))
    ends = list(range(n + v, n + 2 * v))
    manager = pywrapcp.RoutingIndexManager(n + 2 * v, v, starts, ends)
    routing = pywrapcp.RoutingModel(manager)
    time_callbacks = []

    for vehicle, engineer in enumerate(engineers):
        travel = matrices[engineer.transport]

        def time_cost(from_index, to_index, travel=travel):
            origin, destination = manager.IndexToNode(from_index), manager.IndexToNode(to_index)
            if destination >= n + v:
                return 0
            service = requests[origin].duration_minutes if origin < n else 0
            return service + travel.minutes[origin][destination]

        def distance_cost(from_index, to_index, travel=travel):
            origin, destination = manager.IndexToNode(from_index), manager.IndexToNode(to_index)
            return 0 if destination >= n + v else travel.meters[origin][destination]

        time_callbacks.append(routing.RegisterTransitCallback(time_cost))
        routing.SetArcCostEvaluatorOfVehicle(routing.RegisterTransitCallback(distance_cost), vehicle)
        routing.SetFixedCostOfVehicle(3000, vehicle)

    routing.AddDimensionWithVehicleTransits(time_callbacks, 1440, 1440, False, 'Time')
    time = routing.GetDimensionOrDie('Time')
    for vehicle, engineer in enumerate(engineers):
        shift_start, shift_end = minutes(engineer.shift_start), minutes(engineer.shift_end)
        time.CumulVar(routing.Start(vehicle)).SetRange(shift_start, shift_start)
        time.CumulVar(routing.End(vehicle)).SetRange(shift_start, shift_end)
        routing.AddVariableMinimizedByFinalizer(time.CumulVar(routing.End(vehicle)))

    for node, request in enumerate(requests):
        index = manager.NodeToIndex(node)
        earliest = max(minutes(request.window_start), minutes(request.event_time) if request.event_time else 0)
        latest = minutes(request.window_end) - request.duration_minutes
        if latest < earliest:
            # No vehicle can serve the request; optional node must still have a valid domain.
            time.CumulVar(index).SetRange(0, 1440)
            allowed = []
        else:
            time.CumulVar(index).SetRange(earliest, latest)
            allowed = [vehicle for vehicle, engineer in enumerate(engineers) if request.required_skill in engineer.skills and (request.required_transport is None or request.required_transport == engineer.transport)]
        for vehicle in range(v):
            if vehicle not in allowed:
                routing.VehicleVar(index).RemoveValue(vehicle)
        routing.AddDisjunction([index], 20_000_000 if request.priority == 'urgent' else 10_000_000)

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    if not baseline:
        search.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search.time_limit.seconds = 1 if baseline else min(MAX_SOLVE_SECONDS, max(1, n // 8))
    solution = routing.SolveWithParameters(search)
    if solution is None:
        return empty_plan(data)

    assigned = set()
    routes = []
    for vehicle, engineer in enumerate(engineers):
        index = routing.Start(vehicle)
        previous_node = manager.IndexToNode(index)
        previous_end = minutes(engineer.shift_start)
        stops = []
        distance = 0
        geometry_points = [engineer.start_location]
        travel = matrices[engineer.transport]
        while not routing.IsEnd(solution.Value(routing.NextVar(index))):
            index = solution.Value(routing.NextVar(index))
            node = manager.IndexToNode(index)
            request = requests[node]
            arrival = previous_end + travel.minutes[previous_node][node]
            start = solution.Value(time.CumulVar(index))
            end = start + request.duration_minutes
            stops.append(RouteStop(request_id=request.id, order=len(stops) + 1, planned_arrival=clock(arrival), planned_start=clock(start), planned_end=clock(end)))
            assigned.add(request.id)
            distance += travel.meters[previous_node][node]
            geometry_points.append(request.location)
            previous_node, previous_end = node, end
        routes.append(EngineerRoute(engineer_id=engineer.id, stops=stops, distance_km=round(distance / 1000, 2), geometry=route_geometry(geometry_points, engineer.transport) if engineer.transport != 'transit' and stops else None))

    for engineer in data.engineers:
        if not engineer.available:
            routes.append(EngineerRoute(engineer_id=engineer.id, stops=[], distance_km=0))
    unassigned = [Unassigned(request_id=request.id, reason=reason_for(request, data.engineers)) for request in requests if request.id not in assigned]
    return Plan(routes=routes, unassigned=unassigned, metrics=Metrics(used_engineers=sum(bool(route.stops) for route in routes), total_distance_km=round(sum(route.distance_km for route in routes), 2), assigned_requests=len(assigned), unassigned_requests=len(unassigned)))
