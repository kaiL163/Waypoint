from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text

from . import database
from .planner import plan_dataset
from .routing import RoutingUnavailable
from .schemas import Dataset, Plan, ReplanInput
from .uploads import parse_uploads


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.initialize()
    yield


app = FastAPI(title='Waypoint API', version='1.0.0', lifespan=lifespan)


@app.exception_handler(RoutingUnavailable)
async def routing_error(_, exc: RoutingUnavailable):
    return JSONResponse(status_code=503, content={'detail': str(exc)})


@app.get('/api/health')
def health():
    with database.engine.connect() as connection:
        connection.execute(text('SELECT 1'))
    return {'status': 'ok'}


@app.get('/api/engineers')
def engineers():
    return database.get_dataset().engineers


@app.get('/api/requests')
def requests():
    return database.get_dataset().requests


@app.put('/api/data/dataset', response_model=Dataset)
def replace_dataset(data: Dataset):
    database.save_dataset(data)
    return data


@app.post('/api/data/upload', response_model=Dataset)
async def upload(files: list[UploadFile]):
    try:
        data = await parse_uploads(files)
    except (ValueError, UnicodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    database.save_dataset(data)
    return data


@app.get('/api/planning/current', response_model=Plan)
def current():
    plan = database.get_current_plan()
    if plan is None:
        raise HTTPException(status_code=404, detail='План ещё не построен.')
    return plan


@app.post('/api/planning/baseline', response_model=Plan)
def baseline(data: Dataset):
    return plan_dataset(data, baseline=True)


@app.post('/api/planning/optimize', response_model=Plan)
def optimize(data: Dataset):
    plan = plan_dataset(data)
    database.save_dataset(data, plan)
    return plan


@app.post('/api/planning/replan', response_model=Plan)
def replan(payload: ReplanInput):
    data = database.get_dataset()
    event = payload.event
    if event.type == 'urgent_request':
        if event.request is None:
            raise HTTPException(status_code=422, detail='Требуется event.request.')
        if any(request.id == event.request.id for request in data.requests):
            raise HTTPException(status_code=409, detail='Заявка с таким ID уже существует.')
        data.requests.append(event.request.model_copy(update={'priority': 'urgent'}))
    elif event.type == 'cancel_request':
        request = next((request for request in data.requests if request.id == event.request_id), None)
        if request is None:
            raise HTTPException(status_code=404, detail='Заявка не найдена.')
        request.status = 'cancelled'
    else:
        engineer = next((engineer for engineer in data.engineers if engineer.id == event.engineer_id), None)
        if engineer is None:
            raise HTTPException(status_code=404, detail='Инженер не найден.')
        engineer.available = False
    plan = plan_dataset(data)
    database.save_dataset(data, plan)
    return plan
