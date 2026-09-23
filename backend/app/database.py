from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

from geoalchemy2 import Geometry, WKTElement
from sqlalchemy import Boolean, DateTime, String, create_engine, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .schemas import Dataset, Plan

DATABASE_URL = os.getenv('DATABASE_URL') or URL.create(
    'postgresql+psycopg',
    username=os.getenv('DB_USER', 'waypoint'),
    password=os.getenv('DB_PASSWORD', 'waypoint'),
    host=os.getenv('DB_HOST', 'localhost'),
    port=int(os.getenv('DB_PORT', '5432')),
    database=os.getenv('DB_NAME', 'waypoint'),
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine)


class Base(DeclarativeBase):
    pass


class EngineerRow(Base):
    __tablename__ = 'engineers'
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    start_location = mapped_column(Geometry('POINT', srid=4326, spatial_index=True), nullable=False)


class RequestRow(Base):
    __tablename__ = 'service_requests'
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    location = mapped_column(Geometry('POINT', srid=4326, spatial_index=True), nullable=False)


class PlanRow(Base):
    __tablename__ = 'plans'
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


def initialize() -> None:
    with engine.begin() as connection:
        connection.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
    Base.metadata.create_all(engine)


def get_dataset() -> Dataset:
    with SessionLocal() as session:
        engineers = [row.payload for row in session.scalars(select(EngineerRow).order_by(EngineerRow.id))]
        requests = [row.payload for row in session.scalars(select(RequestRow).order_by(RequestRow.id))]
    return Dataset(engineers=engineers, requests=requests)


def save_dataset(data: Dataset, plan: Plan | None = None) -> None:
    with SessionLocal.begin() as session:
        session.query(PlanRow).delete()
        session.query(RequestRow).delete()
        session.query(EngineerRow).delete()
        for item in data.engineers:
            point = item.start_location
            session.add(EngineerRow(id=item.id, payload=item.model_dump(by_alias=True), start_location=WKTElement(f'POINT({point.lng} {point.lat})', srid=4326)))
        for item in data.requests:
            point = item.location
            session.add(RequestRow(id=item.id, payload=item.model_dump(by_alias=True), location=WKTElement(f'POINT({point.lng} {point.lat})', srid=4326)))
        if plan is not None:
            session.add(PlanRow(payload=plan.model_dump(by_alias=True)))


def get_current_plan() -> Plan | None:
    with SessionLocal() as session:
        row = session.scalar(select(PlanRow).where(PlanRow.current.is_(True)).order_by(PlanRow.created_at.desc()).limit(1))
        return Plan.model_validate(row.payload) if row else None
