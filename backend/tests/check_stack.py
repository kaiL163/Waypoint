"""Read-only integration smoke check against live OSRM and PostgreSQL."""
import os
import sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from sqlalchemy import text
from app import database
from app.demo import get_demo
from app.solver import make_plan
from app.routing import matrix

assert os.getenv('ROUTING_MODE')!='estimate', 'This check requires real OSRM.'
data=get_demo('large')
points=[data.engineers[0].startLocation,data.requests[2].location]
for mode in ['car','walk','bike']:
    result=matrix(points,mode)
    print(mode,result.minutes[0][1],result.meters[0][1],flush=True)
plans={}
for strategy in ['baseline','optimized']:
    plan=make_plan(data,strategy)
    plans[strategy]=plan
    assert plan.metrics.assignedRequests+plan.metrics.unassignedRequests==72
    assigned=[]
    for route in plan.routes:
        e=next(e for e in data.engineers if e.id==route.engineerId)
        previous=e.shiftStart
        if e.transport!='transit':
            assert route.geometry and len(route.geometry)>2
        for stop in route.stops:
            r=next(r for r in data.requests if r.id==stop.requestId)
            assert previous<=stop.plannedArrival<=stop.plannedStart
            assert r.windowStart<=stop.plannedStart<=r.windowEnd
            assert stop.plannedEnd<=e.shiftEnd
            assert r.requiredSkill in e.skills
            assert not r.requiredTransport or e.transport==r.requiredTransport
            assert stop.explanation
            previous=stop.plannedEnd
            assigned.append(r.id)
    assert len(assigned)==len(set(assigned))
    print(strategy,plan.metrics.model_dump(),flush=True)
def quality(plan):
    urgent=sum(next(r for r in data.requests if r.id==u.requestId).priority=='urgent' for u in plan.unassigned)
    return urgent,plan.metrics.unassignedRequests,plan.metrics.usedEngineers,plan.metrics.totalDistanceKm
assert quality(plans['optimized'])<=quality(plans['baseline'])
with database.engine.connect() as c:
    print('PostGIS',c.execute(text('SELECT PostGIS_Version()')).scalar())
    print('History snapshots',c.execute(text('SELECT count(*) FROM waypoint_history_v2')).scalar())
    print('Spatial points',c.execute(text('SELECT count(*) FROM waypoint_locations_v2 WHERE ST_SRID(point)=4326')).scalar())
print('Live stack OK; no dataset was modified.')
