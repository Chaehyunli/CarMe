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
    kakao_client_secret: str = ""
    kakao_redirect_uri: str = ""
    frontend_login_callback_url: str = "http://localhost:5173/auth/callback"
    admin_signup_code: str = ""
    jwt_secret: str
    jwt_access_ttl_minutes: int = 30
    jwt_refresh_ttl_days: int = 14
    upload_url_ttl_seconds: int = 300

    openai_api_key: str = ""
    openai_chat_model: str = ""
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen3:8b"
    ollama_embedding_model: str = "qwen3-embedding:4b"
    embedding_model_name: str = "qwen3-embedding:4b"
    embedding_dimensions: int = 1024
    chat_session_idle_ttl_minutes: int = 30
    rag_minimum_evidence_score: float = 9.0
    rag_minimum_topic_coverage: float = 0.5
    rag_minimum_score_gap: float = 0.75
    rag_minimum_diagnostic_signals: int = 1
    rag_max_context_chunks: int = 4
    rag_intent_llm_enabled: bool = True
    rag_intent_model: str = ""
    rag_intent_timeout_seconds: float = 4.0
    rag_intent_history_turns: int = 4
    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com"
    official_source_sync_timeout_seconds: float = 30.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
