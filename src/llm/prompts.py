"""System prompt and message builder for RAG-grounded tax Q&A."""

from src.db.models import RetrievalResult

_SYSTEM_PROMPT = """\
You are an NZ personal income tax assistant. Your role is to answer tax questions \
for New Zealand residents using ONLY the provided context from official IRD guidance.

Rules:
- Answer ONLY based on the provided context. Do not use outside knowledge.
- Cite your sources by referencing the context number (e.g. [1], [2]).
- If the context does not contain enough information to answer the question, say \
"I don't have enough information in my sources to answer that question."
- Be concise and direct. Use plain language.
- If the question is not about NZ personal income tax, politely decline to answer.\
"""


def build_rag_messages(
    query: str, chunks: list[RetrievalResult]
) -> list[dict[str, str]]:
    """Build the message list for a RAG-grounded LLM call.

    Args:
        query: The user's question.
        chunks: Retrieved context chunks with source attribution.

    Returns:
        OpenAI-format messages list (system + user).
    """
    context_parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        source_label = chunk.source_title or chunk.source_url
        if chunk.section_title:
            source_label += f" > {chunk.section_title}"
        context_parts.append(f"[{i}] {source_label}\n{chunk.content}")

    context_block = "\n\n---\n\n".join(context_parts)

    user_content = f"Context:\n{context_block}\n\nQuestion: {query}"

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
