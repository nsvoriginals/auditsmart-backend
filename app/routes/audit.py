"""
AuditSmart v3.0 — Audit Routes

Endpoints:
  POST /audit/scan          → Run audit (plan-based AI routing)
  POST /audit/deep          → Purchase + run Deep Audit ($20)
  GET  /audit/history       → User's audit history
  GET  /audit/report/{id}   → Full audit report
  GET  /audit/report/{id}/pdf → Download PDF
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from bson import ObjectId
import base64
import razorpay
import hashlib
import hmac

from app.utils.auth import get_current_user
from app.database import get_db
from app.agents.pipeline import run_audit_pipeline
from app.config import settings

router = APIRouter()


# ── REQUEST MODELS ─────────────────────────────────────────────────────────────
class AuditRequest(BaseModel):
    contract_code: str
    contract_name: Optional[str] = "Contract"
    chain: Optional[str] = "ethereum"


class DeepAuditOrderRequest(BaseModel):
    contract_code: str
    contract_name: Optional[str] = "Contract"
    chain: Optional[str] = "ethereum"


class DeepAuditVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    contract_code: str
    contract_name: Optional[str] = "Contract"
    chain: Optional[str] = "ethereum"


# ── HELPERS ────────────────────────────────────────────────────────────────────
def get_razorpay_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        return None
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def validate_contract(code: str):
    code = code.strip()
    if not code or len(code) < 10:
        raise HTTPException(400, "Contract code is too short or empty")
    if len(code) > settings.MAX_CONTRACT_SIZE:
        raise HTTPException(400, f"Contract too large. Max {settings.MAX_CONTRACT_SIZE} chars.")
    if "pragma" not in code.lower() and "contract " not in code.lower():
        raise HTTPException(400, "Does not look like Solidity. Must contain 'pragma' or 'contract'.")
    return code


def serialize_audit(a: dict) -> dict:
    a["id"] = str(a.pop("_id"))
    a["user_id"] = str(a.get("user_id", ""))
    if isinstance(a.get("created_at"), datetime):
        a["created_at"] = a["created_at"].isoformat()
    a.pop("pdf_base64", None)
    a.pop("thinking_chain", None)  # Don't send in list responses
    return a


def serialize_audit_full(a: dict) -> dict:
    a["id"] = str(a.pop("_id"))
    a["user_id"] = str(a.get("user_id", ""))
    if isinstance(a.get("created_at"), datetime):
        a["created_at"] = a["created_at"].isoformat()
    a.pop("pdf_base64", None)
    return a


async def save_audit(db, user: dict, req, result: dict, plan_used: str) -> dict:
    """Save audit result to MongoDB and return saved doc."""
    audit_doc = {
        "user_id":             user["_id"],
        "contract_name":       req.contract_name,
        "chain":               req.chain,
        "contract_code_hash":  hash(req.contract_code),
        "risk_level":          result.get("risk_level", "unknown"),
        "risk_score":          result.get("risk_score", 0),
        "total_findings":      result.get("total_findings", 0),
        "raw_findings_count":  result.get("raw_findings_count", 0),
        "critical_count":      result.get("critical_count", 0),
        "high_count":          result.get("high_count", 0),
        "medium_count":        result.get("medium_count", 0),
        "low_count":           result.get("low_count", 0),
        "info_count":          result.get("info_count", 0),
        "findings":            result.get("findings", []),
        "summary":             result.get("summary", ""),
        "agents_used":         result.get("agents_used", []),
        "scan_duration_ms":    result.get("scan_duration_ms", 0),
        "pdf_base64":          result.get("pdf_base64", ""),
        "pdf_available":       result.get("pdf_available", False),
        "plan_used":           plan_used,
        "has_fix_suggestions": result.get("has_fix_suggestions", False),
        "deployment_verdict":  result.get("deployment_verdict", ""),
        "thinking_chain":      result.get("thinking_chain"),  # Deep audit only
        "is_deep_audit":       plan_used == "deep_audit",
        "version":             "3.0",
        "created_at":          datetime.utcnow()
    }
    insert_result = await db.audits.insert_one(audit_doc)
    audit_doc["_id"] = insert_result.inserted_id
    return audit_doc


# ── REGULAR AUDIT ──────────────────────────────────────────────────────────────
@router.post("/scan")
async def scan_contract(
    req: AuditRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Run audit based on user's plan.
    free → Groq + Gemini
    pro → Groq + Claude Haiku
    enterprise → Groq + Claude Sonnet
    """
    db = get_db()
    plan = current_user.get("plan", "free")
    audits_left = current_user.get("free_audits_remaining", 0)

    # Quota check
    if audits_left <= 0 and plan != "enterprise":
        raise HTTPException(402, {
            "error": "Audit limit reached",
            "message": f"Your {plan} plan limit is reached. Upgrade to continue.",
            "upgrade_url": "/pricing"
        })

    code = validate_contract(req.contract_code)

    try:
        result = await run_audit_pipeline(
            contract_code=code,
            contract_name=req.contract_name,
            plan=plan
        )
    except Exception as e:
        print(f"❌ Pipeline error: {e}")
        raise HTTPException(500, f"Audit pipeline error: {str(e)}")

    audit_doc = await save_audit(db, current_user, req, result, plan)

    # Deduct quota
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$inc": {"free_audits_remaining": -1}}
    )

    response = serialize_audit(audit_doc.copy())
    response["pdf_available"] = result.get("pdf_available", False)
    response["has_fix_suggestions"] = result.get("has_fix_suggestions", False)
    response["deployment_verdict"] = result.get("deployment_verdict", "")
    return response


# ── DEEP AUDIT: Create Payment Order ──────────────────────────────────────────
@router.post("/deep/create-order")
async def create_deep_audit_order(
    req: DeepAuditOrderRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Step 1 of Deep Audit flow.
    Creates a Razorpay order for $20 (₹1650).
    Returns order_id for frontend to open Razorpay checkout.
    """
    validate_contract(req.contract_code)

    client = get_razorpay_client()
    if not client:
        raise HTTPException(500, "Payment gateway not configured. Contact support.")

    # ₹1650 = ~$20 USD (in paise = 165000)
    DEEP_AUDIT_AMOUNT_PAISE = 165000

    try:
        order = client.order.create({
            "amount":   DEEP_AUDIT_AMOUNT_PAISE,
            "currency": "INR",
            "notes": {
                "user_id":       str(current_user["_id"]),
                "audit_type":    "deep_audit",
                "contract_name": req.contract_name,
                "email":         current_user.get("email", "")
            }
        })

        return {
            "order_id":      order["id"],
            "amount":        DEEP_AUDIT_AMOUNT_PAISE,
            "amount_display": "₹1,650 (~$20 USD)",
            "currency":      "INR",
            "key_id":        settings.RAZORPAY_KEY_ID,
            "audit_type":    "deep_audit",
            "description":   "AuditSmart Deep Audit — Claude Opus + Extended Thinking",
            "features": [
                "Claude Opus — most powerful AI model",
                "Extended Thinking — see AI reasoning chain",
                "Full exploit scenario for every critical/high finding",
                "Production-ready patched code snippets",
                "Deployment verdict: SAFE / CAUTION / DO NOT DEPLOY",
                "Priority processing"
            ]
        }
    except Exception as e:
        print(f"❌ Razorpay order error: {e}")
        raise HTTPException(500, f"Payment error: {str(e)}")


# ── DEEP AUDIT: Verify Payment + Run Audit ────────────────────────────────────
@router.post("/deep/verify-and-run")
async def verify_deep_audit_and_run(
    req: DeepAuditVerifyRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Step 2 of Deep Audit flow.
    1. Verify Razorpay payment signature
    2. If valid → run Claude Opus audit
    3. Save result + return full report
    """
    # Verify payment signature
    body = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
    expected_sig = hmac.HMAC(
        settings.RAZORPAY_KEY_SECRET.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()

    if expected_sig != req.razorpay_signature:
        raise HTTPException(400, "Invalid payment signature. Payment verification failed.")

    code = validate_contract(req.contract_code)

    db = get_db()

    # Save payment record first
    await db.payments.insert_one({
        "user_id":              current_user["_id"],
        "audit_type":           "deep_audit",
        "razorpay_order_id":    req.razorpay_order_id,
        "razorpay_payment_id":  req.razorpay_payment_id,
        "amount":               165000,
        "currency":             "INR",
        "status":               "verified",
        "created_at":           datetime.utcnow()
    })

    print(f"💰 Deep Audit payment verified: {req.razorpay_payment_id}")
    print(f"🚀 Starting Claude Opus audit for: {req.contract_name}")

    # Run Claude Opus audit
    try:
        result = await run_audit_pipeline(
            contract_code=code,
            contract_name=req.contract_name,
            plan="deep_audit"
        )
    except Exception as e:
        print(f"❌ Deep Audit pipeline error: {e}")
        raise HTTPException(500, f"Audit error: {str(e)}")

    # Save audit with payment reference
    audit_doc = await save_audit(db, current_user, req, result, "deep_audit")

    # Link payment to audit
    await db.payments.update_one(
        {"razorpay_payment_id": req.razorpay_payment_id},
        {"$set": {"audit_id": str(audit_doc["_id"])}}
    )

    # Return full result including thinking chain
    response = serialize_audit_full(audit_doc.copy())
    response["pdf_available"] = result.get("pdf_available", False)
    response["has_fix_suggestions"] = result.get("has_fix_suggestions", False)
    response["deployment_verdict"] = result.get("deployment_verdict", "")
    response["is_deep_audit"] = True
    response["thinking_chain"] = result.get("thinking_chain")  # Show to user
    return response


# ── HISTORY ────────────────────────────────────────────────────────────────────
@router.get("/history")
async def get_history(
    limit: int = 10,
    current_user: dict = Depends(get_current_user)
):
    db = get_db()
    cursor = db.audits.find(
        {"user_id": current_user["_id"]},
        {"pdf_base64": 0, "thinking_chain": 0}
    ).sort("created_at", -1).limit(limit)

    audits = await cursor.to_list(limit)
    return {"audits": [serialize_audit(a) for a in audits]}


# ── REPORT ─────────────────────────────────────────────────────────────────────
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

    audit = await db.audits.find_one(
        {"_id": oid, "user_id": current_user["_id"]},
        {"pdf_base64": 0}
    )
    if not audit:
        raise HTTPException(404, "Audit not found")

    return serialize_audit_full(audit)


# ── PDF DOWNLOAD ───────────────────────────────────────────────────────────────
@router.get("/report/{audit_id}/pdf")
async def download_pdf(
    audit_id: str,
    current_user: dict = Depends(get_current_user)
):
    db = get_db()
    try:
        oid = ObjectId(audit_id)
    except Exception:
        raise HTTPException(400, "Invalid audit ID")

    audit = await db.audits.find_one(
        {"_id": oid, "user_id": current_user["_id"]},
        {"pdf_base64": 1, "pdf_available": 1, "contract_name": 1, "is_deep_audit": 1}
    )
    if not audit:
        raise HTTPException(404, "Audit not found")

    if not audit.get("pdf_available") or not audit.get("pdf_base64"):
        raise HTTPException(404, "PDF not available. Re-run the audit to generate a PDF.")

    try:
        pdf_bytes = base64.b64decode(audit["pdf_base64"])
    except Exception:
        raise HTTPException(500, "Failed to decode PDF data")

    prefix = "DeepAudit" if audit.get("is_deep_audit") else "AuditSmart"
    contract_name = audit.get("contract_name", "Contract")
    filename = f"{prefix}_Report_{contract_name}_{audit_id[:8]}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        }
    )
