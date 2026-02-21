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
                        "qwba",
                        "fact_sheet",
                        "operational_statement",
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

CALCULATE_INCOME_TAX: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "calculate_income_tax",
        "description": (
            "Calculate NZ income tax for a given annual income with a "
            "bracket-by-bracket breakdown. Use when a user asks 'how much "
            "tax on $X' or 'what is my tax on $X income'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "annual_income": {
                    "type": "number",
                    "description": "Gross annual income in NZD.",
                },
                "tax_year": {
                    "type": "string",
                    "description": (
                        "Tax year, e.g. '2025-26'. Defaults to the current "
                        "tax year if not specified."
                    ),
                },
            },
            "required": ["annual_income"],
        },
    },
}

CALCULATE_PAYE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "calculate_paye",
        "description": (
            "Calculate PAYE deductions per pay period, including income tax, "
            "ACC earner's levy, and optional student loan repayment. Use when "
            "asked about take-home pay, net pay, or PAYE deductions. "
            "Limitations: assumes tax code M or ME (standard employee), "
            "does not include KiwiSaver employee/employer contributions, "
            "and does not handle secondary employment tax codes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "annual_income": {
                    "type": "number",
                    "description": "Gross annual income in NZD.",
                },
                "pay_period": {
                    "type": "string",
                    "enum": ["weekly", "fortnightly", "four-weekly", "monthly"],
                    "description": "Pay frequency. Defaults to 'monthly'.",
                },
                "has_student_loan": {
                    "type": "boolean",
                    "description": "Whether to include student loan repayment.",
                },
                "tax_year": {
                    "type": "string",
                    "description": (
                        "Tax year, e.g. '2025-26'. Defaults to the current "
                        "tax year if not specified."
                    ),
                },
            },
            "required": ["annual_income"],
        },
    },
}

CALCULATE_STUDENT_LOAN: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "calculate_student_loan_repayment",
        "description": (
            "Calculate annual student loan repayment amount. Use when asked "
            "about student loan repayments or deductions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "annual_income": {
                    "type": "number",
                    "description": "Gross annual income in NZD.",
                },
                "tax_year": {
                    "type": "string",
                    "description": (
                        "Tax year, e.g. '2025-26'. Defaults to the current "
                        "tax year if not specified."
                    ),
                },
            },
            "required": ["annual_income"],
        },
    },
}

CALCULATE_ACC_LEVY: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "calculate_acc_levy",
        "description": (
            "Calculate ACC earner's levy for a given annual income. Use when "
            "asked about ACC levies or contributions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "annual_income": {
                    "type": "number",
                    "description": "Gross annual income in NZD.",
                },
                "tax_year": {
                    "type": "string",
                    "description": (
                        "Tax year, e.g. '2025-26'. Defaults to the current "
                        "tax year if not specified."
                    ),
                },
            },
            "required": ["annual_income"],
        },
    },
}

TOOLS: list[dict[str, Any]] = [
    SEARCH_TAX_DOCUMENTS,
    CALCULATE_INCOME_TAX,
    CALCULATE_PAYE,
    CALCULATE_STUDENT_LOAN,
    CALCULATE_ACC_LEVY,
]
