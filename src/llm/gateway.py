"""Thin async wrapper around LiteLLM for LLM completions."""

import logging
from typing import Any

import litellm
from pydantic import BaseModel

from config.settings import settings

logger = logging.getLogger(__name__)


class CompletionResult(BaseModel):
    """Result from an LLM completion, carrying both content and tool calls."""

    content: str | None = None
    tool_calls: list[Any] | None = None
    raw_message: Any = None
    model: str = ""


class LLMGateway:
    """Async LLM completion via LiteLLM."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.llm_default_model

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> CompletionResult:
        """Send messages to the LLM and return the response.

        Args:
            messages: OpenAI-format message list (system/user/assistant/tool).
            tools: Optional tool definitions in OpenAI format.

        Returns:
            CompletionResult with content, tool_calls, and raw message.
        """
        logger.info("Calling LLM model=%s tools=%s", self.model, bool(tools))
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
        }
        if tools:
            kwargs["tools"] = tools

        response = await litellm.acompletion(**kwargs)
        message = response.choices[0].message

        return CompletionResult(
            content=message.content,
            tool_calls=message.tool_calls,
            raw_message=message,
            model=response.model or self.model,
        )
