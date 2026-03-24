from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── MongoDB ────────────────────────────────────────────────────────────────
    MONGODB_URL: str = "mongodb://localhost:27017"
    DB_NAME: str = "auditsmart"

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET: str = "change-this-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 168

    # ── AI APIs ───────────────────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""           # Free plan uses this
    ANTHROPIC_API_KEY: str = ""        # Pro, Enterprise, Deep Audit

    # ── Groq Settings ─────────────────────────────────────────────────────────
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_MAX_TOKENS: int = 4096
    GROQ_TEMPERATURE: float = 0.1
    AGENT_TIMEOUT_SECONDS: int = 120

    # ── Claude Model Map ──────────────────────────────────────────────────────
    # free       → Groq + Gemini              (~$0.05/audit)
    # pro        → Groq + claude-haiku        (~$0.12/audit)
    # enterprise → Groq + claude-sonnet       (~$0.49/audit)
    # deep_audit → Full claude-opus-4-5 only  (~$1.78/audit, charges $20)
    CLAUDE_HAIKU_MODEL: str = "claude-haiku-4-5-20251001"
    CLAUDE_SONNET_MODEL: str = "claude-sonnet-4-6"
    CLAUDE_OPUS_MODEL: str = "claude-opus-4-5"
    CLAUDE_TIMEOUT_SECONDS: int = 120

    # ── Payments ──────────────────────────────────────────────────────────────
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""

    # ── Plan Limits ───────────────────────────────────────────────────────────
    FREE_AUDITS_LIMIT: int = 3
    PRO_AUDITS_LIMIT: int = 20
    ENTERPRISE_AUDITS_LIMIT: int = 50

    # ── Deep Audit Pricing ────────────────────────────────────────────────────
    DEEP_AUDIT_PRICE_INR: int = 1650   # ~$20 USD in INR paise = 165000 paise
    DEEP_AUDIT_PRICE_USD: float = 20.0

    # ── App ───────────────────────────────────────────────────────────────────
    FRONTEND_URL: str = "https://auditsmart.org"
    MAX_CONTRACT_SIZE: int = 50000
    RATE_LIMIT_PER_MINUTE: int = 5
    PDF_ENABLED: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

print("=" * 55)
print("AuditSmart v3.0 Config:")
print(f"  GROQ:        {'✅' if settings.GROQ_API_KEY else '❌ MISSING'}")
print(f"  GEMINI:      {'✅' if settings.GEMINI_API_KEY else '❌ MISSING'} (Free plan)")
print(f"  ANTHROPIC:   {'✅' if settings.ANTHROPIC_API_KEY else '❌ MISSING'} (Pro/Ent/Deep)")
print(f"  RAZORPAY:    {'✅' if settings.RAZORPAY_KEY_ID else '⚠️  Not set'}")
print(f"  Plans: Free(3) | Pro(20) | Ent(50) | DeepAudit($20/ea)")
print("=" * 55)
