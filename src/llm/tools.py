"""Tool definitions for LLM function calling (OpenAI format)."""

from typing import Any

SEARCH_TAX_DOCUMENTS: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_tax_documents",
        "description": (
            "Search the NZ tax document corpus for information on a specific "
            "topic. Use this when the provided context doesn't contain enough "
            "information to answer the user's question, or when you need to "
            "look up a specific section, form, or tax concept."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A natural language search query. Be specific — "
                        "include section references (e.g., 'section CE 1'), "
                        "form numbers (e.g., 'IR3'), tax codes "
                        "(e.g., 'tax code SL'), or specific concepts "
                        "(e.g., 'independent earner tax credit eligibility')."
                    ),
                },
                "source_type_filter": {
                    "type": "string",
                    "enum": [
                        "ird_guidance",
                        "legislation",
                        "tib",
                        "guide_pdf",
                        "interpretation_statement",
                    ],
                    "description": (
                        "Optional: filter results to a specific source type. "
                        "Use 'legislation' when the user asks about the law "
                        "itself, 'ird_guidance' for practical how-to questions."
                    ),
                },
                "tax_year_filter": {
                    "type": "string",
                    "description": (
                        "Optional: filter results to a specific tax year, "
                        "e.g., '2025-26'. Use when the user is asking about "
                        "a specific year."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}

# All tools available for the LLM. Calculator tools will be added in Phase 2.
TOOLS: list[dict[str, Any]] = [SEARCH_TAX_DOCUMENTS]
