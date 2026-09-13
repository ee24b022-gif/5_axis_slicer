from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from dependencies import get_db
from job_lifecycle import InvalidTransitionError
from local_executor import LocalJobExecutor
from contextlib import asynccontextmanager
from routers.meshes import router as meshes_router
from routers.jobs import router as jobs_router
from routers.machine_profiles import router as machine_profiles_router
from routers.auth import router as auth_router
from routers.api_keys import router as api_keys_router

from config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env != "production":
        executor = LocalJobExecutor(max_workers=settings.worker_concurrency)
        app.state.executor = executor
        yield
        executor.shutdown()
    else:
        app.state.executor = None
        yield

app = FastAPI(
    title="5-Axis Slicer API",
    version="0.1.0",
    description="Core slicing API engine",
    lifespan=lifespan
)

app.include_router(auth_router)
app.include_router(api_keys_router)
app.include_router(meshes_router)
app.include_router(jobs_router)
app.include_router(machine_profiles_router)

import redis
from logging_config import setup_logging

setup_logging()

@app.exception_handler(InvalidTransitionError)
async def invalid_transition_exception_handler(request: Request, exc: InvalidTransitionError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "code": "INVALID_TRANSITION"}
    )

@app.get("/health")
def health_check():
    """Liveness probe"""
    return {"status": "healthy"}

@app.get("/readiness")
def readiness_check(db: Session = Depends(get_db)):
    """Readiness probe testing DB and Redis connectivity"""
    try:
        # Check Database
        db.execute(text("SELECT 1"))
        
        # Check Redis
        r = redis.Redis.from_url(settings.redis_url)
        if not r.ping():
            raise Exception("Redis ping failed")
            
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Dependencies unavailable: {str(e)}")
