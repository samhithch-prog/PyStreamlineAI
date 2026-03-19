from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ZoSwi AI Interview API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    frontend_origin: str = "http://localhost:3000"

    database_url: str = "sqlite+aiosqlite:///./zoswi_interview.db"
    redis_url: str = ""

    auth_required: bool = True
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "zoswi-auth"
    jwt_audience: str = "zoswi-platform"
    access_token_ttl_seconds: int = 3600
    streamlit_launch_secret: str = ""
    streamlit_launch_issuer: str = "zoswi-streamlit"
    streamlit_launch_audience: str = "zoswi-interview-launch"
    ws_token_ttl_seconds: int = 60

    openai_api_key: str = ""
    openai_api_setting_key: str = "ZOSWI_AI_API_KEY"
    db_api_key_cache_ttl_seconds: int = 30
    stt_model: str = "gpt-4o-mini-transcribe"
    stt_fallback_models: str = "whisper-1"
    llm_model: str = "gpt-4.1-mini"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "cedar"
    llm_fallback_models: str = "gpt-4o-mini"

    max_questions_per_interview: int = 5
    answer_time_limit_seconds: int = 120
    interview_duration_seconds: int = 1800
    storage_dir: str = "storage"
    ws_events_per_minute: int = 120
    api_requests_per_minute: int = 300
    candidate_max_active_interviews: int = 3
    candidate_max_interviews_total: int = 3
    candidate_max_interviews_per_day: int = 10
    recruiter_review_limit_per_minute: int = 50

    telemetry_enabled: bool = False
    telemetry_service_name: str = "zoswi-ai-interview-api"
    telemetry_otlp_endpoint: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
