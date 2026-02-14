"""Thin async wrapper around LiteLLM for LLM completions."""

import logging

import litellm

from config.settings import settings

logger = logging.getLogger(__name__)


class LLMGateway:
    """Async LLM completion via LiteLLM."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.llm_default_model

    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Send messages to the LLM and return the response text.

        Args:
            messages: OpenAI-format message list (system/user/assistant).

        Returns:
            The assistant's response text.
        """
        logger.info("Calling LLM model=%s", self.model)
        response = await litellm.acompletion(
            model=self.model,
            messages=messages,
            temperature=0.1,
        )
        content: str = response.choices[0].message.content  # type: ignore[union-attr]
        return content
