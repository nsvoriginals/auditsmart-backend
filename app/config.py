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

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
