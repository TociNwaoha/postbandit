from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/clipbandit"
    database_sync_url: str = "postgresql://postgres:postgres@localhost:5432/clipbandit"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "clipbandit"

    # Redis + Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    api_rate_limit_redis_db: int = 3
    auth_rate_limit_redis_db: int = 2

    # Auth
    nextauth_secret: str = "changeme"
    nextauth_url: str = "http://localhost:3001"
    admin_email: str = "admin@clipbandit.com"
    admin_password: str = "changeme123"
    google_client_id: str = "placeholder"
    google_client_secret: str = "placeholder"

    # JWT
    jwt_secret_key: str = "changeme-jwt-secret-key-32-chars-min"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 120

    # Public URLs
    backend_public_url: str = "http://localhost:8000"
    frontend_public_url: str = "http://localhost:3001"
    frontend_url: str = "http://localhost:3001"

    # Stripe Billing
    stripe_billing_enabled: bool = False
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_creator_price_id: str = ""
    stripe_pro_price_id: str = ""
    stripe_elite_price_id: str = ""

    # Backblaze B2 (S3-compatible API)
    b2_key_id: str = "placeholder"
    b2_application_key: str = "placeholder"
    b2_bucket_name: str = "placeholder"
    b2_endpoint_url: str = "https://placeholder.backblazeb2.com"
    b2_region: str = "placeholder"

    # Anthropic (legacy)
    anthropic_api_key: str = "placeholder"

    # DeepSeek
    deepseek_api_key: str = "placeholder"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_timeout_sec: int = 30
    bandit_lm_api_key: str = "placeholder"
    google_ai_api_key: str = "placeholder"
    carousel_claude_model: str = "claude-sonnet-4-6"
    carousel_render_timeout_seconds: int = 240
    carousel_reference_image_max_mb: int = 10

    # Social distribution
    social_token_encryption_key: str = "placeholder"
    social_oauth_state_ttl_minutes: int = 15

    youtube_client_id: str = "placeholder"
    youtube_client_secret: str = "placeholder"

    facebook_app_id: str = "placeholder"
    facebook_app_secret: str = "placeholder"
    instagram_app_id: str = "placeholder"
    instagram_app_secret: str = "placeholder"
    threads_app_id: str = "placeholder"
    threads_app_secret: str = "placeholder"

    meta_app_id: str = "placeholder"
    meta_app_secret: str = "placeholder"
    meta_graph_api_version: str = "v21.0"
    threads_graph_api_version: str = "v1.0"

    tiktok_client_key: str = "placeholder"
    tiktok_client_secret: str = "placeholder"
    tiktok_publish_poll_interval_seconds: int = 5
    tiktok_publish_poll_timeout_seconds: int = 720

    x_client_id: str = "placeholder"
    x_client_secret: str = "placeholder"

    linkedin_client_id: str = "placeholder"
    linkedin_client_secret: str = "placeholder"

    # App
    environment: str = "development"
    log_level: str = "INFO"
    sentry_dsn: str = ""
    backup_dir: str = "/opt/clipbandit/backups"
    backup_retention_days: int = 14
    max_upload_size_mb: int = 5000
    max_concurrent_jobs: int = 2
    youtube_import_max_playlist_items: int = 50
    youtube_import_concurrency: int = 3
    ytdlp_timeout_seconds: int = 60
    enable_youtube_api_metadata: bool = False
    youtube_api_key: str = "placeholder"
    youtube_local_helper_ttl_minutes: int = 15
    youtube_import_admission_mode: str = "warn"
    youtube_import_min_free_disk_gb: int = 20
    youtube_import_max_ingest_queue_depth: int = 100
    youtube_import_max_active_per_user: int = 3
    youtube_import_max_active_global: int = 12
    youtube_import_rate_limit_per_hour: int = 25
    youtube_helper_session_rate_limit_per_hour: int = 20
    youtube_import_admission_storage_path: str = "/tmp/clipbandit-storage"
    workspace_lease_ttl_seconds: int = 3600
    workspace_cleanup_enabled: bool = True
    workspace_cleanup_dry_run: bool = True
    workspace_cleanup_retention_hours: int = 24
    workspace_cleanup_orphan_grace_minutes: int = 45
    failed_import_cleanup_enabled: bool = True
    failed_import_cleanup_retention_hours: int = 24
    failed_import_cleanup_dry_run: bool = False
    stale_queued_upload_cleanup_enabled: bool = True
    stale_queued_upload_cleanup_retention_hours: int = 2
    stale_queued_upload_cleanup_dry_run: bool = False
    raw_source_retention_enabled: bool = True
    raw_source_retention_days: int = 45
    editor_max_asset_upload_bytes: int = 25 * 1024 * 1024
    editor_preview_proxy_timeout_seconds: int = 1800

    # Transcription
    whisper_model_size: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_download_root: str = "/tmp/whisper-models"
    whisper_num_workers: int = 2
    whisper_beam_size: int = 1
    whisper_best_of: int = 1
    whisper_condition_on_previous_text: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
