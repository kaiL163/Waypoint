import os
os.environ['ROUTING_MODE']='estimate'
os.environ['MAX_SOLVE_SECONDS']='1'
import unittest
from pydantic import ValidationError
from app.models import Dataset, Engineer, ServiceRequest, Point
from app.solver import make_plan, frozen_prefix
from app.io_data import _to_beeline_request
from app.demo import get_demo

LOCAL='Локальные работы'
EMERGENCY='Аварийные работы'
POINT={'lat':55.75,'lng':37.61}

def engineer(id='e', **extra):
    return Engineer.model_validate(dict(id=id,name=id,startLocation=POINT,shiftStart='09:00',shiftEnd='18:00',skills=[LOCAL],transport='walk',**extra))

def request(id='r', **extra):
    fields=dict(id=id,location={**POINT,'address':'Москва'},durationMinutes=30,windowStart='09:00',windowEnd='17:00',requiredSkill=LOCAL)
    fields.update(extra)
    return ServiceRequest.model_validate(fields)

def ids(plan):
    return [s.requestId for r in plan.routes for s in r.stops]

class PlanningTests(unittest.TestCase):
    def test_baseline_preserves_input_order(self):
        data=Dataset(engineers=[engineer()],requests=[request('later',windowStart='12:00'),request('earlier',windowEnd='10:00')])
        self.assertEqual(ids(make_plan(data,'baseline')),['later'])
        self.assertEqual(set(ids(make_plan(data))),{'later','earlier'})

    def test_window_limits_start_not_completion(self):
        data=Dataset(engineers=[engineer()],requests=[request(durationMinutes=60,windowEnd='09:30')])
        for strategy in ['baseline','optimized']:
            plan=make_plan(data,strategy)
            self.assertEqual(ids(plan),['r'])
            self.assertEqual(plan.routes[0].stops[0].plannedEnd,'10:00')

    def test_last_service_must_end_within_shift(self):
        data=Dataset(engineers=[engineer()],requests=[request(windowStart='17:50',windowEnd='18:00')])
        self.assertEqual(ids(make_plan(data)),[])

    def test_urgent_precedes_normal_when_capacity_conflicts(self):
        data=Dataset(engineers=[engineer()],requests=[request('normal',durationMinutes=60,windowEnd='09:00'),request('urgent',durationMinutes=60,windowEnd='09:00',priority='urgent')])
        self.assertEqual(ids(make_plan(data)),['urgent'])

    def test_skills_transport_and_cancelled(self):
        data=Dataset(engineers=[engineer()],requests=[request('skill',requiredSkill=EMERGENCY),request('transport',requiredTransport='car'),request('cancelled',status='cancelled')])
        plan=make_plan(data)
        self.assertEqual(ids(plan),[])
        self.assertEqual(plan.metrics.unassignedRequests,2)
        self.assertTrue(all(item.reason for item in plan.unassigned))

    def test_empty_data_and_no_engineers(self):
        self.assertEqual(make_plan(Dataset(engineers=[],requests=[])).metrics.usedEngineers,0)
        self.assertEqual(make_plan(Dataset(engineers=[],requests=[request()])).metrics.unassignedRequests,1)

    def test_frozen_work_and_event_time(self):
        data=Dataset(engineers=[engineer()],requests=[request('first',durationMinutes=60),request('second',durationMinutes=60)])
        previous=make_plan(data,'baseline')
        data.requests.append(request('new',priority='urgent',eventTime='09:30'))
        result=make_plan(data,previous=previous,at='09:30')
        first=result.routes[0].stops[0]
        self.assertEqual(first.requestId,'first')
        self.assertTrue(first.frozen)
        self.assertEqual(first.plannedStart,'09:00')
        self.assertTrue(all(s.plannedStart>='10:00' for s in result.routes[0].stops[1:]))

    def test_unavailable_keeps_committed_stop_only(self):
        data=Dataset(engineers=[engineer()],requests=[request('first',durationMinutes=60),request('second')])
        previous=make_plan(data,'baseline')
        data.engineers[0].available=False
        result=make_plan(data,previous=previous,at='09:30')
        self.assertEqual(ids(result),['first'])
        self.assertEqual(result.unassigned[0].requestId,'second')

    def test_no_frozen_stops_before_shift(self):
        data=Dataset(engineers=[engineer()],requests=[request()])
        self.assertEqual(frozen_prefix(data,make_plan(data,'baseline'),'08:00'),{'e':[]})

    def test_same_event_time_does_not_freeze_future_work(self):
        data=Dataset(engineers=[engineer()],requests=[request('first',durationMinutes=60),request('second')])
        previous=make_plan(data,'baseline')
        replanned=make_plan(data,previous=previous,at='09:30')
        prefix=frozen_prefix(data,replanned,'09:30')
        self.assertEqual([s.requestId for s in prefix['e']],['first'])

    def test_validation(self):
        with self.assertRaises(ValidationError):
            Dataset(engineers=[engineer()],requests=[request(),request()])
        for point in [{'lat':float('nan'),'lng':0},{'lat':91,'lng':0}]:
            with self.assertRaises(ValidationError):
                Point.model_validate(point)
        with self.assertRaises(ValidationError):
            request(requiredSkill='unknown')
        with self.assertRaises(ValidationError):
            request(durationMinutes=-1)

    def test_norm_excludes_travel(self):
        row={'Заявка':'1','Тип заявки HD':'Подключение','Адрес':'Москва','lat':'55.75','lng':'37.61','Начало':'09:00','Окончание':'12:00'}
        self.assertEqual(_to_beeline_request(row).durationMinutes,70)

    def test_large_demo_constraints(self):
        data=get_demo('large')
        self.assertEqual((len(data.engineers),len(data.requests)),(12,72))
        result=make_plan(data)
        self.assertEqual(result.metrics.assignedRequests+result.metrics.unassignedRequests,72)
        self.assertEqual(len(ids(result)),len(set(ids(result))))
        for route in result.routes:
            e=next(e for e in data.engineers if e.id==route.engineerId)
            previous=e.shiftStart
            for stop in route.stops:
                r=next(r for r in data.requests if r.id==stop.requestId)
                self.assertLessEqual(previous,stop.plannedArrival)
                self.assertLessEqual(r.windowStart,stop.plannedStart)
                self.assertLessEqual(stop.plannedStart,r.windowEnd)
                self.assertLessEqual(stop.plannedEnd,e.shiftEnd)
                self.assertIn(r.requiredSkill,e.skills)
                self.assertTrue(not r.requiredTransport or r.requiredTransport==e.transport)
                previous=stop.plannedEnd

if __name__=='__main__':
    unittest.main()
