from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "lead-finder-backend"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    mongodb_uri: str = "mongodb://mongodb:27017"
    mongodb_db_name: str = "lead_finder"

    api_title: str = "Lead Finder API"
    api_version: str = "v1"
    api_description: str = "Lead Discovery and Outreach Platform"

    log_level: str = "INFO"
    log_dir: str = "logs"
    log_file: str = "app.log"
    log_max_bytes: int = Field(default=10_485_760, ge=1)
    log_backup_count: int = Field(default=5, ge=1)

    request_id_header: str = "X-Request-ID"
    cors_origins: str = "*"

    product_hunt_api_url: str = "https://api.producthunt.com/v2/api/graphql"
    product_hunt_user_agent: str = "LeadFinder/1.0 (lead-finder-backend)"
    product_hunt_timeout: float = Field(default=30.0, ge=1.0)
    product_hunt_max_companies: int = Field(default=50, ge=1, le=200)
    product_hunt_api_token: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
