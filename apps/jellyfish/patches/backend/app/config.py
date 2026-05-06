"""应用配置，从环境变量加载。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Jellyfish API"
    debug: bool = False

    api_v1_prefix: str = "/api/v1"

    database_url: str = "sqlite+aiosqlite:///./jellyfish.db"

    cors_origins: list[str] = [
        "http://localhost:7788",
        "http://127.0.0.1:7788",
    ]

    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"

    image_api_provider: str | None = None
    image_api_key: str | None = None
    image_api_base_url: str | None = None

    video_api_provider: str | None = None
    video_api_key: str | None = None
    video_api_base_url: str | None = None

    s3_endpoint_url: str | None = None
    s3_region_name: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket_name: str | None = None
    s3_base_path: str = ""
    s3_public_base_url: str | None = None

    local_storage_dir: str = "/data/storage"


settings = Settings()
