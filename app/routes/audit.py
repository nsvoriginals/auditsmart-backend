from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from bson import ObjectId
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
        raise HTTPException(402, "Free audit limit reached. Please upgrade to Pro.")

    if not req.contract_code or len(req.contract_code.strip()) < 10:
        raise HTTPException(400, "Contract code is too short or empty")

    # Run multi-agent pipeline
    try:
        result = await run_audit_pipeline(
            contract_code=req.contract_code,
            contract_name=req.contract_name
        )
    except Exception as e:
        raise HTTPException(500, f"Audit pipeline error: {str(e)}")

    # Save to DB
    audit_doc = {
        "user_id": user["_id"],
        "contract_name": req.contract_name,
        "chain": req.chain,
        "contract_code_hash": hash(req.contract_code),
        "risk_level": result.get("risk_level", "unknown"),
        "risk_score": result.get("risk_score", 0),
        "total_findings": result.get("total_findings", 0),
        "critical_count": result.get("critical_count", 0),
        "high_count": result.get("high_count", 0),
        "medium_count": result.get("medium_count", 0),
        "low_count": result.get("low_count", 0),
        "findings": result.get("findings", []),
        "summary": result.get("summary", ""),
        "agents_used": result.get("agents_used", []),
        "scan_duration_ms": result.get("scan_duration_ms", 0),
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

    return serialize_audit(audit_doc)

@router.get("/history")
async def get_history(
    limit: int = 10,
    current_user: dict = Depends(get_current_user)
):
    db = get_db()
    cursor = db.audits.find(
        {"user_id": current_user["_id"]}
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

    audit = await db.audits.find_one({
        "_id": oid,
        "user_id": current_user["_id"]
    })
    if not audit:
        raise HTTPException(404, "Audit not found")

    return serialize_audit(audit)
