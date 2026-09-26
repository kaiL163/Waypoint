import os
os.environ['ROUTING_MODE']='estimate'
os.environ['MAX_SOLVE_SECONDS']='1'
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.models import Dataset
from app.solver import make_plan
from test_planning import engineer, request

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.data=Dataset(engineers=[engineer()],requests=[request('a',durationMinutes=60),request('b')],revision=3)
        self.plan=make_plan(self.data,'baseline')
        self.client=TestClient(app)
        self.load=patch('app.main.database.load',return_value=(self.data,self.plan,self.plan,3)).start()
        self.save=patch('app.main.database.save',side_effect=lambda d,p,b,r:d.model_copy(update={'revision':r+1})).start()
        self.addCleanup(patch.stopall)

    def event(self,event):
        return self.client.post('/api/planning/replan',json={'dataset':self.data.model_dump(mode='json'),'event':event})

    def test_requires_event_time(self):
        self.assertEqual(self.event({'type':'cancel_request','requestId':'b'}).status_code,422)

    def test_rejects_unknown_id(self):
        self.assertEqual(self.event({'type':'cancel_request','requestId':'missing','eventTime':'08:00'}).status_code,404)

    def test_cannot_cancel_committed_work(self):
        self.assertEqual(self.event({'type':'cancel_request','requestId':'a','eventTime':'09:30'}).status_code,409)
        self.save.assert_not_called()

    def test_cancel_future_request(self):
        response=self.event({'type':'cancel_request','requestId':'b','eventTime':'09:30'})
        self.assertEqual(response.status_code,200,response.text)
        payload=response.json()
        self.assertEqual(payload['plan']['replannedAt'],'09:30')
        self.assertIn('baseline',payload)
        self.assertEqual(payload['dataset']['revision'],4)
        self.assertTrue(payload['plan']['routes'][0]['stops'][0]['frozen'])

    def test_stale_data_cannot_overwrite(self):
        self.data.revision=1
        self.assertEqual(self.client.post('/api/planning/compare',json=self.data.model_dump(mode='json')).status_code,409)
        self.save.assert_not_called()

    def test_urgent_validation_returns_422(self):
        response=self.event({'type':'urgent_request','eventTime':'09:30','input':{'address':'Москва','lat':100,'lng':37,'eventTime':'09:30','windowStart':'12:00','windowEnd':'11:00','durationMinutes':30,'requiredSkill':'unknown'}})
        self.assertEqual(response.status_code,422)

    def test_baseline_does_not_save_state(self):
        response=self.client.post('/api/planning/optimize?strategy=baseline',json=self.data.model_dump(mode='json'))
        self.assertEqual(response.status_code,200)
        self.save.assert_not_called()
