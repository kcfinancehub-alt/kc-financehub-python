"""KC FinanceHub Python AI service – ratio analysis, CMA, Indian GAAP."""

from __future__ import annotations

import os
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from agents.brain import generate_financial_report, validate_document

app = FastAPI(title="KC FinanceHub AI Service", version="1.0.0")

INTERNAL_SECRET = os.getenv("INTERNAL_API_SECRET", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def verify_internal(authorization: str = Header(default="")) -> None:
    expected = f"Bearer {INTERNAL_SECRET}"
    if not INTERNAL_SECRET or authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


class ValidateRequest(BaseModel):
    document_id: str
    org_id: str


class ReportJobRequest(BaseModel):
    report_id: str
    org_id: str
    document_ids: list[str]
    report_type: str
    manual_override: bool = False
    job_id: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "kc-financehub-ai"}


@app.post("/validate", dependencies=[Depends(verify_internal)])
def validate(req: ValidateRequest) -> dict[str, str]:
    validate_document(req.document_id, req.org_id)
    return {"status": "validated", "document_id": req.document_id}


@app.post("/jobs/report", dependencies=[Depends(verify_internal)])
def enqueue_report(
    req: ReportJobRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    background_tasks.add_task(process_report_job, req.model_dump())
    return {"status": "accepted", "job_id": req.job_id}


def process_report_job(payload: dict[str, Any]) -> None:
    report_id = payload["report_id"]
    org_id = payload["org_id"]
    document_ids = payload["document_ids"]
    report_type = payload["report_type"]

    content = generate_financial_report(
        org_id=org_id,
        document_ids=document_ids,
        report_type=report_type,
    )

    update_report_in_supabase(report_id, content)


def update_report_in_supabase(report_id: str, content: dict[str, Any]) -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return

    import httpx

    url = f"{SUPABASE_URL}/rest/v1/financial_reports?id=eq.{report_id}"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    body = {
        "content": content,
        "compliance_notes": content.get("compliance_notes", {}).get("body", ""),
        "status": "pending_review",
    }
    httpx.patch(url, headers=headers, json=body, timeout=30.0)
