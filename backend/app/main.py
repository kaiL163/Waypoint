from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .demo import get_demo, list_demos
from .io_data import read_dataset, validate_dataset
from .models import (
    Dataset,
    DemoScenarioInfo,
    Plan,
    ReplanBody,
    ReplanResponse,
    ServiceRequest,
    Strategy,
)
from .planning import changes_between, create_urgent, make_plan

app = FastAPI(title="Waypoint API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_store: dict[str, Dataset | Plan | None] = {"dataset": None, "plan": None}


def _require_dataset() -> Dataset:
    dataset = _store["dataset"]
    if dataset is None:
        raise HTTPException(status_code=404, detail="Данные ещё не загружены.")
    return dataset  # type: ignore[return-value]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/engineers")
def get_engineers():
    return _require_dataset().engineers


@app.get("/api/requests")
def get_requests():
    return _require_dataset().requests


@app.get("/api/planning/current")
def get_current_plan() -> Plan:
    plan = _store["plan"]
    if plan is None:
        raise HTTPException(status_code=404, detail="План ещё не построен.")
    return plan  # type: ignore[return-value]


@app.post("/api/planning/optimize")
def optimize(body: Dataset, strategy: Strategy = Query(default="optimized")) -> Plan:
    dataset = validate_dataset(body)
    plan = make_plan(dataset, strategy)
    _store["dataset"] = dataset
    if strategy == "optimized":
        _store["plan"] = plan
    return plan


@app.post("/api/planning/replan")
def replan(body: ReplanBody) -> ReplanResponse:
    dataset = validate_dataset(body.dataset)
    event = body.event

    if event.type == "urgent_request":
        if event.request is not None:
            urgent = event.request
        elif event.input is not None:
            urgent = ServiceRequest.model_validate(
                create_urgent(event.input.model_dump(), [r.id for r in dataset.requests])
            )
        else:
            raise HTTPException(status_code=400, detail="Для срочной заявки нужны request или input.")
        dataset = Dataset(engineers=dataset.engineers, requests=[*dataset.requests, urgent])
    elif event.type == "cancel_request":
        request_id = event.requestId or (event.request.id if event.request else None)
        if not request_id:
            raise HTTPException(status_code=400, detail="Укажите requestId для отмены.")
        dataset = Dataset(
            engineers=dataset.engineers,
            requests=[
                r.model_copy(update={"status": "cancelled"}) if r.id == request_id else r
                for r in dataset.requests
            ],
        )
    elif event.type == "engineer_unavailable":
        if not event.engineerId:
            raise HTTPException(status_code=400, detail="Укажите engineerId.")
        dataset = Dataset(
            engineers=[
                e.model_copy(update={"available": False}) if e.id == event.engineerId else e
                for e in dataset.engineers
            ],
            requests=dataset.requests,
        )
    else:
        raise HTTPException(status_code=400, detail="Неизвестный тип события.")

    plan = make_plan(dataset, "optimized")
    changes = changes_between(body.previousPlan, plan, dataset) if body.previousPlan else []
    _store["dataset"] = dataset
    _store["plan"] = plan
    return ReplanResponse(dataset=dataset, plan=plan, changes=changes)


@app.get("/api/data/demos", response_model=list[DemoScenarioInfo])
def demos() -> list[DemoScenarioInfo]:
    return list_demos()


@app.post("/api/data/demo")
def load_demo(scenario: str | None = Query(default=None)) -> Dataset:
    try:
        dataset = get_demo(scenario)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    dataset = validate_dataset(dataset)
    _store["dataset"] = dataset
    _store["plan"] = None
    return dataset


@app.post("/api/data/upload")
async def upload(files: list[UploadFile] = File(...)) -> Dataset:
    if not files:
        raise HTTPException(status_code=400, detail="Загрузите хотя бы один файл.")
    dataset = await read_dataset(files)
    _store["dataset"] = dataset
    _store["plan"] = None
    return dataset
