from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    admin_chat_id: int | None = Field(default=None, alias="ADMIN_CHAT_ID")
    ai_request_timeout: int = Field(default=30, alias="AI_REQUEST_TIMEOUT")
    database_path: str = Field(default="support.db", alias="DATABASE_PATH")
    ai_provider: str = Field(default="stub", alias="AI_PROVIDER")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    use_forum_topics: bool = Field(default=True, alias="USE_FORUM_TOPICS")
    kb_path: str = Field(default="knowledge_base.json", alias="KB_PATH")
    chroma_dir: str = Field(default="./chroma_store", alias="CHROMA_DIR")

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
