from fastapi import APIRouter, HTTPException
from app.celery_app import celery_app

router = APIRouter()


@router.get("/{task_id}/status")
def get_task_status(task_id: str):
    """Poll the status of a Celery async task by its ID."""
    result = celery_app.AsyncResult(task_id)
    response = {"state": result.state, "task_id": task_id}
    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.result)
    elif result.state in ("STARTED", "RETRY"):
        response["info"] = str(result.info) if result.info else None
    return response
