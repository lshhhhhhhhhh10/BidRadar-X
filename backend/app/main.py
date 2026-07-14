from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.tasks import router as tasks_router
from .api.projects import router as projects_router
from .api.subscriptions import router as subscriptions_router
from .services.publisher import REPORT_DIR
from .services.scheduler import LocalScheduler, SystemClock
from .services.scheduler_worker import SchedulerWorker
from .services.task_runner import TaskRunner
from .storage.database import initialize_database
from .storage.repository import Repository


initialize_database()
REPORT_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(application: FastAPI):
    clock = SystemClock()
    repository = Repository()
    worker = SchedulerWorker(
        repository=repository,
        task_runner=TaskRunner(repository=repository),
        scheduler=LocalScheduler(clock=clock),
        clock=clock,
    )
    worker_task = asyncio.create_task(worker.run_forever())
    application.state.scheduler_worker = worker
    try:
        yield
    finally:
        worker.stop()
        await worker_task

app = FastAPI(
    title="招投标情报工作台 API",
    version="0.1.0",
    description="本地运行的模拟工作流后端。",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(tasks_router)
app.include_router(projects_router)
app.include_router(subscriptions_router)
app.mount("/reports", StaticFiles(directory=REPORT_DIR), name="reports")


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "招投标情报工作台 API", "docs": "/docs"}
