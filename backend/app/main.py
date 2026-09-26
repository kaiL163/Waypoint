from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import database
from .demo import get_demo, list_demos
from .io_data import read_dataset, validate_dataset
from .models import Dataset, DemoScenarioInfo, Plan, ReplanBody, ReplanResponse, ServiceRequest, Strategy
from .planning import changes_between, create_urgent
from .solver import make_plan, frozen_prefix
from .routing import RoutingUnavailable


@asynccontextmanager
async def lifespan(app):
    database.initialize()
    yield


app=FastAPI(title="Waypoint API",version="2.0.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(','),allow_methods=['*'],allow_headers=['*'])


@app.exception_handler(RoutingUnavailable)
async def routing_error(_,exc):
    return JSONResponse(status_code=503,content={'detail':str(exc)})


@app.exception_handler(database.StaleState)
async def stale_error(_,exc):
    return JSONResponse(status_code=409,content={'detail':str(exc)})


def checked(data):
    dataset=validate_dataset(data)
    current,plan,baseline,revision=database.load()
    if current and dataset.revision!=revision:
        raise database.StaleState('Открыта устаревшая версия данных. Обновите страницу.')
    return dataset,plan,revision


@app.get('/api/health')
def health():
    with database.engine.connect() as connection:
        connection.execute(text('SELECT 1'))
    return {'status':'ok'}


@app.get('/api/state')
def current_state():
    data,plan,baseline,revision=database.load()
    return {'dataset':data,'plan':plan,'baseline':baseline,'revision':revision}


@app.get('/api/engineers')
def get_engineers():
    data,*_=database.load()
    return data.engineers if data else []


@app.get('/api/requests')
def get_requests():
    data,*_=database.load()
    return data.requests if data else []


@app.get('/api/planning/current',response_model=Plan)
def get_current_plan():
    _,plan,_,_=database.load()
    if plan is None:
        raise HTTPException(404,'План ещё не построен.')
    return plan


@app.post('/api/planning/compare',response_model=ReplanResponse)
def compare(body: Dataset):
    dataset,previous,revision=checked(body)
    at=previous.replannedAt if previous else None
    baseline=make_plan(dataset,'baseline',previous,at)
    plan=make_plan(dataset,'optimized',previous,at)
    changes=changes_between(previous,plan,dataset) if previous else []
    saved=database.save(dataset,plan,baseline,revision)
    return ReplanResponse(dataset=saved,plan=plan,baseline=baseline,changes=changes)


@app.post('/api/planning/optimize',response_model=Plan)
def optimize(body: Dataset,strategy: Strategy=Query(default='optimized')):
    if strategy=='baseline':
        # A read-only calculation must not replace the dataset or invalidate its revision.
        return make_plan(validate_dataset(body),'baseline')
    return compare(body).plan


@app.post('/api/planning/replan',response_model=ReplanResponse)
def replan(body: ReplanBody):
    _,previous,revision=checked(body.dataset)
    stored,_,_,_=database.load()
    if stored is None:
        raise HTTPException(404,'Сначала загрузите данные и постройте план.')
    dataset=stored.model_copy(deep=True)
    event=body.event
    if previous and previous.replannedAt and event.eventTime<previous.replannedAt:
        raise HTTPException(422,'Время события не может предшествовать предыдущему перепланированию.')
    locked={s.requestId for stops in frozen_prefix(dataset,previous,event.eventTime).values() for s in stops}
    if event.type=='urgent_request':
        if event.request:
            urgent=event.request.model_copy(update={'priority':'urgent','eventTime':event.eventTime})
        elif event.input:
            urgent=ServiceRequest.model_validate(create_urgent(event.input.model_dump(),[r.id for r in dataset.requests]))
            urgent.eventTime=event.eventTime
        else:
            raise HTTPException(422,'Для срочной заявки нужны request или input.')
        if any(r.id==urgent.id for r in dataset.requests):
            raise HTTPException(409,'Заявка с таким ID уже существует.')
        dataset.requests.append(urgent)
    elif event.type=='cancel_request':
        request=next((r for r in dataset.requests if r.id==event.requestId),None)
        if not request:
            raise HTTPException(404,'Заявка не найдена.')
        if request.id in locked:
            raise HTTPException(409,'Поездка или работа по этой заявке уже началась. В прототипе её нельзя отменить задним числом.')
        request.status='cancelled'
    else:
        engineer=next((e for e in dataset.engineers if e.id==event.engineerId),None)
        if not engineer:
            raise HTTPException(404,'Инженер не найден.')
        engineer.available=False
    dataset=validate_dataset(Dataset.model_validate(dataset.model_dump()))
    baseline=make_plan(dataset,'baseline',previous,event.eventTime)
    plan=make_plan(dataset,'optimized',previous,event.eventTime)
    changes=changes_between(previous,plan,dataset) if previous else []
    saved=database.save(dataset,plan,baseline,revision)
    return ReplanResponse(dataset=saved,plan=plan,baseline=baseline,changes=changes)


@app.get('/api/data/demos',response_model=list[DemoScenarioInfo])
def demos():
    return list_demos()


@app.post('/api/data/demo',response_model=Dataset)
def load_demo(scenario: str | None=Query(default=None)):
    try:
        data=validate_dataset(get_demo(scenario))
    except ValueError as exc:
        raise HTTPException(404,str(exc)) from exc
    *_,revision=database.load()
    return database.save(data,None,None,revision)


@app.post('/api/data/upload',response_model=Dataset)
async def upload(files: list[UploadFile]=File(...)):
    if not files or len(files)>10:
        raise HTTPException(400,'Выберите от 1 до 10 файлов.')
    *_,revision=database.load()
    data=await read_dataset(files)
    return database.save(data,None,None,revision)
