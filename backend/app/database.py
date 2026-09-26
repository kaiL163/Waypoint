import os
from datetime import datetime, timezone

from geoalchemy2 import Geometry, WKTElement
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, delete, insert, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import URL

from .models import Dataset, Plan

engine = create_engine(os.getenv('DATABASE_URL') or URL.create('postgresql+psycopg',username=os.getenv('DB_USER','waypoint'),password=os.getenv('DB_PASSWORD','waypoint_dev_password'),host=os.getenv('DB_HOST','localhost'),port=int(os.getenv('DB_PORT','5432')),database=os.getenv('DB_NAME','waypoint')),pool_pre_ping=True)
metadata = MetaData()
state = Table('waypoint_state_v2',metadata,Column('id',Integer,primary_key=True),Column('revision',Integer,nullable=False),Column('payload',JSONB,nullable=False))
history = Table('waypoint_history_v2',metadata,Column('revision',Integer,primary_key=True),Column('saved_at',DateTime(timezone=True),nullable=False),Column('payload',JSONB,nullable=False))
locations = Table('waypoint_locations_v2',metadata,Column('key',String(260),primary_key=True),Column('point',Geometry('POINT',srid=4326,spatial_index=True),nullable=False))


class StaleState(Exception):
    pass


def initialize():
    with engine.begin() as connection:
        connection.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        metadata.create_all(connection)
        connection.execute(text("INSERT INTO waypoint_state_v2 (id,revision,payload) VALUES (1,0,'{}'::jsonb) ON CONFLICT (id) DO NOTHING"))


def load():
    with engine.connect() as connection:
        row=connection.execute(select(state).where(state.c.id==1)).mappings().one()
    payload=row['payload']
    data=Dataset.model_validate(payload['dataset']) if payload.get('dataset') else None
    if data:
        data.revision=row['revision']
    return data,Plan.model_validate(payload['plan']) if payload.get('plan') else None,Plan.model_validate(payload['baseline']) if payload.get('baseline') else None,row['revision']


def save(data: Dataset, plan: Plan | None, baseline: Plan | None, expected: int):
    with engine.begin() as connection:
        revision=connection.execute(select(state.c.revision).where(state.c.id==1).with_for_update()).scalar_one()
        if revision!=expected:
            raise StaleState('Данные изменились в другой вкладке. Обновите страницу и повторите действие.')
        saved=data.model_copy(update={'revision':revision+1})
        payload={'dataset':saved.model_dump(mode='json'),'plan':plan.model_dump(mode='json') if plan else None,'baseline':baseline.model_dump(mode='json') if baseline else None}
        connection.execute(update(state).where(state.c.id==1).values(revision=revision+1,payload=payload))
        connection.execute(insert(history).values(revision=revision+1,saved_at=datetime.now(timezone.utc),payload=payload))
        connection.execute(delete(locations))
        for kind,items in [('engineer',saved.engineers),('request',saved.requests)]:
            for item in items:
                point=item.startLocation if kind=='engineer' else item.location
                connection.execute(insert(locations).values(key=f'{kind}:{item.id}',point=WKTElement(f'POINT({point.lng} {point.lat})',srid=4326)))
    return saved
