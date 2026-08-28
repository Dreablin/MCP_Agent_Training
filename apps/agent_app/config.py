import sys
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_LLM_PROVIDERS = ("ollama", "openai")


class AgentAppSettings(BaseSettings):
    app_name: str = Field(default="Agent App", min_length=1)
    log_level: str = "INFO"

    checkpoint_db_path: Path = PROJECT_ROOT / "data" / "agent_checkpoints.db"
    audit_db_path: Path = PROJECT_ROOT / "data" / "agent_debug.db"

    email_mcp_url: str = "http://127.0.0.1:8111/mcp"
    calendar_mcp_url: str = "http://127.0.0.1:8013/mcp/"
    todo_mcp_command: str = sys.executable
    todo_mcp_args: tuple[str, ...] = ("-m", "apps.todo_MCP.main")
    llm_provider: str = "ollama"
    llm_model: str = "gemma4:31b"
    llm_temperature: float = 0.0
    ollama_base_url: str = "http://127.0.0.1:11434"
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("AGENT_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    studio_use_real_runtime: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AGENT_",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            msg = f"Unsupported log level: {value}"
            raise ValueError(msg)
        return normalized

    @field_validator("llm_provider")
    @classmethod
    def normalize_llm_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_LLM_PROVIDERS:
            options = ", ".join(SUPPORTED_LLM_PROVIDERS)
            msg = f"Unsupported LLM provider: {value}. Supported values: {options}"
            raise ValueError(msg)
        return normalized

    def ensure_data_dir(self) -> None:
        self.checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_db_path.parent.mkdir(parents=True, exist_ok=True)


def get_settings() -> AgentAppSettings:
    return AgentAppSettings()
