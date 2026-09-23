import unittest
from unittest.mock import patch

from app.main import app, replan
from app.schemas import Dataset, ReplanInput


class ApiTests(unittest.TestCase):
    def test_openapi_has_planning_routes(self):
        paths = app.openapi()['paths']
        self.assertIn('/api/planning/optimize', paths)
        self.assertIn('/api/planning/replan', paths)
        self.assertIn('/api/data/upload', paths)

    def test_cancel_event_updates_dataset(self):
        data = Dataset.model_validate({
            'engineers': [],
            'requests': [{'id': 'r1', 'location': {'lat': 55.75, 'lng': 37.6, 'address': 'Москва'}, 'durationMinutes': 30, 'windowStart': '09:00', 'windowEnd': '12:00', 'requiredSkill': 'repair'}],
        })
        payload = ReplanInput.model_validate({'event': {'type': 'cancel_request', 'requestId': 'r1'}})
        with patch('app.main.database.get_dataset', return_value=data), patch('app.main.database.save_dataset') as save:
            result = replan(payload)
        self.assertEqual(result.metrics.assigned_requests, 0)
        self.assertEqual(data.requests[0].status, 'cancelled')
        save.assert_called_once()
