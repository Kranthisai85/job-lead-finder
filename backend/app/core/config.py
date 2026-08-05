from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "lead-finder-backend"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8001

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

    qualification_passing_score: int = Field(default=50, ge=0, le=100)
    qualification_enabled_rules: str = (
        "website_exists,company_name_exists,description_exists,not_localhost,"
        "not_github_io,not_vercel_app,not_netlify_app,not_notion_site,"
        "description_length,has_topic"
    )

    crawler_timeout: float = Field(default=20.0, ge=1.0)
    crawler_max_redirects: int = Field(default=5, ge=0)
    crawler_max_html_size: int = Field(default=2_000_000, ge=1)
    crawler_user_agent: str = "LeadFinderBot/1.0 (+https://lead-finder.local)"

    technology_minimum_confidence: int = Field(default=50, ge=0, le=100)
    technology_enabled_technologies: str = "*"

    mobile_detection_enabled: bool = True
    mobile_detection_minimum_confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    enabled_sources: str = "producthunt"
    collection_timeout: float = Field(default=120.0, ge=1.0)
    max_collectors: int = Field(default=10, ge=1, le=50)

    scheduler_enabled: bool = True
    collect_cron: str = "0 * * * *"
    validation_cron: str = "30 * * * *"
    cleanup_cron: str = "0 2 * * *"
    max_job_runtime: int = Field(default=600, ge=1)

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_timeout: float = Field(default=60.0, ge=1.0)
    ollama_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    ollama_max_tokens: int = Field(default=512, ge=1, le=4096)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
