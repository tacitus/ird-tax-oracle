"""Query orchestrator: retrieve context, call LLM, return grounded answer."""

import logging

from src.db.models import AskResponse, SourceReference
from src.llm.gateway import LLMGateway
from src.llm.prompts import build_rag_messages
from src.rag.retriever import HybridRetriever

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates retrieval and LLM calls to answer a tax question."""

    def __init__(self, retriever: HybridRetriever, llm: LLMGateway) -> None:
        self._retriever = retriever
        self._llm = llm

    async def ask(self, question: str) -> AskResponse:
        """Answer a tax question using RAG.

        Args:
            question: The user's natural-language tax question.

        Returns:
            AskResponse with answer text, source citations, and model name.
        """
        logger.info("Processing question: %s", question[:80])

        chunks = await self._retriever.search(question)
        logger.info("Retrieved %d chunks", len(chunks))

        messages = build_rag_messages(question, chunks)
        answer = await self._llm.complete(messages)

        # Deduplicate sources by URL
        seen_urls: set[str] = set()
        sources: list[SourceReference] = []
        for chunk in chunks:
            if chunk.source_url not in seen_urls:
                seen_urls.add(chunk.source_url)
                sources.append(
                    SourceReference(
                        url=chunk.source_url,
                        title=chunk.source_title,
                        section_title=chunk.section_title,
                    )
                )

        return AskResponse(
            answer=answer,
            sources=sources,
            model=self._llm.model,
        )
