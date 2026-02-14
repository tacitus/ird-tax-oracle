"""Query orchestrator: retrieve context, call LLM, return grounded answer."""

import json
import logging
from typing import Any

from src.db.models import AskResponse, SourceReference
from src.llm.gateway import LLMGateway
from src.llm.postprocess import linkify_bare_urls, strip_trailing_sources
from src.llm.prompts import build_rag_messages
from src.llm.tools import TOOLS
from src.rag.retriever import HybridRetriever

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 3


class Orchestrator:
    """Coordinates retrieval and LLM calls to answer a tax question."""

    def __init__(self, retriever: HybridRetriever, llm: LLMGateway) -> None:
        self._retriever = retriever
        self._llm = llm

    async def ask(self, question: str) -> AskResponse:
        """Answer a tax question using RAG with tool-call support.

        Args:
            question: The user's natural-language tax question.

        Returns:
            AskResponse with answer text, source citations, and model name.
        """
        logger.info("Processing question: %s", question[:80])

        # 1. Initial retrieval
        chunks = await self._retriever.search(question)
        all_chunks = list(chunks)
        logger.info("Retrieved %d chunks", len(chunks))

        # 2. Build messages
        messages: list[dict[str, Any]] = build_rag_messages(question, chunks)

        # 3. LLM completion loop (handles tool calls)
        tool_rounds = 0
        result = await self._llm.complete(messages, tools=TOOLS)

        while result.tool_calls and tool_rounds < _MAX_TOOL_ROUNDS:
            tool_rounds += 1
            logger.info("Tool call round %d", tool_rounds)

            # Append the assistant message with tool calls
            messages.append(result.raw_message.model_dump())

            for tool_call in result.tool_calls:
                tool_result = await self._execute_tool(tool_call)

                # Track chunks from follow-up searches
                if tool_call.function.name == "search_tax_documents":
                    followup_chunks = tool_result.get("_chunks", [])
                    all_chunks.extend(followup_chunks)

                # Append tool response message
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(
                        {k: v for k, v in tool_result.items() if not k.startswith("_")}
                    ),
                })

            result = await self._llm.complete(messages, tools=TOOLS)

        answer = result.content or ""

        # Deduplicate sources by URL
        seen_urls: set[str] = set()
        sources: list[SourceReference] = []
        for chunk in all_chunks:
            if chunk.source_url not in seen_urls:
                seen_urls.add(chunk.source_url)
                sources.append(
                    SourceReference(
                        url=chunk.source_url,
                        title=chunk.source_title,
                        section_title=chunk.section_title,
                    )
                )

        # Post-process: strip duplicate sources block, linkify bare URLs
        answer = strip_trailing_sources(answer)
        answer = linkify_bare_urls(answer, sources)

        return AskResponse(
            answer=answer,
            sources=sources,
            model=result.model,
        )

    async def _execute_tool(self, tool_call: Any) -> dict[str, Any]:
        """Execute a single tool call and return the result.

        Args:
            tool_call: The tool call object from the LLM response.

        Returns:
            Dict with tool results. Internal keys prefixed with '_' are
            stripped before sending to the LLM.
        """
        name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)
        logger.info("Executing tool=%s args=%s", name, args)

        if name == "search_tax_documents":
            followup_chunks = await self._retriever.search(
                query=args["query"],
                top_k=5,
            )
            return {
                "chunks": [
                    {
                        "title": c.source_title or c.source_url,
                        "url": c.source_url,
                        "section": c.section_title,
                        "content": c.content,
                    }
                    for c in followup_chunks
                ],
                "_chunks": followup_chunks,  # internal: for source tracking
            }

        logger.warning("Unknown tool requested: %s", name)
        return {"error": f"Unknown tool: {name}"}
