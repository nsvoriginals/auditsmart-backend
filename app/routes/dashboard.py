from fastapi import APIRouter, Depends
from app.utils.auth import get_current_user
from app.database import get_db
from datetime import datetime

router = APIRouter()

@router.get("/stats")
async def get_stats(current_user: dict = Depends(get_current_user)):
    db = get_db()
    user_id = current_user["_id"]

    # Aggregate audit stats for this user
    total_audits = await db.audits.count_documents({"user_id": user_id})

    # Critical findings count
    crit_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": None, "total": {"$sum": "$critical_count"}}}
    ]
    crit_result = await db.audits.aggregate(crit_pipeline).to_list(1)
    critical_findings = crit_result[0]["total"] if crit_result else 0

    # Total vulns
    vuln_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": None, "total": {"$sum": "$total_findings"}}}
    ]
    vuln_result = await db.audits.aggregate(vuln_pipeline).to_list(1)
    total_vulnerabilities = vuln_result[0]["total"] if vuln_result else 0

    return {
        "total_audits": total_audits,
        "critical_findings": critical_findings,
        "total_vulnerabilities": total_vulnerabilities,
        "free_audits_remaining": current_user.get("free_audits_remaining", 0),
        "plan": current_user.get("plan", "free")
    }
