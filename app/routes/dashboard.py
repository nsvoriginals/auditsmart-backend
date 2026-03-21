from fastapi import APIRouter, Depends
from app.utils.auth import get_current_user
from app.database import get_db

router = APIRouter()


@router.get("/stats")
async def get_stats(
    current_user: dict = Depends(get_current_user)
):
    db = get_db()
    user_id = current_user["_id"]

    total_audits = await db.audits.count_documents(
        {"user_id": user_id})

    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": None,
            "total_findings": {"$sum": "$total_findings"},
            "critical_findings": {"$sum": "$critical_count"},
            "high_findings": {"$sum": "$high_count"},
            "medium_findings": {"$sum": "$medium_count"},
            "low_findings": {"$sum": "$low_count"},
            "total_vulnerabilities": {
                "$sum": {
                    "$add": [
                        "$critical_count",
                        "$high_count",
                        "$medium_count",
                        "$low_count"
                    ]
                }
            },
            # v2.0 — track raw vs deduped counts
            "total_raw_findings": {"$sum": {"$ifNull": ["$raw_findings_count", "$total_findings"]}},
            "avg_risk_score": {"$avg": "$risk_score"},
            "avg_scan_duration": {"$avg": "$scan_duration_ms"},
        }}
    ]

    result = await db.audits.aggregate(pipeline).to_list(1)

    stats = result[0] if result else {
        "total_findings": 0,
        "critical_findings": 0,
        "high_findings": 0,
        "medium_findings": 0,
        "low_findings": 0,
        "total_vulnerabilities": 0,
        "total_raw_findings": 0,
        "avg_risk_score": 0,
        "avg_scan_duration": 0,
    }

    return {
        "total_audits": total_audits,
        "total_findings": stats.get("total_findings", 0),
        "critical_findings": stats.get("critical_findings", 0),
        "high_findings": stats.get("high_findings", 0),
        "medium_findings": stats.get("medium_findings", 0),
        "low_findings": stats.get("low_findings", 0),
        "total_vulnerabilities": stats.get("total_vulnerabilities", 0),
        "total_raw_findings": stats.get("total_raw_findings", 0),
        "avg_risk_score": round(stats.get("avg_risk_score", 0), 1),
        "avg_scan_duration_ms": round(stats.get("avg_scan_duration", 0)),
        "free_audits_remaining": current_user.get("free_audits_remaining", 0),
        "plan": current_user.get("plan", "free"),
        "version": "2.0"
    }
