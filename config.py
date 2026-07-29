from functools import lru_cache

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.env_crypto import decrypt_env_value


class Settings(BaseSettings):
    env_secret_key: str | None = Field(default=None, alias="ENV_SECRET_KEY")
    bot_token: str = Field(alias="BOT_TOKEN")
    admin_chat_id: int | None = Field(default=None, alias="ADMIN_CHAT_ID")
    rate_limit_messages: int = Field(default=5, alias="RATE_LIMIT_MESSAGES")
    rate_limit_window: int = Field(default=10, alias="RATE_LIMIT_WINDOW")
    ai_request_timeout: int = Field(default=60, alias="AI_REQUEST_TIMEOUT")
    database_path: str = Field(default="support.db", alias="DATABASE_PATH")
    ai_provider: str = Field(default="stub", alias="AI_PROVIDER")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    use_forum_topics: bool = Field(default=True, alias="USE_FORUM_TOPICS")
    kb_path: str = Field(default="knowledge_base.json", alias="KB_PATH")
    chroma_dir: str = Field(default="./chroma_store", alias="CHROMA_DIR")
    use_vector_rag: bool = Field(default=False, alias="USE_VECTOR_RAG")
    timezone: str = Field(default="Asia/Qyzylorda", alias="TIMEZONE")
    workday_start_hour: int = Field(default=9, alias="WORKDAY_START_HOUR")
    workday_start_minute: int = Field(default=30, alias="WORKDAY_START_MINUTE")
    workday_end_hour: int = Field(default=18, alias="WORKDAY_END_HOUR")
    report_hour: int = Field(default=18, alias="REPORT_HOUR")
    duty_contact: str | None = Field(default=None, alias="DUTY_CONTACT")

    @field_validator("bot_token", "gemini_api_key", "groq_api_key", mode="before")
    @classmethod
    def decrypt_secret_values(cls, value: object, info: ValidationInfo) -> object:
        secret_key = info.data.get("env_secret_key") if info.data else None
        return decrypt_env_value(value, secret_key)

    @field_validator("admin_chat_id", mode="before")
    @classmethod
    def empty_admin_chat_id_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("groq_api_key", mode="before")
    @classmethod
    def empty_groq_api_key_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("gemini_api_key", mode="before")
    @classmethod
    def empty_gemini_api_key_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("duty_contact", mode="before")
    @classmethod
    def empty_duty_contact_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
