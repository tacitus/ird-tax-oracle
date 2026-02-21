"""Rewrite follow-up questions into standalone queries for retrieval."""

import logging

from src.db.models import ConversationTurn
from src.llm.gateway import LLMGateway

logger = logging.getLogger(__name__)

_REWRITE_SYSTEM_PROMPT = (
    "You are a query rewriter. Given a conversation history and a follow-up "
    "question, rewrite the follow-up as a standalone question suitable for "
    "searching a document database about New Zealand tax. Keep it concise. "
    "If the question is already standalone, return it unchanged. "
    "Return ONLY the rewritten question — no explanation or preamble."
)

_MAX_HISTORY_FOR_REWRITE = 3


async def rewrite_query(
    llm: LLMGateway,
    question: str,
    history: list[ConversationTurn],
) -> str:
    """Rewrite a follow-up question into a standalone retrieval query.

    If no history is provided, returns the question unchanged (no LLM call).

    Args:
        llm: LLM gateway for the rewrite call.
        question: The user's raw follow-up question.
        history: Prior conversation turns for context.

    Returns:
        A standalone question suitable for retrieval.
    """
    if not history:
        return question

    # Use only the last N turns for rewrite context
    recent = history[-_MAX_HISTORY_FOR_REWRITE:]

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _REWRITE_SYSTEM_PROMPT},
    ]
    for turn in recent:
        messages.append({"role": "user", "content": turn.question})
        messages.append({"role": "assistant", "content": turn.answer})
    messages.append({"role": "user", "content": question})

    result = await llm.complete(messages)
    rewritten = (result.content or question).strip()

    if rewritten != question:
        logger.info(
            "Query rewritten: %r -> %r", question[:80], rewritten[:80]
        )

    return rewritten
