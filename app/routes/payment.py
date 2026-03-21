import razorpay
import hashlib
import hmac
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.utils.auth import get_current_user
from app.database import get_db
from app.config import settings
from datetime import datetime

router = APIRouter()


class RazorpayOrderRequest(BaseModel):
    plan: str  # "pro" or "enterprise"


class RazorpayVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan: str


PLAN_PRICES = {
    "pro": 49900,        # INR 499 in paise
    "enterprise": 199900  # INR 1999 in paise
}

PLAN_LIMITS = {
    "pro": 50,
    "enterprise": -1  # unlimited
}

PLAN_FEATURES = {
    "free": {
        "audits": 3,
        "pdf_download": True,  # v2.0 — PDF in free tier
        "agents": 8,
    },
    "pro": {
        "audits": 50,
        "pdf_download": True,
        "agents": 8,
        "priority_queue": True,
    },
    "enterprise": {
        "audits": -1,  # unlimited
        "pdf_download": True,
        "agents": 8,
        "priority_queue": True,
        "api_access": True,
    }
}


def get_razorpay_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        return None
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


@router.post("/razorpay/create-order")
async def create_razorpay_order(
    req: RazorpayOrderRequest,
    current_user: dict = Depends(get_current_user)
):
    if req.plan not in PLAN_PRICES:
        raise HTTPException(400, "Invalid plan. Choose 'pro' or 'enterprise'.")

    client = get_razorpay_client()
    if not client:
        raise HTTPException(500, "Payment gateway not configured")

    try:
        order = client.order.create({
            "amount": PLAN_PRICES[req.plan],
            "currency": "INR",
            "notes": {
                "user_id": str(current_user["_id"]),
                "plan": req.plan,
                "email": current_user.get("email", "")
            }
        })
        return {
            "order_id": order["id"],
            "amount": PLAN_PRICES[req.plan],
            "currency": "INR",
            "key": settings.RAZORPAY_KEY_ID,
            "key_id": settings.RAZORPAY_KEY_ID,
            "plan": req.plan,
            "features": PLAN_FEATURES.get(req.plan, {})
        }
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

    # Verify signature
    body = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()

    if expected != req.razorpay_signature:
        raise HTTPException(400, "Invalid payment signature")

    # Activate plan
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


# v2.0 — Plan info endpoint (no auth needed)
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
