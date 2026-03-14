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
    description="AI-powered smart contract security auditing",
    version="1.0.0",
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
    return {"status": "AuditSmart API running", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "ok"}
