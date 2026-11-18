from fastapi import APIRouter, Body, Request
from fastapi.responses import Response

from .service import execute, recheck, sign

router = APIRouter(tags=["M6-批次复核"])


@router.get("/runs")
def page(request: Request):
    data = execute({"store": request.app.state.store})
    return request.app.state.templates.TemplateResponse(
        request,
        "m6_runs.html",
        {
            "title": "批次复核",
            "data": data,
            "approvals": request.app.state.store.approvals(),
        },
    )


@router.get("/api/runs")
def runs(request: Request):
    execute({"store": request.app.state.store})
    return {
        "runs": request.app.state.store.all(),
        "approvals": request.app.state.store.approvals(),
    }


@router.post("/api/runs/approve")
def approve(request: Request, payload: dict = Body(default={})):
    return sign(payload, store=request.app.state.store)


@router.get("/api/runs/{batch_key}/recheck")
def recheck_batch(batch_key: str, request: Request):
    return recheck(request.app.state.store, batch_key)


@router.get("/api/export/allocations.csv")
def export(request: Request):
    data = execute({"store": request.app.state.store})
    return Response(
        data["csv"],
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=evidence.csv"},
    )
