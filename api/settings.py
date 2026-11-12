"""Application settings loaded from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = Field(
        default="postgresql+psycopg://localhost/job_platform",
        validation_alias="DATABASE_URL",
    )
    ollama_base_url: str = "http://localhost:11434/v1"
    debug: bool = False
    mapbox_access_token: str | None = Field(default=None, validation_alias="MAPBOX_ACCESS_TOKEN")
    google_maps_api_key: str | None = Field(default=None, validation_alias="GOOGLE_MAPS_API_KEY")
    geo_routing_provider: str = Field(default="estimate", validation_alias="GEO_ROUTING_PROVIDER")
    geo_geocode_daily_cap: int = Field(default=50, validation_alias="GEO_GEOCODE_DAILY_CAP")
    geo_geocode_monthly_cap: int = Field(default=100_000, validation_alias="GEO_GEOCODE_MONTHLY_CAP")
    geo_matrix_monthly_cap: int = Field(default=100_000, validation_alias="GEO_MATRIX_MONTHLY_CAP")
    stripe_secret_key: str | None = Field(default=None, validation_alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(default=None, validation_alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_id_monthly_1500: str | None = Field(
        default=None, validation_alias="STRIPE_PRICE_ID_MONTHLY_1500"
    )
    app_base_url: str = Field(default="http://localhost:5173", validation_alias="APP_BASE_URL")
    app_mount_path: str = Field(default="", validation_alias="APP_MOUNT_PATH")


settings = Settings()
