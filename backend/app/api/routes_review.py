"""Gaps, corrections, review queue, routing actions, monitoring metrics and evals."""

from fastapi import APIRouter, HTTPException

from app.db import feedback_repo
from app.evals import runner
from app.evals.synthesize import synthesize
from app.models.api import EvalRunBody, ReviewBody, SendRoutingBody, SynthesizeBody
from app.observability import metrics

router = APIRouter(prefix="/api")


@router.get("/gaps")
def list_gaps(type: str | None = None, status: str | None = None) -> list[dict]:  # noqa: A002
    return feedback_repo.list_gaps(type, status)


@router.get("/gaps/{gap_id}")
def get_gap(gap_id: str) -> dict:
    gap = feedback_repo.get_gap(gap_id)
    if not gap:
        raise HTTPException(status_code=404, detail="gap not found")
    return gap


@router.get("/review-queue")
def review_queue(status: str | None = None, type: str | None = None) -> dict:  # noqa: A002
    return {"counts": feedback_repo.gap_counts(), "items": feedback_repo.list_gaps(type, status)}


@router.patch("/review-queue/{gap_id}")
def review(gap_id: str, body: ReviewBody) -> dict:
    gap = feedback_repo.review_gap(gap_id, body.review_status, body.reviewer_note)
    if not gap:
        raise HTTPException(status_code=404, detail="gap not found")
    return gap


@router.post("/routing/{routing_id}/send")
def send_routing(routing_id: str, body: SendRoutingBody) -> dict:
    """Records the (edited) question as sent. Delivery is intentionally log-only."""
    if not feedback_repo.get_routing(routing_id):
        raise HTTPException(status_code=404, detail="routing suggestion not found")
    feedback_repo.mark_routing_sent(routing_id, body.question, body.sent_by)
    return feedback_repo.get_routing(routing_id)


@router.post("/routing/{routing_id}/dismiss")
def dismiss_routing(routing_id: str) -> dict:
    if not feedback_repo.get_routing(routing_id):
        raise HTTPException(status_code=404, detail="routing suggestion not found")
    feedback_repo.dismiss_routing(routing_id)
    return feedback_repo.get_routing(routing_id)


@router.get("/metrics")
def get_metrics(window: str = "24h") -> dict:
    if window not in metrics.WINDOWS:
        raise HTTPException(
            status_code=400, detail=f"window must be one of {list(metrics.WINDOWS)}"
        )
    return metrics.summary(window)


@router.get("/evals")
def list_evals() -> dict:
    return {"datasets": runner.dataset_info(), "runs": runner.list_runs()}


@router.post("/evals/run", status_code=202)
def run_eval(body: EvalRunBody | None = None) -> dict:
    dataset = (body or EvalRunBody()).dataset
    try:
        return {"run_id": runner.start_background(dataset), "dataset": dataset}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/evals/{run_id}")
def get_eval(run_id: str) -> dict:
    run = runner.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="eval run not found")
    return run


@router.post("/evals/synthesize")
def synthesize_cases(body: SynthesizeBody | None = None) -> dict:
    return {"generated": synthesize((body or SynthesizeBody()).n)}
