from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # MongoDB
    MONGODB_URL: str = "mongodb://localhost:27017"
    DB_NAME: str = "auditsmart"

    # JWT
    JWT_SECRET: str = "change-this-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 168  # 7 days

    # Groq
    GROQ_API_KEY: str = ""

    # Gemini
    GEMINI_API_KEY: str = ""

    # Razorpay
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""

    # App
    FRONTEND_URL: str = "https://auditsmart.org"
    FREE_AUDITS_LIMIT: int = 3

    # v2.0 — PDF & Features
    PDF_ENABLED: bool = True  # Free tier gets PDF too
    MAX_CONTRACT_SIZE: int = 50000  # 50KB max contract
    RATE_LIMIT_PER_MINUTE: int = 5
    
    # v2.0 — Enhanced Agents
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_MAX_TOKENS: int = 4096
    GROQ_TEMPERATURE: float = 0.1
    GEMINI_MODEL: str = "gemini-1.5-pro"
    GEMINI_MAX_TOKENS: int = 8192
    AGENT_TIMEOUT_SECONDS: int = 120

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

# --- STARTUP DIAGNOSTICS ---
print("=" * 50)
print("AuditSmart v2.0 Config Loaded:")
print(f"  MONGODB_URL: {'SET (' + settings.MONGODB_URL[:20] + '...)' if settings.MONGODB_URL else 'MISSING!'}")
print(f"  GROQ_API_KEY: {'SET (' + settings.GROQ_API_KEY[:8] + '...)' if settings.GROQ_API_KEY else 'MISSING!'}")
print(f"  GEMINI_API_KEY: {'SET (' + settings.GEMINI_API_KEY[:8] + '...)' if settings.GEMINI_API_KEY else 'MISSING!'}")
print(f"  RAZORPAY_KEY_ID: {'SET' if settings.RAZORPAY_KEY_ID else 'MISSING!'}")
print(f"  FRONTEND_URL: {settings.FRONTEND_URL}")
print(f"  FREE_AUDITS_LIMIT: {settings.FREE_AUDITS_LIMIT}")
print(f"  PDF_ENABLED: {settings.PDF_ENABLED}")
print(f"  GROQ_MODEL: {settings.GROQ_MODEL}")
print("=" * 50)
