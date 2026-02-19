"""Query orchestrator: retrieve context, call LLM, return grounded answer."""

import json
import logging
import time
from collections import Counter
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import asyncpg

from src.calculators.acc import calculate_acc_levy
from src.calculators.income_tax import calculate_income_tax
from src.calculators.paye import calculate_paye
from src.calculators.student_loan import calculate_student_loan_repayment
from src.db.models import AskResponse, SourceReference, ToolUsed
from src.db.query_log import log_query
from src.llm.gateway import LLMGateway
from src.llm.postprocess import linkify_bare_urls, strip_trailing_sources
from src.llm.prompts import build_rag_messages
from src.llm.tools import TOOLS
from src.rag.retriever import HybridRetriever

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 3

_TOOL_LABELS: dict[str, str] = {
    "calculate_income_tax": "Income tax calculator",
    "calculate_paye": "PAYE calculator",
    "calculate_student_loan_repayment": "Student loan calculator",
    "calculate_acc_levy": "ACC levy calculator",
    "search_tax_documents": "Document search",
}


class Orchestrator:
    """Coordinates retrieval and LLM calls to answer a tax question."""

    def __init__(
        self,
        retriever: HybridRetriever,
        llm: LLMGateway,
        pool: asyncpg.Pool | None = None,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._pool = pool

    async def ask(self, question: str) -> AskResponse:
        """Answer a tax question using RAG with tool-call support.

        Args:
            question: The user's natural-language tax question.

        Returns:
            AskResponse with answer text, source citations, and model name.
        """
        start = time.monotonic()
        logger.info("Processing question: %s", question[:80])

        # 1. Initial retrieval
        chunks = await self._retriever.search(question)
        all_chunks = list(chunks)
        logger.info("Retrieved %d chunks", len(chunks))

        # 2. Build messages
        messages: list[dict[str, Any]] = build_rag_messages(question, chunks)

        # 3. LLM completion loop (handles tool calls)
        tool_rounds = 0
        tools_used: list[ToolUsed] = []
        tool_call_log: list[dict] = []
        result = await self._llm.complete(messages, tools=TOOLS)

        while result.tool_calls and tool_rounds < _MAX_TOOL_ROUNDS:
            tool_rounds += 1
            logger.info("Tool call round %d", tool_rounds)

            # Append the assistant message with tool calls
            messages.append(result.raw_message.model_dump())

            for tool_call in result.tool_calls:
                tool_result = await self._execute_tool(tool_call)
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)

                # Track tool usage (deduplicated by name)
                if not any(t.name == name for t in tools_used):
                    tools_used.append(ToolUsed(
                        name=name,
                        label=_TOOL_LABELS.get(name, name),
                    ))

                # Log all tool calls (not deduplicated)
                tool_call_log.append({"name": name, "args": args})

                # Track chunks from follow-up searches
                if name == "search_tax_documents":
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

        # Deduplicate sources by URL; only show section_title when one chunk per URL
        url_counts = Counter(c.source_url for c in all_chunks)
        seen_urls: set[str] = set()
        sources: list[SourceReference] = []
        for chunk in all_chunks:
            if chunk.source_url not in seen_urls:
                seen_urls.add(chunk.source_url)
                sources.append(
                    SourceReference(
                        url=chunk.source_url,
                        title=chunk.source_title,
                        section_title=(
                            chunk.section_title if url_counts[chunk.source_url] == 1 else None
                        ),
                    )
                )

        # Post-process: strip duplicate sources block, linkify bare URLs
        answer = strip_trailing_sources(answer)
        answer = linkify_bare_urls(answer, sources)

        # Log query and get ID for feedback
        latency_ms = int((time.monotonic() - start) * 1000)
        query_id = None
        if self._pool is not None:
            query_id = await log_query(
                self._pool, question, answer, result.model, latency_ms,
                tool_calls=tool_call_log or None,
            )

        return AskResponse(
            answer=answer,
            sources=sources,
            model=result.model,
            tools_used=tools_used,
            query_id=query_id,
        )

    async def ask_stream(self, question: str) -> AsyncIterator[dict[str, Any]]:
        """Stream an answer to a tax question via SSE-compatible events.

        Yields dicts with event type and payload:
          {"type": "status", "message": "Searching..."}
          {"type": "tool_use", "tool": "...", "label": "..."}
          {"type": "chunk", "delta": "..."}
          {"type": "sources", "sources": [...]}
          {"type": "done", "model": "..."}

        Args:
            question: The user's natural-language tax question.
        """
        start = time.monotonic()
        logger.info("Streaming question: %s", question[:80])

        yield {"type": "status", "message": "Searching tax documents..."}

        # 1. Retrieve context
        chunks = await self._retriever.search(question)
        all_chunks = list(chunks)
        logger.info("Retrieved %d chunks for stream", len(chunks))

        yield {"type": "status", "message": "Generating answer..."}

        # 2. Build messages
        messages: list[dict[str, Any]] = build_rag_messages(question, chunks)

        # 3. Tool loop (non-streamed) — execute tools before streaming final answer
        tool_rounds = 0
        tools_used_names: set[str] = set()
        tool_call_log: list[dict] = []
        result = await self._llm.complete(messages, tools=TOOLS)

        while result.tool_calls and tool_rounds < _MAX_TOOL_ROUNDS:
            tool_rounds += 1
            logger.info("Stream tool call round %d", tool_rounds)
            messages.append(result.raw_message.model_dump())

            for tool_call in result.tool_calls:
                tool_result = await self._execute_tool(tool_call)
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)

                # Emit tool_use event (deduplicated)
                if name not in tools_used_names:
                    tools_used_names.add(name)
                    yield {
                        "type": "tool_use",
                        "tool": name,
                        "label": _TOOL_LABELS.get(name, name),
                    }

                # Log all tool calls
                tool_call_log.append({"name": name, "args": args})

                # Track chunks from follow-up searches
                if name == "search_tax_documents":
                    followup_chunks = tool_result.get("_chunks", [])
                    all_chunks.extend(followup_chunks)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(
                        {k: v for k, v in tool_result.items()
                         if not k.startswith("_")}
                    ),
                })

            result = await self._llm.complete(messages, tools=TOOLS)

        # 4. Stream the final LLM response
        if result.content:
            # LLM already gave a final text answer (no streaming needed)
            full_answer = result.content
            yield {"type": "chunk", "delta": full_answer}
        else:
            # Stream from scratch with the full message history
            full_answer = ""
            async for delta in self._llm.stream(messages):
                full_answer += delta
                yield {"type": "chunk", "delta": delta}

        # 5. Build sources; only show section_title when one chunk per URL
        url_counts = Counter(c.source_url for c in all_chunks)
        seen_urls: set[str] = set()
        sources: list[SourceReference] = []
        for chunk in all_chunks:
            if chunk.source_url not in seen_urls:
                seen_urls.add(chunk.source_url)
                sources.append(
                    SourceReference(
                        url=chunk.source_url,
                        title=chunk.source_title,
                        section_title=(
                            chunk.section_title if url_counts[chunk.source_url] == 1 else None
                        ),
                    )
                )

        yield {
            "type": "sources",
            "sources": [s.model_dump() for s in sources],
        }

        # Log query before emitting "done" so we can include query_id
        latency_ms = int((time.monotonic() - start) * 1000)
        model_name = result.model or self._llm.model
        query_id = None
        if self._pool is not None:
            query_id = await log_query(
                self._pool, question, full_answer, model_name, latency_ms,
                tool_calls=tool_call_log or None,
            )

        yield {
            "type": "done",
            "model": model_name,
            "query_id": str(query_id) if query_id else None,
        }

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
                source_type=args.get("source_type_filter"),
                tax_year=args.get("tax_year_filter"),
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

        if name == "calculate_income_tax":
            return calculate_income_tax(
                annual_income=Decimal(str(args["annual_income"])),
                tax_year=args.get("tax_year", "2025-26"),
            )

        if name == "calculate_paye":
            return calculate_paye(
                annual_income=Decimal(str(args["annual_income"])),
                pay_period=args.get("pay_period", "monthly"),
                has_student_loan=args.get("has_student_loan", False),
                tax_year=args.get("tax_year", "2025-26"),
            )

        if name == "calculate_student_loan_repayment":
            return calculate_student_loan_repayment(
                annual_income=Decimal(str(args["annual_income"])),
                tax_year=args.get("tax_year", "2025-26"),
            )

        if name == "calculate_acc_levy":
            return calculate_acc_levy(
                annual_income=Decimal(str(args["annual_income"])),
                tax_year=args.get("tax_year", "2025-26"),
            )

        logger.warning("Unknown tool requested: %s", name)
        return {"error": f"Unknown tool: {name}"}
