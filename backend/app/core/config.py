from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CarMe API"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"
    frontend_origin: str = "http://localhost:5173"

    database_url: str
    s3_endpoint_url: str
    s3_bucket: str = "carme-private"
    s3_region: str = "ap-northeast-2"
    s3_access_key: str
    s3_secret_key: str

    kakao_rest_api_key: str = ""
    kakao_redirect_uri: str = ""
    jwt_secret: str
    jwt_access_ttl_minutes: int = 30
    jwt_refresh_ttl_days: int = 14

    openai_api_key: str = ""
    openai_chat_model: str = ""
    embedding_model_name: str = "BAAI/bge-m3"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
