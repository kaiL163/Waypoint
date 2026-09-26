"""VRPTW with open routes, an exact input-order baseline and frozen prefixes."""
import os

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .models import Dataset, EngineerRoute, Plan, PlanMetrics, RouteStop, UnassignedItem
from .routing import matrix, geometry, UNREACHABLE


def minutes(value: str) -> int:
    hour, minute = map(int, value.split(':'))
    return hour*60+minute


def clock(value: int) -> str:
    return f'{value//60:02d}:{value%60:02d}'


def frozen_prefix(data: Dataset, previous: Plan | None, at: str | None):
    result = {e.id: [] for e in data.engineers}
    if not previous or not at:
        return result
    cutoff = minutes(at)
    for engineer in data.engineers:
        route = next((r for r in previous.routes if r.engineerId == engineer.id), None)
        departure = minutes(engineer.shiftStart)
        for stop in route.stops if route else []:
            if not stop.frozen and previous.replannedAt:
                departure=max(departure,minutes(previous.replannedAt))
            # Departure is immediately after prior work; travel/waiting already begun is committed.
            if not stop.frozen and departure >= cutoff:
                break
            result[engineer.id].append(stop.model_copy(update={'frozen': True}, deep=True))
            departure = minutes(stop.plannedEnd)
    return result


def make_plan(data: Dataset, strategy='optimized', previous: Plan | None=None, at: str | None=None) -> Plan:
    prefix = frozen_prefix(data, previous, at)
    jobs = {r.id:r for r in data.requests}
    frozen = {s.requestId for stops in prefix.values() for s in stops}
    remaining = [r for r in data.requests if r.status!='cancelled' and r.id not in frozen]
    anchors, ready = {}, {}
    for e in data.engineers:
        last = prefix[e.id][-1] if prefix[e.id] else None
        anchors[e.id] = jobs[last.requestId].location if last else e.startLocation
        ready[e.id] = max(minutes(e.shiftStart), minutes(at) if at else 0, minutes(last.plannedEnd) if last else 0)
    engineers = [e for e in data.engineers if e.available and ready[e.id] < minutes(e.shiftEnd)]
    n, v = len(remaining), len(engineers)
    points = [r.location for r in remaining]+[anchors[e.id] for e in engineers]
    matrices = {mode:matrix(points, mode) for mode in sorted({e.transport for e in engineers})} if n and v else {}

    def compatible(req, e):
        return req.requiredSkill in e.skills and (not req.requiredTransport or req.requiredTransport==e.transport)

    def baseline_sequences():
        sequences = [[] for _ in engineers]
        positions = [n+i for i in range(v)]
        times = [ready[e.id] for e in engineers]
        for node, req in enumerate(remaining):  # deliberately NOT sorted
            for vehicle, e in enumerate(engineers):
                if not compatible(req,e):
                    continue
                travel = matrices[e.transport].minutes[positions[vehicle]][node]
                start = max(times[vehicle]+travel, minutes(req.windowStart), minutes(req.eventTime) if req.eventTime else 0)
                if start <= minutes(req.windowEnd) and start+req.durationMinutes <= minutes(e.shiftEnd):
                    sequences[vehicle].append(node)
                    times[vehicle], positions[vehicle] = start+req.durationMinutes, node
                    break
        return sequences

    base = baseline_sequences() if n and v else [[] for _ in engineers]
    sequences = base
    if strategy=='optimized' and n and v:
        manager = pywrapcp.RoutingIndexManager(n+2*v, v, list(range(n,n+v)), list(range(n+v,n+2*v)))
        routing = pywrapcp.RoutingModel(manager)
        max_edge = max((d for m in matrices.values() for row in m.meters for d in row if d<UNREACHABLE), default=0)
        distance_bound = (n+v)*max_edge+1
        vehicle_cost = distance_bound+1
        normal_penalty = (v+1)*vehicle_cost+distance_bound+1
        urgent_penalty = (n+1)*normal_penalty
        callbacks = []
        for vehicle,e in enumerate(engineers):
            travel = matrices[e.transport]
            def duration(a,b,travel=travel):
                origin,target=manager.IndexToNode(a),manager.IndexToNode(b)
                service=remaining[origin].durationMinutes if origin<n else 0
                return service+(0 if origin>=n+v or target>=n+v else travel.minutes[origin][target])
            def distance(a,b,travel=travel):
                origin,target=manager.IndexToNode(a),manager.IndexToNode(b)
                return 0 if origin>=n+v or target>=n+v else travel.meters[origin][target]
            callbacks.append(routing.RegisterTransitCallback(duration))
            routing.SetArcCostEvaluatorOfVehicle(routing.RegisterTransitCallback(distance),vehicle)
            routing.SetFixedCostOfVehicle(0 if prefix[e.id] else vehicle_cost,vehicle)
        routing.AddDimensionWithVehicleTransits(callbacks,1440,1440,False,'Time')
        time=routing.GetDimensionOrDie('Time')
        for vehicle,e in enumerate(engineers):
            time.CumulVar(routing.Start(vehicle)).SetValue(ready[e.id])
            time.CumulVar(routing.End(vehicle)).SetRange(ready[e.id],minutes(e.shiftEnd))
        for node,req in enumerate(remaining):
            index=manager.NodeToIndex(node)
            earliest=max(minutes(req.windowStart),minutes(req.eventTime) if req.eventTime else 0)
            latest=minutes(req.windowEnd)
            if earliest<=latest:
                time.CumulVar(index).SetRange(earliest,latest)
            for vehicle,e in enumerate(engineers):
                if earliest>latest or not compatible(req,e):
                    routing.VehicleVar(index).RemoveValue(vehicle)
            routing.AddDisjunction([index],urgent_penalty if req.priority=='urgent' else normal_penalty)
        search=pywrapcp.DefaultRoutingSearchParameters()
        search.first_solution_strategy=routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
        search.local_search_metaheuristic=routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        search.time_limit.seconds=max(1,min(int(os.getenv('MAX_SOLVE_SECONDS','10')),max(2,n//8)))
        solution=routing.SolveWithParameters(search)
        if solution:
            sequences=[]
            for vehicle in range(v):
                index=routing.Start(vehicle)
                nodes=[]
                while not routing.IsEnd(solution.Value(routing.NextVar(index))):
                    index=solution.Value(routing.NextVar(index))
                    nodes.append(manager.IndexToNode(index))
                sequences.append(nodes)

        def quality(routes):
            assigned={node for route in routes for node in route}
            urgent=sum(r.priority=='urgent' and i not in assigned for i,r in enumerate(remaining))
            used=len({e.id for e in data.engineers if prefix[e.id]} | {e.id for i,e in enumerate(engineers) if routes[i]})
            distance=0
            for vehicle,e in enumerate(engineers):
                pos=n+vehicle
                for node in routes[vehicle]:
                    distance+=matrices[e.transport].meters[pos][node]
                    pos=node
            return urgent,n-len(assigned),used,distance
        if quality(base)<quality(sequences):
            sequences=base

    route_stops={e.id:list(prefix[e.id]) for e in data.engineers}
    assigned=set(frozen)
    for vehicle,e in enumerate(engineers):
        pos,t=n+vehicle,ready[e.id]
        travel=matrices.get(e.transport)
        for node in sequences[vehicle]:
            req=remaining[node]
            arrival=t+travel.minutes[pos][node]
            start=max(arrival,minutes(req.windowStart),minutes(req.eventTime) if req.eventTime else 0)
            end=start+req.durationMinutes
            if start>minutes(req.windowEnd) or end>minutes(e.shiftEnd) or not compatible(req,e):
                raise RuntimeError('Планировщик вернул недопустимый маршрут; результат не сохранён.')
            km=round(travel.meters[pos][node]/1000,2)
            why=(f'Навык «{req.requiredSkill}» и транспорт подходят. Переезд от предыдущей точки: '
                 f'{travel.minutes[pos][node]} мин, {km:.2f} км. Начало {clock(start)} в окне '
                 f'{req.windowStart}–{req.windowEnd}; завершение {clock(end)} до конца смены {e.shiftEnd}. ')
            why += ('Первый допустимый инженер во входном порядке, заявки обрабатываются по поступлению.' if strategy=='baseline' else
                    'Назначение выбрано при совместном поиске: приоритет срочных, затем число выполненных заявок, число инженеров и пробег. Математический оптимум не гарантируется.')
            route_stops[e.id].append(RouteStop(requestId=req.id,order=len(route_stops[e.id])+1,plannedArrival=clock(arrival),plannedStart=clock(start),plannedEnd=clock(end),travelMinutes=travel.minutes[pos][node],distanceKm=km,explanation=why))
            assigned.add(req.id)
            pos,t=node,end

    unassigned=[]
    for node,req in enumerate(remaining):
        if req.id in assigned:
            continue
        skilled=[e for e in engineers if req.requiredSkill in e.skills]
        capable=[e for e in skilled if compatible(req,e)]
        if not skilled:
            reason=f'Нет доступного инженера с навыком «{req.requiredSkill}» и оставшимся временем смены.'
        elif not capable:
            reason='Нет доступного инженера с нужным навыком и требуемым транспортом.'
        else:
            reachable=[e for e in capable if matrices[e.transport].minutes[n+engineers.index(e)][node]<UNREACHABLE]
            starts=[max(ready[e.id]+matrices[e.transport].minutes[n+engineers.index(e)][node],minutes(req.windowStart),minutes(req.eventTime) if req.eventTime else 0) for e in reachable]
            if not reachable:
                reason='Между точкой инженера и заявкой нет доступного пути в дорожном графе.'
            elif all(start>minutes(req.windowEnd) for start in starts):
                reason=f'Даже напрямую самое раннее начало {clock(min(starts))}, позже конца окна {req.windowEnd}.'
            elif all(start+req.durationMinutes>minutes(e.shiftEnd) for start,e in zip(starts,reachable)):
                reason='Работа с учётом дороги и длительности не помещается в оставшуюся смену.'
            else:
                reason='Не включена в найденный план: конфликт с другими назначениями и их приоритетом. Это не доказательство отсутствия любого допустимого плана.'
        unassigned.append(UnassignedItem(requestId=req.id,reason=reason))

    routes=[]
    warnings=list(data.importWarnings)
    estimated=sum(r.location.estimated for r in data.requests)
    if estimated:
        warnings.append(f'{estimated} заявок имеют приблизительные координаты. Уточните lat/lng до практического использования плана.')
    if any(e.transport=='transit' for e in data.engineers):
        warnings.append('Общественный транспорт: оценка времени и расстояния, без расписаний и пересадок.')
    if os.getenv('ROUTING_MODE')=='estimate':
        warnings.append('Включён режим приближённых расстояний для всех видов транспорта; OSRM не используется.')
    for e in data.engineers:
        stops=route_stops[e.id]
        if not stops:
            continue
        coords=geometry([e.startLocation]+[jobs[s.requestId].location for s in stops],e.transport)
        if coords is None and e.transport!='transit' and os.getenv('ROUTING_MODE')!='estimate':
            warnings.append(f'{e.name}: дорожная геометрия недоступна; на карте показан порядок остановок.')
        routes.append(EngineerRoute(engineerId=e.id,stops=stops,distanceKm=round(sum(s.distanceKm for s in stops),2),geometry=coords,
            explanation=f'Остановок: {len(stops)}. Порядок учитывает время начала работ, переезды и конец смены. Возврат на старт не требуется.' + (' Зафиксированы уже начатые поездки/работы; пересчитан только остаток дня.' if prefix[e.id] else '')))
    return Plan(routes=routes,unassigned=unassigned,metrics=PlanMetrics(usedEngineers=len(routes),totalDistanceKm=round(sum(r.distanceKm for r in routes),2),assignedRequests=sum(len(r.stops) for r in routes),unassignedRequests=len(unassigned)),warnings=list(dict.fromkeys(warnings)),replannedAt=at)
