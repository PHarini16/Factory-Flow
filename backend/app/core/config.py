"""Application configuration, read from environment variables (.env supported)."""
from functools import lru_cache
from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "FactoryFlow"
    database_url: str = "sqlite:///./factoryflow.db"
    secret_key: str = "CHANGE-ME-in-production-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    demo_mode: bool = True  # enables /demo/* reset endpoints. Set False in production.
    auto_migrate: bool = True  # run `alembic upgrade head` + seed on startup
    login_rate_limit: int = 10  # attempts per minute per (ip, username)

    # Factory (seller) details - dummy data
    factory_name: str = "Sri Murugan Snacks Pvt Ltd"
    factory_gstin: str = "33AAAAA0000A1Z5"
    factory_address: str = "12 Industrial Estate, Coimbatore, Tamil Nadu 641001"
    factory_state: str = "Tamil Nadu"
    factory_state_code: str = "33"

    default_variance_tolerance_pct: Decimal = Decimal("3")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
