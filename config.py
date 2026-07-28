from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    admin_chat_id: int | None = Field(default=None, alias="ADMIN_CHAT_ID")
    ai_request_timeout: int = Field(default=30, alias="AI_REQUEST_TIMEOUT")
    database_path: str = Field(default="support.db", alias="DATABASE_PATH")
    ai_provider: str = Field(default="stub", alias="AI_PROVIDER")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    use_forum_topics: bool = Field(default=True, alias="USE_FORUM_TOPICS")

    @field_validator("admin_chat_id", mode="before")
    @classmethod
    def empty_admin_chat_id_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("gemini_api_key", mode="before")
    @classmethod
    def empty_gemini_api_key_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
