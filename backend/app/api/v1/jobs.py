from __future__ import annotations

import asyncio

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.response import success_response
from app.scheduler.jobs import DAILY_LEAD_GENERATION_JOB
from app.scheduler.service import get_scheduler_service
from app.schemas.common import APIResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])

_manual_run_lock = asyncio.Lock()
_manual_run_active = False


async def _execute_manual_pipeline() -> None:
    global _manual_run_active
    try:
        await get_scheduler_service().run_job(DAILY_LEAD_GENERATION_JOB)
    finally:
        async with _manual_run_lock:
            _manual_run_active = False


@router.post("/run-now", response_model=APIResponse[dict])
async def run_pipeline_now() -> APIResponse[dict] | JSONResponse:
    """Manually start the daily lead-generation pipeline (does not change the scheduled time)."""
    global _manual_run_active
    async with _manual_run_lock:
        if _manual_run_active:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "success": False,
                    "message": "Lead generation is already running",
                    "data": {"job_name": DAILY_LEAD_GENERATION_JOB, "status": "running"},
                    "request_id": "",
                },
            )
        _manual_run_active = True

    asyncio.create_task(_execute_manual_pipeline())
    return success_response(
        message="Lead generation started. The daily schedule is unchanged.",
        data={
            "job_name": DAILY_LEAD_GENERATION_JOB,
            "status": "started",
        },
    )


@router.get("/run-now/status", response_model=APIResponse[dict])
async def run_pipeline_status() -> APIResponse[dict]:
    async with _manual_run_lock:
        active = _manual_run_active
    return success_response(
        message="Manual run status retrieved",
        data={
            "job_name": DAILY_LEAD_GENERATION_JOB,
            "status": "running" if active else "idle",
        },
    )
