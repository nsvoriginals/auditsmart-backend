from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from bson import ObjectId
import base64
from app.utils.auth import get_current_user
from app.database import get_db
from app.agents.pipeline import run_audit_pipeline
from app.config import settings

router = APIRouter()


class AuditRequest(BaseModel):
    contract_code: str
    contract_name: Optional[str] = "Contract"
    chain: Optional[str] = "ethereum"


def serialize_audit(a: dict) -> dict:
    """Serialize MongoDB audit document for API response."""
    a["id"] = str(a.pop("_id"))
    a["user_id"] = str(a.get("user_id", ""))
    if isinstance(a.get("created_at"), datetime):
        a["created_at"] = a["created_at"].isoformat()
    # Don't send pdf_base64 in list responses (too large)
    # Client should use /report/{id}/pdf endpoint instead
    a.pop("pdf_base64", None)
    return a


def serialize_audit_full(a: dict) -> dict:
    """Serialize with PDF data included."""
    a["id"] = str(a.pop("_id"))
    a["user_id"] = str(a.get("user_id", ""))
    if isinstance(a.get("created_at"), datetime):
        a["created_at"] = a["created_at"].isoformat()
    return a


@router.post("/scan")
async def scan_contract(
    req: AuditRequest,
    current_user: dict = Depends(get_current_user)
):
    db = get_db()
    user = current_user
    plan = user.get("plan", "free")
    free_left = user.get("free_audits_remaining", 0)

    # Check quota
    if plan == "free" and free_left <= 0:
        raise HTTPException(402,
                            "Free audit limit reached. Please upgrade to Pro.")

    # v2.0 — Better validation
    code = req.contract_code.strip()
    if not code or len(code) < 10:
        raise HTTPException(400, "Contract code is too short or empty")

    if len(code) > settings.MAX_CONTRACT_SIZE:
        raise HTTPException(400,
                            f"Contract too large. Max {settings.MAX_CONTRACT_SIZE} chars.")

    # Check it looks like Solidity
    if "pragma" not in code.lower() and "contract " not in code.lower():
        raise HTTPException(400,
                            "Code doesn't appear to be a Solidity contract. "
                            "Must contain 'pragma' or 'contract' keyword.")

    # Run multi-agent pipeline v2.0
    try:
        result = await run_audit_pipeline(
            contract_code=code,
            contract_name=req.contract_name
        )
    except Exception as e:
        print(f"❌ Audit pipeline error: {e}")
        raise HTTPException(500, f"Audit pipeline error: {str(e)}")

    # Save to DB (including PDF base64)
    audit_doc = {
        "user_id": user["_id"],
        "contract_name": req.contract_name,
        "chain": req.chain,
        "contract_code_hash": hash(code),
        "risk_level": result.get("risk_level", "unknown"),
        "risk_score": result.get("risk_score", 0),
        "total_findings": result.get("total_findings", 0),
        "raw_findings_count": result.get("raw_findings_count", 0),
        "critical_count": result.get("critical_count", 0),
        "high_count": result.get("high_count", 0),
        "medium_count": result.get("medium_count", 0),
        "low_count": result.get("low_count", 0),
        "info_count": result.get("info_count", 0),
        "findings": result.get("findings", []),
        "summary": result.get("summary", ""),
        "agents_used": result.get("agents_used", []),
        "scan_duration_ms": result.get("scan_duration_ms", 0),
        "pdf_base64": result.get("pdf_base64", ""),
        "pdf_available": result.get("pdf_available", False),
        "version": "2.0",
        "created_at": datetime.utcnow()
    }
    insert_result = await db.audits.insert_one(audit_doc)
    audit_doc["_id"] = insert_result.inserted_id

    # Deduct free audit if on free plan
    if plan == "free":
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$inc": {"free_audits_remaining": -1}}
        )

    # Return response (without heavy PDF data)
    response = serialize_audit(audit_doc.copy())
    response["pdf_available"] = result.get("pdf_available", False)
    return response


@router.get("/history")
async def get_history(
    limit: int = 10,
    current_user: dict = Depends(get_current_user)
):
    db = get_db()
    # v2.0 — Exclude pdf_base64 from list queries (too heavy)
    cursor = db.audits.find(
        {"user_id": current_user["_id"]},
        {"pdf_base64": 0}  # Exclude PDF data from list
    ).sort("created_at", -1).limit(limit)

    audits = await cursor.to_list(limit)
    return {"audits": [serialize_audit(a) for a in audits]}


@router.get("/report/{audit_id}")
async def get_report(
    audit_id: str,
    current_user: dict = Depends(get_current_user)
):
    db = get_db()
    try:
        oid = ObjectId(audit_id)
    except Exception:
        raise HTTPException(400, "Invalid audit ID")

    # v2.0 — Exclude PDF from JSON response (use /pdf endpoint)
    audit = await db.audits.find_one(
        {"_id": oid, "user_id": current_user["_id"]},
        {"pdf_base64": 0}
    )
    if not audit:
        raise HTTPException(404, "Audit not found")

    return serialize_audit(audit)


# ═══ v2.0 — NEW: PDF Download Endpoint ═══
@router.get("/report/{audit_id}/pdf")
async def download_pdf(
    audit_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Download the PDF audit report for a specific audit."""
    db = get_db()
    try:
        oid = ObjectId(audit_id)
    except Exception:
        raise HTTPException(400, "Invalid audit ID")

    audit = await db.audits.find_one(
        {"_id": oid, "user_id": current_user["_id"]},
        {"pdf_base64": 1, "pdf_available": 1, "contract_name": 1}
    )
    if not audit:
        raise HTTPException(404, "Audit not found")

    if not audit.get("pdf_available") or not audit.get("pdf_base64"):
        raise HTTPException(404, "PDF not available for this audit. "
                            "Re-run the audit to generate a PDF report.")

    # Decode base64 to bytes
    try:
        pdf_bytes = base64.b64decode(audit["pdf_base64"])
    except Exception:
        raise HTTPException(500, "Failed to decode PDF data")

    contract_name = audit.get("contract_name", "Contract")
    filename = f"AuditSmart_Report_{contract_name}_{audit_id[:8]}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        }
    )


# ═══ v2.0 — NEW: PDF as base64 endpoint (for frontend rendering) ═══
@router.get("/report/{audit_id}/pdf-data")
async def get_pdf_data(
    audit_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get PDF as base64 for in-browser display."""
    db = get_db()
    try:
        oid = ObjectId(audit_id)
    except Exception:
        raise HTTPException(400, "Invalid audit ID")

    audit = await db.audits.find_one(
        {"_id": oid, "user_id": current_user["_id"]},
        {"pdf_base64": 1, "pdf_available": 1}
    )
    if not audit:
        raise HTTPException(404, "Audit not found")

    if not audit.get("pdf_available") or not audit.get("pdf_base64"):
        raise HTTPException(404, "PDF not available for this audit")

    return {
        "pdf_base64": audit["pdf_base64"],
        "pdf_available": True
    }
