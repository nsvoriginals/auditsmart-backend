import hashlib
import hmac
import httpx
import base64
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.utils.auth import get_current_user
from app.database import get_db
from app.config import settings
from datetime import datetime

router = APIRouter()

RAZORPAY_API = "https://api.razorpay.com/v1"


class RazorpayOrderRequest(BaseModel):
    plan: str


class RazorpayVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan: str


PLAN_PRICES = {
    "pro": 49900,
    "enterprise": 199900
}

PLAN_LIMITS = {
    "pro": 50,
    "enterprise": -1
}

PLAN_FEATURES = {
    "free": {
        "audits": 3,
        "pdf_download": True,
        "agents": 8,
    },
    "pro": {
        "audits": 50,
        "pdf_download": True,
        "agents": 8,
        "priority_queue": True,
    },
    "enterprise": {
        "audits": -1,
        "pdf_download": True,
        "agents": 8,
        "priority_queue": True,
        "api_access": True,
    }
}


def razorpay_headers() -> dict:
    """Build Basic Auth headers for Razorpay REST API."""
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise HTTPException(500, "Payment gateway not configured")
    creds = f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}"
    encoded = base64.b64encode(creds.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
    }


@router.post("/razorpay/create-order")
async def create_razorpay_order(
    req: RazorpayOrderRequest,
    current_user: dict = Depends(get_current_user)
):
    if req.plan not in PLAN_PRICES:
        raise HTTPException(400, "Invalid plan. Choose 'pro' or 'enterprise'.")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{RAZORPAY_API}/orders",
                headers=razorpay_headers(),
                json={
                    "amount": PLAN_PRICES[req.plan],
                    "currency": "INR",
                    "notes": {
                        "user_id": str(current_user["_id"]),
                        "plan": req.plan,
                        "email": current_user.get("email", "")
                    }
                }
            )

        if resp.status_code != 200:
            print(f"❌ Razorpay error: {resp.text}")
            raise HTTPException(502, f"Payment gateway error: {resp.text}")

        order = resp.json()
        return {
            "order_id": order["id"],
            "amount": PLAN_PRICES[req.plan],
            "currency": "INR",
            "key": settings.RAZORPAY_KEY_ID,
            "key_id": settings.RAZORPAY_KEY_ID,
            "plan": req.plan,
            "features": PLAN_FEATURES.get(req.plan, {})
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Razorpay error: {e}")
        raise HTTPException(500, f"Payment error: {str(e)}")


@router.post("/razorpay/verify")
async def verify_razorpay_payment(
    req: RazorpayVerifyRequest,
    current_user: dict = Depends(get_current_user)
):
    if req.plan not in PLAN_PRICES:
        raise HTTPException(400, "Invalid plan")

    # Verify HMAC-SHA256 signature
    body = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, req.razorpay_signature):
        raise HTTPException(400, "Invalid payment signature")

    # Activate plan in DB
    db = get_db()
    limit = PLAN_LIMITS.get(req.plan, 0)

    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {
            "plan": req.plan,
            "free_audits_remaining": limit,
            "updated_at": datetime.utcnow()
        }}
    )

    # Save payment record
    await db.payments.insert_one({
        "user_id": current_user["_id"],
        "plan": req.plan,
        "razorpay_order_id": req.razorpay_order_id,
        "razorpay_payment_id": req.razorpay_payment_id,
        "amount": PLAN_PRICES.get(req.plan, 0),
        "currency": "INR",
        "status": "verified",
        "created_at": datetime.utcnow()
    })

    return {
        "status": "success",
        "plan": req.plan,
        "features": PLAN_FEATURES.get(req.plan, {})
    }


@router.get("/plans")
async def get_plans():
    """Return available plans and pricing."""
    return {
        "plans": {
            "free": {
                "price": 0,
                "currency": "INR",
                "audits": 3,
                "features": PLAN_FEATURES["free"]
            },
            "pro": {
                "price": 499,
                "currency": "INR",
                "audits": 50,
                "features": PLAN_FEATURES["pro"]
            },
            "enterprise": {
                "price": 1999,
                "currency": "INR",
                "audits": "Unlimited",
                "features": PLAN_FEATURES["enterprise"]
            }
        }
    }