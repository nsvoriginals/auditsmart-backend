from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from datetime import datetime
from app.database import get_db
from app.utils.auth import hash_password, verify_password, create_token
from app.config import settings

router = APIRouter()


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def user_response(user: dict, token: str) -> dict:
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user["_id"]),
            "name": user.get("name", ""),
            "email": user.get("email", ""),
            "plan": user.get("plan", "free"),
            "free_audits_remaining": user.get(
                "free_audits_remaining", settings.FREE_AUDITS_LIMIT)
        }
    }


@router.post("/register", status_code=201)
async def register(req: RegisterRequest):
    db = get_db()

    if len(req.password) < 8:
        raise HTTPException(400,
                            "Password must be at least 8 characters")

    if len(req.name.strip()) < 2:
        raise HTTPException(400, "Name must be at least 2 characters")

    existing = await db.users.find_one(
        {"email": req.email.lower()})
    if existing:
        raise HTTPException(409, "Email already registered")

    user_doc = {
        "name": req.name.strip(),
        "email": req.email.lower(),
        "password": hash_password(req.password),
        "plan": "free",
        "free_audits_remaining": settings.FREE_AUDITS_LIMIT,
        "total_audits": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    result = await db.users.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id

    token = create_token(str(result.inserted_id), req.email.lower())
    return user_response(user_doc, token)


@router.post("/login")
async def login(req: LoginRequest):
    db = get_db()

    user = await db.users.find_one({"email": req.email.lower()})
    if not user or not verify_password(req.password, user["password"]):
        raise HTTPException(401, "Invalid email or password")

    token = create_token(str(user["_id"]), user["email"])
    return user_response(user, token)
