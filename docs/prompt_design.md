# NZ Tax RAG — System Prompt & Tool Design

> Companion document to `design.md`. Covers the LLM system prompt, tool
> definitions, orchestrator prompt template, and evaluation scenarios.
>
> **Last updated:** 2026-02-14

---

## 1. Design Principles

The system prompt is the most consequential piece of text in the entire system.
A wrong tax number from an LLM hallucination is worse than no answer at all.
Every design decision here optimises for **correctness first**, helpfulness second.

### 1.1 Core Constraints

1. **Never fabricate tax figures.** All rates, thresholds, and dollar amounts must
   come from retrieved context or deterministic calculator tools — never from the
   LLM's parametric memory. This is the single most important rule.

2. **Cite every factual claim.** Every rate, threshold, rule, or deadline must
   include a source reference so the user can verify it. Trust is earned through
   transparency.

3. **Stay in scope.** The system covers NZ personal income tax for individuals.
   It must clearly decline questions about GST, company tax, trusts, and
   international tax — and explain *what* it can help with instead.

4. **Default to the current tax year.** NZ tax years run 1 April – 31 March
   (e.g., the 2025–26 year is 1 April 2025 to 31 March 2026). When the user
   doesn't specify a year, assume the current year. When rules have recently
   changed, flag this proactively.

5. **Prefer tools over arithmetic.** When the user asks "how much tax on
   $85,000", the LLM should call the `calculate_income_tax` tool rather than
   attempting mental arithmetic. LLMs are unreliable at multi-step maths.

6. **Disclaim appropriately.** This system provides general tax information, not
   professional tax advice. Complex or ambiguous situations should recommend
   consulting a tax professional or IRD directly.

### 1.2 Architectural Context

The orchestrator retrieves context *before* calling the LLM. The flow is:

```
User question
    → Orchestrator embeds query
    → Hybrid retrieval (semantic + keyword)
    → Top-k chunks injected into prompt as <context>
    → LLM generates answer (may call tools)
    → If tool call: execute tool, return result to LLM
    → Final answer returned to user
```

This means the LLM always receives pre-retrieved context. It does not "decide"
whether to search — the retrieval has already happened. The LLM's job is to
synthesise that context into a clear answer, call calculator tools when
computation is needed, and cite its sources.

---

## 2. System Prompt

### 2.1 Design Rationale

The prompt is structured in layers, from most to least critical:

1. **Identity and scope** — What is this system, what does it cover
2. **Hard rules** — The non-negotiable constraints (no fabrication, cite sources)
3. **Context handling** — How to use the retrieved chunks
4. **Tool usage** — When and how to call calculators
5. **Tax year logic** — Default year, how to handle ambiguity
6. **Response style** — Tone, structure, disclaimers
7. **Scope boundaries** — What's out of scope and how to decline

The prompt uses XML-style tags for structure because most LLMs (Gemini, Claude,
GPT-4) parse these reliably, and LiteLLM preserves them across providers. The
`<context>` block is injected by the orchestrator at call time.

### 2.2 The Prompt

```
You are a New Zealand personal income tax assistant. You help New Zealand
residents understand their income tax obligations using authoritative
information from Inland Revenue (IRD) guidance, the Income Tax Act 2007,
and related official sources.

<hard_rules>
1. NEVER state a tax rate, threshold, dollar amount, deadline, or
   percentage from your own knowledge. Use ONLY the information provided
   in <context> or returned by a tool call. If the context doesn't contain
   the answer, say so — do not guess.

2. ALWAYS cite your sources. When stating a fact from the context, include
   the source document title and URL in your answer, e.g.:
   "The top marginal rate is 39% for income over $180,000
   (IRD: Tax rates for individuals, ird.govt.nz/…)."

3. When a user asks for a tax calculation (e.g., "how much tax on $X"),
   call the appropriate calculator tool. Do not perform tax arithmetic
   yourself.

4. If the retrieved context is insufficient or contradictory, tell the
   user what you found and what's missing. Suggest they check ird.govt.nz
   directly or consult a tax professional.

5. If asked about a topic outside your scope (GST, company tax, trusts,
   international tax, provisional tax for businesses), say clearly:
   "That's outside what I cover. I focus on personal income tax for NZ
   residents — things like PAYE, tax credits, KiwiSaver, student loans,
   and individual tax returns. For [topic], I'd suggest checking
   ird.govt.nz/[relevant-section] or talking to a tax advisor."
</hard_rules>

<tax_year_rules>
The current NZ tax year is {current_tax_year} ({tax_year_start} to
{tax_year_end}).

- When the user doesn't specify a tax year, assume they mean the current
  tax year ({current_tax_year}).
- When recent tax changes are relevant (e.g., a new bracket was introduced
  in the current year), proactively note the change and when it took
  effect.
- If the user asks about a prior year and the context contains that
  year's data, answer using the correct year's figures. If you only have
  current-year data, say so.
- If a question is ambiguous about the tax year and the answer would
  differ materially between years, ask which year they mean.
</tax_year_rules>

<context_instructions>
You will receive retrieved document chunks in a <context> block. Each
chunk has metadata including its source URL, document title, source type,
and section reference.

When using context:
- Prefer IRD guidance pages over raw legislation for explaining concepts
  to users — they are written in plain language.
- Use legislation references to back up specific legal points when the
  user asks a detailed or technical question.
- If multiple chunks cover the same topic, synthesise them rather than
  repeating each one. Resolve any apparent contradictions by noting the
  source dates and preferring the most recent.
- Cross-references in legislation (e.g., "see section CE 1") may appear
  in the context. If a cross-referenced section was retrieved, use it.
  If not, note the cross-reference and suggest the user check it.
</context_instructions>

<response_style>
- Write in clear, plain New Zealand English.
- Use NZ terminology: "Inland Revenue" or "IRD" (not "IRS" or "HMRC"),
  "tax code" (not "filing status"), "ACC earner's levy" (not "social
  security"), "KiwiSaver" (one word, capital K and S).
- Keep answers focused. A typical answer should be 2–4 paragraphs. For
  simple factual questions, shorter is better.
- Use specific numbers and examples where they help. "You'd pay $10,500
  on the first $14,000 at 10.5%, then…" is better than "the rate
  increases with income."
- End every answer with a brief source attribution line, e.g.:
  "Sources: IRD — Tax rates for individuals; Income Tax Act 2007, s YA 1."
- If the question involves a complex or unusual scenario (e.g., multiple
  income sources, transitional residency, look-through companies), add:
  "This is general information — for your specific situation, consider
  consulting a tax advisor or contacting IRD."
</response_style>
```

### 2.3 Template Variables

The orchestrator injects these at call time:

| Variable | Example | Source |
|----------|---------|--------|
| `{current_tax_year}` | `2025–26` | Derived from system date |
| `{tax_year_start}` | `1 April 2025` | Derived from system date |
| `{tax_year_end}` | `31 March 2026` | Derived from system date |

The `<context>` block is injected as a separate section in the message
sequence (see §4, Orchestrator Prompt Template).

### 2.4 What the Prompt Deliberately Does NOT Include

1. **Specific tax rates or thresholds.** These come from retrieved context and
   change over time. Embedding them in the prompt creates a staleness risk and
   a contradiction risk (prompt says X, context says Y — which does the LLM
   follow?).

2. **A comprehensive list of tax codes.** Same reason. The M, ME, SL, SH, etc.
   codes and their meanings should come from the RAG corpus.

3. **Calculator implementation details.** The LLM doesn't need to know how the
   calculator works internally — just when to call it and what parameters to
   provide.

4. **Worked examples in the prompt.** Few-shot examples baked into a system
   prompt are tempting but dangerous for tax: they can become stale and the LLM
   may pattern-match against them rather than using retrieved context. If we
   want few-shot examples, they should be dynamically selected from a curated
   examples table based on query similarity (a Phase 2 enhancement).

---

## 3. Tool Definitions (OpenAI Format)

These are defined once in `src/llm/tools.py` and passed to LiteLLM, which
translates them to each provider's native format.

### 3.1 Phase 1 Tools

#### `search_tax_documents`

This tool is called by the LLM when it needs *additional* context beyond what
was pre-retrieved. This is a fallback — most queries should be answerable from
the initial retrieval. But if the user asks a follow-up or the initial chunks
don't cover the topic, the LLM can request a targeted search.

```json
{
  "type": "function",
  "function": {
    "name": "search_tax_documents",
    "description": "Search the NZ tax document corpus for information on a specific topic. Use this when the provided context doesn't contain enough information to answer the user's question, or when you need to look up a specific section, form, or tax concept.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "A natural language search query. Be specific — include section references (e.g., 'section CE 1'), form numbers (e.g., 'IR3'), tax codes (e.g., 'tax code SL'), or specific concepts (e.g., 'independent earner tax credit eligibility')."
        },
        "source_type_filter": {
          "type": "string",
          "enum": [
            "ird_guidance",
            "legislation",
            "tib",
            "guide_pdf",
            "interpretation_statement"
          ],
          "description": "Optional: filter results to a specific source type. Use 'legislation' when the user asks about the law itself, 'ird_guidance' for practical how-to questions."
        },
        "tax_year_filter": {
          "type": "string",
          "description": "Optional: filter results to a specific tax year, e.g., '2025-26'. Use when the user is asking about a specific year."
        }
      },
      "required": ["query"]
    }
  }
}
```

### 3.2 Phase 2 Tools (Calculators)

These are deterministic Python functions exposed as tools. The LLM calls them
with structured parameters; the orchestrator executes them and returns results.

#### `calculate_income_tax`

```json
{
  "type": "function",
  "function": {
    "name": "calculate_income_tax",
    "description": "Calculate New Zealand income tax for an individual given their taxable income. Returns a breakdown by tax bracket showing the marginal rate, income in each bracket, and tax payable. Also returns the effective tax rate. Use this whenever a user asks 'how much tax do I pay on $X' or similar.",
    "parameters": {
      "type": "object",
      "properties": {
        "taxable_income": {
          "type": "number",
          "description": "Annual taxable income in NZD. This is gross income minus allowable deductions."
        },
        "tax_year": {
          "type": "string",
          "description": "Tax year, e.g., '2025-26'. Defaults to the current tax year if omitted."
        }
      },
      "required": ["taxable_income"]
    }
  }
}
```

#### `calculate_paye`

```json
{
  "type": "function",
  "function": {
    "name": "calculate_paye",
    "description": "Calculate PAYE (Pay As You Earn) withholding for a pay period. Returns the PAYE amount to be withheld from the employee's pay. Use when a user asks about their take-home pay, PAYE deductions, or payslip calculations.",
    "parameters": {
      "type": "object",
      "properties": {
        "gross_pay": {
          "type": "number",
          "description": "Gross pay for the period in NZD."
        },
        "pay_frequency": {
          "type": "string",
          "enum": ["weekly", "fortnightly", "four-weekly", "monthly"],
          "description": "How often the employee is paid."
        },
        "tax_code": {
          "type": "string",
          "description": "The employee's tax code, e.g., 'M', 'ME', 'SL', 'M SL', 'S', 'SH', 'ST'. Determines secondary income rates and student loan deductions."
        },
        "tax_year": {
          "type": "string",
          "description": "Tax year, e.g., '2025-26'. Defaults to the current tax year if omitted."
        }
      },
      "required": ["gross_pay", "pay_frequency", "tax_code"]
    }
  }
}
```

#### `calculate_student_loan_repayment`

```json
{
  "type": "function",
  "function": {
    "name": "calculate_student_loan_repayment",
    "description": "Calculate student loan repayment obligations for a given income. Returns the annual repayment amount based on income above the repayment threshold. Use when a user asks about student loan deductions or repayment amounts.",
    "parameters": {
      "type": "object",
      "properties": {
        "annual_income": {
          "type": "number",
          "description": "Annual gross income in NZD."
        },
        "tax_year": {
          "type": "string",
          "description": "Tax year, e.g., '2025-26'. Defaults to the current tax year."
        }
      },
      "required": ["annual_income"]
    }
  }
}
```

#### `calculate_acc_levy`

```json
{
  "type": "function",
  "function": {
    "name": "calculate_acc_levy",
    "description": "Calculate the ACC earner's levy for a given income. Returns the annual levy amount. The earner's levy is capped at a maximum liable income. Use when a user asks about ACC deductions or levies.",
    "parameters": {
      "type": "object",
      "properties": {
        "annual_income": {
          "type": "number",
          "description": "Annual liable income in NZD."
        },
        "tax_year": {
          "type": "string",
          "description": "Tax year, e.g., '2025-26'. Defaults to the current tax year."
        }
      },
      "required": ["annual_income"]
    }
  }
}
```

### 3.3 Tool Design Decisions

**Why not a single `calculate_deductions` mega-tool?** Because the LLM needs to
reason about which deduction applies. A user asking "what's my take-home pay"
needs PAYE + ACC + possibly student loan + possibly KiwiSaver. The LLM should
call each relevant tool and synthesise the results. A mega-tool hides the
reasoning and makes it harder to test individual components.

**Why is `tax_year` optional on all calculators?** Because the orchestrator knows
the current tax year and most questions are about the current year. Making it
required would force the LLM to always specify it, increasing the chance of
hallucinating a wrong year string.

**Why no `calculate_kiwisaver` tool in Phase 2?** KiwiSaver contribution rates
(3%, 4%, 6%, 8%, 10%) are straightforward percentages of gross pay. The LLM can
state these from context without a dedicated calculator. A tool might be useful
later for calculating employer contributions and ESCT (employer superannuation
contribution tax), which are more complex.

---

## 4. Orchestrator Prompt Template

This is the message sequence the orchestrator constructs for each query.

### 4.1 Message Sequence

```python
messages = [
    # 1. System prompt (set once at gateway init)
    # — injected by LLMGateway automatically

    # 2. Retrieved context (injected by orchestrator)
    {
        "role": "user",
        "content": format_context_message(retrieved_chunks)
    },

    # 3. The user's actual question
    {
        "role": "user",
        "content": user_question
    }
]
```

### 4.2 Context Formatting

```python
def format_context_message(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a context block for the LLM."""

    if not chunks:
        return (
            "<context>\n"
            "No relevant documents were found for this query.\n"
            "</context>"
        )

    parts = ["<context>"]
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"<source id=\"{i}\">")
        parts.append(f"  <title>{chunk.document_title}</title>")
        parts.append(f"  <url>{chunk.source_url}</url>")
        parts.append(f"  <type>{chunk.source_type}</type>")
        if chunk.section_id:
            parts.append(f"  <section>{chunk.section_id}</section>")
        if chunk.tax_year:
            parts.append(f"  <tax_year>{chunk.tax_year}</tax_year>")
        parts.append(f"  <content>\n{chunk.content}\n  </content>")
        parts.append(f"</source>")
    parts.append("</context>")

    return "\n".join(parts)
```

### 4.3 Why Two User Messages?

The context and the question are sent as separate user messages rather than
concatenated into one. This is intentional:

1. **Clarity for the LLM.** The model can clearly distinguish "here is reference
   material" from "here is what the user wants." Concatenation risks the LLM
   treating context content as part of the user's request.

2. **Token accounting.** Separating context makes it easier to measure how many
   tokens are spent on retrieval vs. the actual query.

3. **Provider compatibility.** Some providers handle multi-turn better than
   others. Two user messages in sequence work reliably across Gemini, Claude,
   and GPT-4 via LiteLLM.

An alternative is a single user message with `<context>` and `<question>` tags.
Both approaches work. The two-message approach is slightly cleaner for logging.

---

## 5. Orchestrator Engine Logic

### 5.1 Core Loop

```python
# src/orchestrator/engine.py — simplified

class QueryEngine:
    MAX_TOOL_ROUNDS = 3  # prevent infinite tool-call loops

    async def answer(self, question: str) -> AnswerResponse:
        # 1. Retrieve context
        chunks = await self.retriever.retrieve(question, top_k=8)

        # 2. Build messages
        messages = [
            {"role": "user", "content": format_context_message(chunks)},
            {"role": "user", "content": question},
        ]

        # 3. LLM completion loop (handles tool calls)
        tool_rounds = 0
        chunks_used = [c.id for c in chunks]

        while tool_rounds < self.MAX_TOOL_ROUNDS:
            response = await self.llm.complete(
                messages=messages,
                tools=self.tool_definitions,
            )

            message = response.choices[0].message

            # If no tool calls, we have the final answer
            if not message.tool_calls:
                break

            # Process tool calls
            messages.append(message.model_dump())
            for tool_call in message.tool_calls:
                result = await self.execute_tool(tool_call)

                # If it was a search, track the new chunks
                if tool_call.function.name == "search_tax_documents":
                    chunks_used.extend(
                        c.id for c in result.get("chunks", [])
                    )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                })

            tool_rounds += 1

        # 4. Build response
        return AnswerResponse(
            answer=message.content,
            model_used=response.model,
            chunks_used=chunks_used,
            tool_calls_made=tool_rounds,
        )
```

### 5.2 Tool Execution

```python
async def execute_tool(self, tool_call) -> dict:
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    match name:
        case "search_tax_documents":
            chunks = await self.retriever.retrieve(
                query=args["query"],
                top_k=5,
                source_type=args.get("source_type_filter"),
                tax_year=args.get("tax_year_filter"),
            )
            return {
                "chunks": [
                    {
                        "title": c.document_title,
                        "url": c.source_url,
                        "section": c.section_id,
                        "content": c.content,
                    }
                    for c in chunks
                ]
            }

        case "calculate_income_tax":
            result = self.tax_calculator.calculate(
                taxable_income=args["taxable_income"],
                tax_year=args.get("tax_year"),
            )
            return result.model_dump()

        case "calculate_paye":
            result = self.paye_calculator.calculate(
                gross_pay=args["gross_pay"],
                pay_frequency=args["pay_frequency"],
                tax_code=args["tax_code"],
                tax_year=args.get("tax_year"),
            )
            return result.model_dump()

        case "calculate_student_loan_repayment":
            result = self.student_loan_calculator.calculate(
                annual_income=args["annual_income"],
                tax_year=args.get("tax_year"),
            )
            return result.model_dump()

        case "calculate_acc_levy":
            result = self.acc_calculator.calculate(
                annual_income=args["annual_income"],
                tax_year=args.get("tax_year"),
            )
            return result.model_dump()

        case _:
            return {"error": f"Unknown tool: {name}"}
```

---

## 6. Tricky Cases and How the Prompt Handles Them

### 6.1 "How much tax do I pay on $85,000?"

**Expected behaviour:** The LLM calls `calculate_income_tax` with
`taxable_income=85000`. The tool returns a bracket breakdown. The LLM presents
the result in plain language with the breakdown, effective rate, and source
citation.

**Why the prompt handles this:** Hard rule 3 says "call the appropriate
calculator tool" and the `calculate_income_tax` tool description explicitly says
"Use this whenever a user asks 'how much tax do I pay on $X'."

### 6.2 "What's my take-home pay if I earn $75,000 with student loan?"

**Expected behaviour:** The LLM needs to call multiple tools: `calculate_paye`
(with tax code "M SL" or "SL"), `calculate_acc_levy`, and
`calculate_student_loan_repayment`. It may also need to ask about KiwiSaver
contribution rate. If it doesn't know the tax code, it should ask.

**Why the prompt handles this:** The tool descriptions cover each deduction type.
The response style section says to use specific numbers and examples. The LLM
should reason about which tools to call.

**Risk:** The LLM might not call all necessary tools. This is a known weakness
of tool-calling LLMs. Mitigation: evaluation test cases that check for multi-tool
scenarios. If this is a persistent problem, the orchestrator could pre-detect
"take-home pay" queries and hint the LLM about which tools are relevant.

### 6.3 "What was the top tax rate in 2020?"

**Expected behaviour:** The LLM should note the tax year (2020–21, which in NZ
context means 1 April 2020 to 31 March 2021), search for that year's brackets,
and answer from context. If the corpus only has current-year data, it should say
so.

**Why the prompt handles this:** The tax year rules section says to use prior-year
data if available, or say explicitly if it's not.

### 6.4 "Should I choose the M or ME tax code?"

**Expected behaviour:** The LLM should explain what each code means (from
retrieved context), describe the eligibility criteria for ME (KiwiSaver member),
and help the user understand which applies to them — without making the decision
for them.

**Why the prompt handles this:** The response style says to be helpful but the
disclaimer says to recommend professional advice for specific situations. This
is a case where the LLM can give factual guidance from the context.

### 6.5 "How do I set up a company for tax purposes?"

**Expected behaviour:** The LLM should decline and redirect. "That's outside what
I cover. I focus on personal income tax for NZ residents — things like PAYE, tax
credits, KiwiSaver, student loans, and individual tax returns. For company tax,
I'd suggest checking ird.govt.nz/income-tax/income-tax-for-businesses-and-organisations
or talking to a tax advisor."

**Why the prompt handles this:** Hard rule 5 covers out-of-scope topics
explicitly.

### 6.6 "I earn $50,000 salary and $15,000 from a rental property"

**Expected behaviour:** The LLM should recognise this involves multiple income
sources (employment + rental). For the salary portion, standard PAYE applies.
For rental income, the user likely needs to file an IR3. The LLM should explain
this from context, note that rental income is added to total taxable income for
marginal rate purposes, and suggest consulting a tax advisor given the
complexity.

**Why the prompt handles this:** The context instructions say to synthesise
multiple chunks. The response style says to add a disclaimer for complex
scenarios.

### 6.7 Empty or irrelevant context

**Expected behaviour:** If retrieval returns nothing useful, the LLM should say:
"I wasn't able to find specific information about [topic] in my sources. This
might be outside what I cover, or the information might not have been indexed
yet. I'd suggest checking ird.govt.nz directly or contacting IRD."

**Why the prompt handles this:** Hard rule 1 says don't guess. Hard rule 4 says
to explain what's missing and suggest alternatives.

---

## 7. Evaluation Scenarios

These should be used to build `tests/eval/test_scenarios.yaml`. Each scenario
has a question, expected behaviour, and what to check in the response.

### 7.1 Factual Accuracy

```yaml
- question: "What are the current income tax rates for individuals?"
  expects:
    - Contains all current bracket rates from context
    - Does NOT invent rates from LLM training data
    - Includes source citation (IRD tax rates page)
    - Mentions the tax year the rates apply to

- question: "What is the ACC earner's levy rate?"
  expects:
    - States the rate from context (not hallucinated)
    - Mentions the maximum liable income cap
    - Cites IRD or ACC as source

- question: "What is the student loan repayment threshold?"
  expects:
    - States the threshold from context
    - States the repayment rate (12%)
    - Cites source
```

### 7.2 Calculator Usage

```yaml
- question: "How much income tax would I pay on $95,000?"
  expects:
    - Calls calculate_income_tax tool
    - Presents bracket-by-bracket breakdown
    - Shows total tax and effective rate
    - Does NOT attempt manual arithmetic

- question: "What's my take-home pay on a $1,500 weekly wage with tax code M?"
  expects:
    - Calls calculate_paye tool
    - May also call calculate_acc_levy
    - Asks about KiwiSaver and student loan if relevant
```

### 7.3 Scope Boundaries

```yaml
- question: "How do I register for GST?"
  expects:
    - Declines clearly
    - States what the system does cover
    - Suggests ird.govt.nz for GST information

- question: "What is the company tax rate in NZ?"
  expects:
    - Declines clearly
    - Redirects to business tax resources

- question: "How do I set up a family trust for tax?"
  expects:
    - Declines clearly
    - Suggests professional advice
```

### 7.4 Tax Year Handling

```yaml
- question: "What was the top tax rate before the 39% bracket was introduced?"
  expects:
    - Recognises this is about a prior tax year
    - Either answers from context or states the data isn't available
    - Does not hallucinate historical rates

- question: "What tax rates apply from April?"
  expects:
    - Clarifies which April / which tax year if ambiguous
    - Or defaults to the upcoming year if context is clear
```

### 7.5 Ambiguity and Clarification

```yaml
- question: "How much tax do I pay?"
  expects:
    - Asks for the user's income amount
    - Does NOT assume a number

- question: "What tax code should I use?"
  expects:
    - Explains the main tax codes from context
    - Asks about the user's employment situation
    - Does NOT prescribe a code without knowing the situation
```

### 7.6 Citation Quality

```yaml
- question: "Am I eligible for the Independent Earner Tax Credit?"
  expects:
    - States eligibility criteria from context
    - States the credit amount from context
    - Every factual claim has a source reference
    - Source URLs are real IRD pages (not hallucinated)
```

### 7.7 Hallucination Resistance

```yaml
- question: "What is the tax rate for income between $50,000 and $70,000?"
  expects:
    - States the rate from context ONLY
    - If context doesn't contain this specific bracket, says so
    - Does NOT fill in from LLM parametric memory

- question: "What deductions can I claim as a PAYE employee?"
  expects:
    - Answers from context (limited deductions for PAYE employees)
    - Does NOT invent deductions that don't exist in NZ tax law
    - Notes that NZ has fewer individual deductions than some countries
```

---

## 8. Future Enhancements

### 8.1 Dynamic Few-Shot Examples

Instead of embedding examples in the system prompt (which become stale), maintain
a curated table of exemplary Q&A pairs. At query time, retrieve the 1–2 most
similar examples and inject them into the prompt as demonstrations. This gives
the LLM concrete patterns without the staleness risk.

### 8.2 Query Classification Pre-Processing

Before retrieval, classify the query into categories: factual lookup, calculation
request, eligibility check, procedural how-to, out-of-scope. This classification
can optimise both retrieval (e.g., filter to legislation for legal questions) and
tool selection (e.g., pre-wire calculator tools for calculation queries).

### 8.3 Conversation Memory

The current design is stateless (single question → answer). For multi-turn
conversations, the orchestrator would need to maintain a conversation history
and pass prior turns to the LLM. This also means re-retrieval might be needed
for follow-up questions that shift topic.

### 8.4 Confidence Scoring

Have the LLM self-assess its confidence on a scale. Low-confidence answers
get a stronger disclaimer and suggestion to verify. This requires prompt
engineering (e.g., "Before answering, assess how well the provided context
covers this question: HIGH / MEDIUM / LOW") and calibration through evaluation.