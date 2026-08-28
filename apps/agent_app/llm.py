from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from apps.agent_app.config import AgentAppSettings


class FallbackChatModel:
    def bind_tools(self, tools: Sequence[BaseTool | Any]) -> "FallbackChatModel":
        return self

    def invoke(self, messages: list[AnyMessage]) -> AIMessage:
        return AIMessage(
            content=(
                "Agent graph is loaded. Configure AGENT_STUDIO_USE_REAL_RUNTIME=true "
                "and model credentials to debug the real MCP tool loop."
            )
        )


def create_chat_model(settings: AgentAppSettings) -> Any:
    if settings.llm_provider == "ollama":
        return ChatOllama(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
        )
    if settings.llm_provider == "openai":
        return ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            temperature=settings.llm_temperature,
        )
    msg = f"Unsupported LLM provider: {settings.llm_provider}"
    raise ValueError(msg)
