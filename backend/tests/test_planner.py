import unittest
from unittest.mock import patch

from app.planner import plan_dataset
from app.routing import Matrix
from app.schemas import Dataset


def dataset() -> Dataset:
    return Dataset.model_validate({
        'engineers': [{'id': 'e1', 'name': 'Иван', 'startLocation': {'lat': 55.75, 'lng': 37.60}, 'shiftStart': '09:00', 'shiftEnd': '18:00', 'skills': ['repair'], 'transport': 'car', 'available': True}],
        'requests': [{'id': 'r1', 'location': {'lat': 55.76, 'lng': 37.61, 'address': 'Москва'}, 'durationMinutes': 30, 'windowStart': '10:00', 'windowEnd': '11:00', 'priority': 'normal', 'requiredSkill': 'repair'}],
    })


def test_assigns_within_window():
    travel = Matrix([[0, 15], [15, 0]], [[0, 5000], [5000, 0]])
    with patch('app.planner.matrix', return_value=travel), patch('app.planner.route_geometry', return_value=None):
        plan = plan_dataset(dataset())
    assert plan.metrics.assigned_requests == 1
    stop = plan.routes[0].stops[0]
    assert stop.planned_start == '10:00'
    assert stop.planned_end == '10:30'
    assert plan.routes[0].distance_km == 5


def test_rejects_wrong_skill():
    data = dataset()
    data.requests[0].required_skill = 'installation'
    travel = Matrix([[0, 15], [15, 0]], [[0, 5000], [5000, 0]])
    with patch('app.planner.matrix', return_value=travel):
        plan = plan_dataset(data)
    assert plan.metrics.assigned_requests == 0
    assert 'навыком' in plan.unassigned[0].reason


def test_rejects_impossible_window():
    data = dataset()
    data.requests[0].window_start = '09:00'
    data.requests[0].window_end = '09:20'
    travel = Matrix([[0, 15], [15, 0]], [[0, 5000], [5000, 0]])
    with patch('app.planner.matrix', return_value=travel):
        plan = plan_dataset(data)
    assert plan.metrics.unassigned_requests == 1


class PlannerTests(unittest.TestCase):
    def test_window(self):
        test_assigns_within_window()

    def test_skill(self):
        test_rejects_wrong_skill()

    def test_impossible_window(self):
        test_rejects_impossible_window()

    def test_large_dataset(self):
        data = dataset()
        data.engineers = [data.engineers[0].model_copy(deep=True) for _ in range(10)]
        for index, engineer in enumerate(data.engineers):
            engineer.id = f'e{index}'
            engineer.transport = 'transit'
        data.requests = [data.requests[0].model_copy(deep=True) for _ in range(55)]
        for index, request in enumerate(data.requests):
            request.id = f'r{index}'
            request.window_start = '09:00'
            request.window_end = '18:00'
            request.duration_minutes = 20
            request.location.lat += index * 0.0001
        with patch('app.planner.route_geometry', return_value=None):
            result = plan_dataset(data)
        self.assertEqual(result.metrics.assigned_requests, 55)
