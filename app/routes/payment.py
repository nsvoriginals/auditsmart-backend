from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from app.utils.auth import get_current_user
from app.database import get_db
from app.config import settings
from datetime import datetime
import hmac
import hashlib

router = APIRouter()

# ─── RAZORPAY ───────────────────────────────────────────
class RazorpayOrderRequest(BaseModel):
    plan: str  # "pro" | "enterprise"

@router.post("/razorpay/create-order")
async def create_razorpay_order(
    req: RazorpayOrderRequest,
    current_user: dict = Depends(get_current_user)
):
    if not settings.RAZORPAY_KEY_ID:
        raise HTTPException(503, "Razorpay not configured")

    try:
        import razorpay
        client = razorpay.Client(auth=(
            settings.RAZORPAY_KEY_ID,
            settings.RAZORPAY_KEY_SECRET
        ))

        plan_prices = {"pro": 4099, "enterprise": 49999}  # paise (INR)
        amount = plan_prices.get(req.plan, 4099)

        order = client.order.create({
            "amount": amount,
            "currency": "INR",
            "notes": {
                "user_id": str(current_user["_id"]),
                "plan": req.plan
            }
        })

        return {
            "order_id": order["id"],
            "amount": amount,
            "currency": "INR",
            "key": settings.RAZORPAY_KEY_ID
        }
    except Exception as e:
        raise HTTPException(500, f"Razorpay error: {str(e)}")


@router.post("/razorpay/verify")
async def verify_razorpay(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    body = await request.json()

    order_id   = body.get("razorpay_order_id", "")
    payment_id = body.get("razorpay_payment_id", "")
    signature  = body.get("razorpay_signature", "")
    plan       = body.get("plan", "pro")

    # Verify Razorpay signature
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256
    ).hexdigest()

    if expected != signature:
        raise HTTPException(400, "Invalid payment signature")

    await _activate_plan(current_user["_id"], plan, payment_id, "razorpay")
    return {"status": "success", "plan": plan}


# ─── Internal helper ─────────────────────────────────────
async def _activate_plan(user_id, plan: str, payment_id: str, gateway: str):
    db = get_db()
    plan_limits = {"pro": 50, "enterprise": 99999}
    await db.users.update_one(
        {"_id": user_id},
        {"$set": {
            "plan": plan,
            "free_audits_remaining": plan_limits.get(plan, 50),
            "updated_at": datetime.utcnow()
        }}
    )
    await db.payments.insert_one({
        "user_id": user_id,
        "plan": plan,
        "payment_id": payment_id,
        "gateway": gateway,
        "created_at": datetime.utcnow()
    })
