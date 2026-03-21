from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.database import connect_db, disconnect_db
from app.routes import auth, audit, dashboard, payment


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await disconnect_db()


app = FastAPI(
    title="AuditSmart API",
    description=(
        "AI-powered smart contract security auditing platform. "
        "Multi-agent pipeline with 8 specialist agents, deduplication engine, "
        "and PDF report generation."
    ),
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,      prefix="/auth",      tags=["Auth"])
app.include_router(audit.router,     prefix="/audit",     tags=["Audit"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(payment.router,   prefix="/payment",   tags=["Payment"])


@app.get("/")
async def root():
    return {
        "status": "AuditSmart API running",
        "version": "2.0.0",
        "features": [
            "8 specialist AI agents",
            "Deduplication engine",
            "False positive filtering",
            "Severity auto-correction",
            "PDF report generation",
            "Backdoor detection (selfdestruct, delegatecall)",
            "Signature verification analysis",
            "ERC20 safety checks"
        ]
    }


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
