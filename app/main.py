from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.database import connect_db, disconnect_db
from app.routes import auth, audit, dashboard, payment
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await disconnect_db()


app = FastAPI(
    title="AuditSmart API v3.0",
    description="AI Smart Contract Security Platform — Powered by Claude (Anthropic)",
    version="3.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000", "http://localhost:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router,      prefix="/auth",      tags=["Auth"])
app.include_router(audit.router,     prefix="/audit",     tags=["Audit"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(payment.router,   prefix="/payment",   tags=["Payment"])


@app.get("/")
async def root():
    return {
        "app":     "AuditSmart v3.0",
        "status":  "running",
        "powered_by": "Claude (Anthropic) + Groq + Gemini",
        "plans":   ["free", "pro", "enterprise", "deep_audit"],
        "docs":    "/docs"
    }


@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0.0"}
