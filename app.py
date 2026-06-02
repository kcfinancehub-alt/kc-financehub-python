"""KC FinanceHub Python AI service – ratio analysis, CMA, Indian GAAP."""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from agents.brain import generate_financial_report, validate_document

logger = logging.getLogger("kc_financehub")

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
    """Background task that generates a financial report and writes it to Supabase.

    Errors are caught, logged, and written back to the report row so the job
    is never silently stuck.  Every failure must be surfaced to the Watchdog
    agent via the error_detail column so admins can escalate.
    """
    report_id = payload["report_id"]
    org_id = payload["org_id"]
    document_ids = payload["document_ids"]
    report_type = payload["report_type"]

    try:
        content = generate_financial_report(
            org_id=org_id,
            document_ids=document_ids,
            report_type=report_type,
        )
        update_report_in_supabase(report_id, content)

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception(
            "[process_report_job] Failed for report_id=%s: %s", report_id, exc
        )
        # Surface the error in Supabase so admins / Watchdog can react
        update_report_in_supabase(
            report_id,
            {
                "status_override": "error",
                "compliance_notes": (
                    "Report generation failed — manual review required. "
                    f"Error: {exc!r}"
                ),
                "ratio_analysis": {},
            },
        )
        raise  # Re-raise so FastAPI background task logs it too


def update_report_in_supabase(report_id: str, content: dict[str, Any]) -> None:
    """PATCH the financial_reports row in Supabase with the generated content.

    Uses the service-role key (bypasses RLS) since this runs in the Python
    backend, not in a user session.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        logger.warning(
            "[update_report_in_supabase] SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY "
            "not set — skipping DB write."
        )
        return

    import httpx  # local import so the module loads without httpx if not needed

    url = f"{SUPABASE_URL}/rest/v1/financial_reports?id=eq.{report_id}"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    # Determine final status — use status_override if the brain injected one
    status = content.pop("status_override", "pending_review")

    body = {
        "content": content,
        "compliance_notes": content.get("compliance_notes", {}).get("body", "")
        if isinstance(content.get("compliance_notes"), dict)
        else content.get("compliance_notes", ""),
        "status": status,
    }

    response = httpx.patch(url, headers=headers, json=body, timeout=30.0)
    response.raise_for_status()  # Raise on 4xx/5xx so the caller can handle it
