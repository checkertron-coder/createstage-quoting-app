from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./quotes.db"
    SECRET_KEY: str = "dev-secret-key"
    COMPANY_NAME: str = "CreateStage Fabrication"
    COMPANY_EMAIL: str = "info@createstage.com"
    COMPANY_PHONE: str = ""
    LABOR_RATE_DEFAULT: float = 85.00
    MARKUP_DEFAULT: float = 1.35

    class Config:
        env_file = ".env"

settings = Settings()
