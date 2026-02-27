from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./quotes.db"
    SECRET_KEY: str = "dev-secret-key"
    COMPANY_NAME: str = "CreateStage Fabrication"
    COMPANY_EMAIL: str = "info@createstage.com"
    COMPANY_PHONE: str = ""
    LABOR_RATE_DEFAULT: float = 125.00
    MARKUP_DEFAULT: float = 1.35
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Auth — v2
    JWT_SECRET: str = ""  # REQUIRED in production — fail loudly if missing at auth time
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 30

    # Cloudflare R2 — optional now, required in Session 3
    CLOUDFLARE_R2_ACCOUNT_ID: str = ""
    CLOUDFLARE_R2_ACCESS_KEY_ID: str = ""
    CLOUDFLARE_R2_SECRET_ACCESS_KEY: str = ""
    CLOUDFLARE_R2_BUCKET: str = "createstage-quotes"

    class Config:
        env_file = ".env"


settings = Settings()
