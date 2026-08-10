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
    log_retention_days: int = Field(default=7, ge=1, le=365)

    request_id_header: str = "X-Request-ID"
    cors_origins: str = "*"

    product_hunt_api_url: str = "https://api.producthunt.com/v2/api/graphql"
    product_hunt_user_agent: str = "LeadFinder/1.0 (lead-finder-backend)"
    product_hunt_timeout: float = Field(default=30.0, ge=1.0)
    product_hunt_max_companies: int = Field(default=50, ge=1, le=200)
    product_hunt_api_token: str | None = None
    # Hard cap per product website resolution (Cloudflare must not block the pipeline).
    product_hunt_website_resolve_timeout: float = Field(default=5.0, ge=0.5, le=30.0)

    hackernews_api_url: str = "https://hn.algolia.com/api/v1/search_by_date"
    hackernews_user_agent: str = "LeadFinder/1.0 (lead-finder-backend)"
    hackernews_timeout: float = Field(default=30.0, ge=1.0)
    hackernews_max_companies: int = Field(default=50, ge=1, le=200)

    ycombinator_api_base: str = "https://yc-oss.github.io/api"
    ycombinator_user_agent: str = "LeadFinder/1.0 (lead-finder-backend)"
    ycombinator_timeout: float = Field(default=45.0, ge=1.0)
    ycombinator_max_companies: int = Field(default=50, ge=1, le=200)

    # When true, India-linked startups are sorted first within each collector batch.
    prefer_india_startups: bool = True

    github_api_base: str = "https://api.github.com"
    github_user_agent: str = "LeadFinder/1.0 (lead-finder-backend)"
    github_timeout: float = Field(default=30.0, ge=1.0)
    github_max_companies: int = Field(default=50, ge=1, le=200)
    github_token: str | None = None
    github_min_stars: int = Field(default=5, ge=0)
    github_lookback_days: int = Field(default=45, ge=1, le=365)
    github_india_query: str = "india OR bangalore OR bengaluru OR mumbai OR hyderabad OR chennai OR pune"

    rss_user_agent: str = "LeadFinder/1.0 (lead-finder-backend)"
    rss_timeout: float = Field(default=30.0, ge=1.0)
    rss_max_companies: int = Field(default=40, ge=1, le=200)
    # Comma-separated feed URLs (India-leaning startup media first).
    rss_feed_urls: str = (
        "https://inc42.com/feed/,"
        "https://yourstory.com/feed/,"
        "https://techcrunch.com/tag/india/feed/"
    )

    google_news_max_companies: int = Field(default=40, ge=1, le=200)
    google_news_feed_urls: str = (
        "https://news.google.com/rss/search?q=Indian+startup+launch&hl=en-IN&gl=IN&ceid=IN:en,"
        "https://news.google.com/rss/search?q=startup+raises+funding+India&hl=en-IN&gl=IN&ceid=IN:en,"
        "https://news.google.com/rss/search?q=new+SaaS+startup+India&hl=en-IN&gl=IN&ceid=IN:en"
    )

    reddit_user_agent: str = "LeadFinder/1.0 by lead-finder-backend"
    reddit_timeout: float = Field(default=30.0, ge=1.0)
    reddit_max_companies: int = Field(default=40, ge=1, le=200)
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_subreddits: str = (
        "indianstartups,developersIndia,startups,SideProject,indiehackers,Entrepreneur"
    )

    qualification_passing_score: int = Field(default=60, ge=0, le=100)
    qualification_enabled_rules: str = (
        "website_exists,company_name_exists,description_exists,not_localhost,"
        "not_github_io,not_vercel_app,not_netlify_app,not_notion_site,"
        "description_length,has_topic"
    )
    # Minimum outbound lead score for email queue eligibility (Step 37).
    min_lead_score: int = Field(default=60, ge=0, le=100)

    crawler_timeout: float = Field(default=20.0, ge=1.0)
    crawler_max_redirects: int = Field(default=5, ge=0)
    crawler_max_html_size: int = Field(default=2_000_000, ge=1)
    crawler_user_agent: str = "LeadFinderBot/1.0 (+https://lead-finder.local)"

    technology_minimum_confidence: int = Field(default=50, ge=0, le=100)
    technology_enabled_technologies: str = "*"

    mobile_detection_enabled: bool = True
    mobile_detection_minimum_confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    enabled_sources: str = (
        "producthunt,hackernews,ycombinator,github,rss,googlenews,reddit"
    )
    collection_timeout: float = Field(default=300.0, ge=1.0)
    max_collectors: int = Field(default=10, ge=1, le=50)

    scheduler_enabled: bool = True
    scheduler_timezone: str = "Asia/Kolkata"
    scheduler_hour: int = Field(default=9, ge=0, le=23)
    scheduler_minute: int = Field(default=0, ge=0, le=59)
    collect_cron: str = "0 * * * *"
    validation_cron: str = "30 * * * *"
    cleanup_cron: str = "0 2 * * *"
    max_job_runtime: int = Field(default=600, ge=1)

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_timeout: float = Field(default=120.0, ge=1.0)
    ollama_temperature: float = Field(default=0.45, ge=0.0, le=2.0)
    ollama_max_tokens: int = Field(default=512, ge=1, le=4096)

    # SMTP delivery (Step 40). Keep disabled until production credentials are set.
    smtp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = ""
    smtp_from_name: str = ""
    smtp_use_tls: bool = True
    smtp_reply_to: str | None = None
    smtp_timeout_seconds: float = Field(default=30.0, ge=1.0)
    # Legacy aliases — prefer SMTP_* above. dry_run=True skips real SMTP in tests/local.
    smtp_tls: bool = True
    from_email: str = ""
    dry_run: bool = True

    @property
    def effective_smtp_from_email(self) -> str:
        return (self.smtp_from_email or self.from_email or "").strip()

    @property
    def effective_smtp_use_tls(self) -> bool:
        # SMTP_USE_TLS is canonical; SMTP_TLS remains a legacy alias.
        return bool(self.smtp_use_tls and self.smtp_tls)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
