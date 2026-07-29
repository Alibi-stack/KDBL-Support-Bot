from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    admin_chat_id: int | None = Field(default=None, alias="ADMIN_CHAT_ID")
    ai_request_timeout: int = Field(default=60, alias="AI_REQUEST_TIMEOUT")
    database_url: str = Field(
        default="postgresql://kdbl:kdbl@localhost:5432/support",
        alias="DATABASE_URL",
    )
    ai_provider: str = Field(default="stub", alias="AI_PROVIDER")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    use_forum_topics: bool = Field(default=True, alias="USE_FORUM_TOPICS")
    kb_path: str = Field(default="knowledge_base.json", alias="KB_PATH")
    chroma_dir: str = Field(default="./chroma_store", alias="CHROMA_DIR")
    chroma_host: str = Field(default="localhost", alias="CHROMA_HOST")
    chroma_port: int = Field(default=8000, alias="CHROMA_PORT")
    use_vector_rag: bool = Field(default=False, alias="USE_VECTOR_RAG")
    alert_chat_id: int | None = Field(default=None, alias="ALERT_CHAT_ID")
    alert_thread_id: int | None = Field(default=None, alias="ALERT_THREAD_ID")
    timezone: str = Field(default="Asia/Qyzylorda", alias="TIMEZONE")
    workday_start_hour: int = Field(default=9, alias="WORKDAY_START_HOUR")
    workday_start_minute: int = Field(default=30, alias="WORKDAY_START_MINUTE")
    workday_end_hour: int = Field(default=18, alias="WORKDAY_END_HOUR")
    report_hour: int = Field(default=18, alias="REPORT_HOUR")
    duty_contact: str | None = Field(default=None, alias="DUTY_CONTACT")

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

    @field_validator("duty_contact", mode="before")
    @classmethod
    def empty_duty_contact_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("alert_chat_id", "alert_thread_id", mode="before")
    @classmethod
    def empty_alert_ids_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def default_alert_chat_id_to_admin_chat_id(self) -> "Settings":
        # Алерты по умолчанию идут в ту же операторскую группу, что и
        # тикеты, если ALERT_CHAT_ID отдельно не задан в .env.
        if self.alert_chat_id is None:
            self.alert_chat_id = self.admin_chat_id
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
