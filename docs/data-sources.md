# NZ Personal Income Tax RAG — Data Sources Research

> Research date: 2026-02-14
> Purpose: Identify, validate and prioritise the best sources of information for the NZ personal income tax RAG system.

---

## Summary of Findings

The design doc's existing source list is a solid foundation but has some **significant gaps**. My research identified several additional high-value sources that should be added, and one source that needs to be **promoted from Tier 2 to Tier 1** given its importance for deterministic calculations.

### Key additions not in the current design:

1. **IRD Payroll Calculations & Business Rules Specification** — this is the *single most authoritative source* for PAYE, ACC, KiwiSaver, and student loan calculation rules. It's a machine-readable specification updated annually. This should be Tier 0.
2. **IRD Working for Families section** — a whole separate section of ird.govt.nz, not under `/income-tax/`
3. **IRD KiwiSaver section** — same, separate section with recent major changes (Budget 2025)
4. **IRD Student Loans section** — separate section with repayment thresholds, rates
5. **ACC Levy Guidebooks** — the official source for earners' levy rates, published annually by ACC (not IRD)
6. **Budget announcements and recent amendment Acts** — critical for staying current, especially given the significant KiwiSaver changes from Budget 2025
7. **Student Loan Scheme Act 2011** and **KiwiSaver Act 2006** — relevant legislation beyond just the Income Tax Act
8. **FamilyBoost** — the new childcare tax credit, not mentioned in scope but relevant to families

---

## Tier 0 — Structured/Machine-Readable Data (highest priority for calculators)

These are structured specifications that should be ingested first because they power the *deterministic calculation* tools. Errors in these sources directly produce wrong numbers.

| Source | URL | Format | Why Critical |
|--------|-----|--------|-------------|
| **IRD Payroll Calculations & Business Rules Specification** | `ird.govt.nz/digital-service-providers/services-catalogue/returns-and-information/payday-filing/payroll-calculations-and-business-rules` | PDF (annual) | **THE canonical spec** for PAYE tax codes, rates, thresholds, ACC levy, KiwiSaver deduction rules, student loan repayment calculations, ESCT. Updated each April. This is what payroll software vendors implement against. |
| **PAYE Deduction Tables (IR340, IR341)** | `ird.govt.nz/-/media/project/ir/home/documents/forms-and-guides/ir300---ir399/ir340/ir340-2025.pdf` | PDF (annual) | Weekly/fortnightly and 4-weekly/monthly PAYE tables. Contains the actual lookup tables with ACC levy baked in. Good cross-reference for validating calculator output. |
| **Working for Families Weekly Payments Chart (IR271)** | `ird.govt.nz/-/media/project/ir/home/documents/forms-and-guides/ir200---ir299/ir271/ir271-2026.pdf` | PDF (annual) | FTC and IWTC payment amounts by income band and number of children. Essential for WfF calculations. |

### Why this matters
The current design doc mentions "Tax calculators — Pure Python, deterministic, tool-callable" as Phase 2, but doesn't identify *where the numbers come from*. The Payroll Calculations spec is the answer. Without it, you're scraping rates from HTML guidance pages and hoping they're complete — they're not. The spec has edge cases (extra pays, mid-year rate changes, rounding rules) that the guidance pages omit.

---

## Tier 1 — Primary Guidance (ingest first for RAG)

### 1A. IRD Income Tax for Individuals (existing in design — confirmed correct)

| Source | URL Pattern | Content | Notes |
|--------|------------|---------|-------|
| Income tax for individuals (main hub) | `ird.govt.nz/income-tax/income-tax-for-individuals/*` | HTML | Tax rates, tax codes, income types, expenses, credits, end-of-year process. The primary "explainer" content. |
| Tax codes and rates | `ird.govt.nz/income-tax/income-tax-for-individuals/tax-codes-and-tax-rates-for-individuals/*` | HTML | Tax brackets, secondary tax codes, tailored tax codes. |
| Types of individual income | `ird.govt.nz/income-tax/income-tax-for-individuals/types-of-individual-income/*` | HTML | Employment, self-employment, overseas income, PIE income, interest, dividends, rental, schedular payments. |
| Individual tax credits | `ird.govt.nz/income-tax/income-tax-for-individuals/individual-tax-credits/*` | HTML | IETC, donation tax credits. |
| Resident Withholding Tax (RWT) | `ird.govt.nz/income-tax/withholding-taxes/resident-withholding-tax-rwt` | HTML | RWT rates, non-declaration rate (45%), how investment income is taxed. |

### 1B. IRD Working for Families (NOT currently in design — should be added)

| Source | URL Pattern | Content | Notes |
|--------|------------|---------|-------|
| Working for Families hub | `ird.govt.nz/working-for-families/*` | HTML | Eligibility, payment types (FTC, IWTC, Best Start, Minimum FTC), abatement rules, registration. This is a **separate major section** of the IRD website, not under `/income-tax/`. |
| Payment types | `ird.govt.nz/working-for-families/types` | HTML | Detailed breakdown of FTC, IWTC, Best Start Tax Credit, Minimum FTC. |
| Estimate your entitlement | `ird.govt.nz/working-for-families/estimate-your-entitlement` | HTML | Contains links to the IR271 chart and the online calculator. |

**Important note:** Budget 2025 announced changes to WfF abatement thresholds and rates, and income-testing of Year 1 Best Start, effective from 1 April 2026. These changes are still being legislated. The RAG system needs to track this.

### 1C. IRD KiwiSaver (NOT currently in design — should be added)

| Source | URL Pattern | Content | Notes |
|--------|------------|---------|-------|
| KiwiSaver hub | `ird.govt.nz/kiwisaver/*` | HTML | Contribution rates, employer contributions, government contributions, ESCT, withdrawal rules. |
| KiwiSaver changes page | `ird.govt.nz/kiwisaver-changes` | HTML | **Critical** — documents the Budget 2025 changes: default rate rising to 3.5% (Apr 2026), then 4% (Apr 2028); government contribution halved; $180K income cap; 16-17 year old eligibility. |

### 1D. IRD Student Loans (NOT currently in design — should be added)

| Source | URL Pattern | Content | Notes |
|--------|------------|---------|-------|
| Student loans hub | `ird.govt.nz/student-loans/*` | HTML | Repayment thresholds, repayment rates (12% above threshold), interest rates, overseas-based borrower rules. |
| Repaying your student loan | `ird.govt.nz/student-loans/repaying-your-student-loan/*` | HTML | NZ-based vs overseas-based repayment obligations, salary/wage deductions, self-employed repayments. |

### 1E. IRD PIE / Investment Income (partially in design — needs expansion)

| Source | URL Pattern | Content | Notes |
|--------|------------|---------|-------|
| PIE income for individuals | `ird.govt.nz/income-tax/income-tax-for-individuals/types-of-individual-income/portfolio-investment-entity-income-for-individuals/*` | HTML | PIR determination (10.5%, 17.5%, 28%), how to choose your PIR, KiwiSaver as a PIE. |
| Find your PIR | `ird.govt.nz/.../prescribed-investor-rates/find-my-prescribed-investor-rate` | HTML | Step-by-step PIR determination based on prior 2 years' income. |
| PIE guide (IR860) | `ird.govt.nz/-/media/.../ir860.pdf` | PDF | Comprehensive PIE guide — more detail than needed for individuals but useful for edge cases. |

### 1F. IRD Forms & Guides (existing in design — confirmed, with specific high-value items)

| Document | ID | Content | Priority |
|----------|----|---------|----------|
| Individual income tax return guide | IR3G (annual) | The definitive guide for filing IR3 returns. Question-by-question walkthrough. | **Highest** |
| Tax code declaration | IR330 | How to choose your tax code (M, ME, S, SH, SL, etc.) | High |
| Tax rate notification for contractors | IR330C | Schedular payment tax rates | Medium |
| Foreign Income Guide | IR1247 | For NZ tax residents with overseas income | Medium |
| PIE guide | IR860 | Comprehensive PIE rules | Medium |
| Overseas pensions guide | IR257 | Foreign superannuation | Low |

### 1G. Tax Technical (existing in design — confirmed correct)

| Source | URL Pattern | Content | Notes |
|--------|------------|---------|-------|
| Interpretation Statements | `taxtechnical.ird.govt.nz/interpretation-statements/*` | HTML | Commissioner's view on specific tax issues. Filter to income-tax-relevant ones. Some are very long. |
| Tax Information Bulletins | `taxtechnical.ird.govt.nz/tib/*` | HTML/PDF | Monthly compilations of new rulings, determinations, legislative commentary. Vol 38 No 1 (Feb 2026) is current. |
| Questions We've Been Asked (QWBAs) | `taxtechnical.ird.govt.nz/questions-we-ve-been-asked/*` | HTML | Practical Q&A format — very RAG-friendly content. |
| Standard Practice Statements | `taxtechnical.ird.govt.nz/standard-practice-statements/*` | HTML | Commissioner's operational procedures. |

**Note:** The design doc lists TIBs but misses QWBAs and Standard Practice Statements. QWBAs in particular are excellent RAG content because they're already in Q&A format.

---

## Tier 2 — Legislation (ingest selectively)

### 2A. Income Tax Act 2007 (existing in design — confirmed, with refinements)

| Part | Content | Relevance |
|------|---------|-----------|
| Part B | Core obligations — income tax liability | Core |
| Part C, subparts CA, CB, CE | Income — general, business, employment | Core |
| Part D | Deductions | Core |
| Part L, subparts LA–LJ | Tax credits (including IETC, donation credits) | Core |
| Part M, subparts MA–MF | Tax credits for families (Working for Families) | Core |
| Part M, subpart MH | FamilyBoost | New — not in design |
| Part M, subpart MK | KiwiSaver tax credits | Core |
| Part R | General collection rules (PAYE, RWT) | Core |
| Schedule 1 | Tax rates | Core |
| Schedule 2 | ACC earner's levy rates | Core |
| Part Y, section YA 1 | Definitions | Reference |

**Warning from design doc (confirmed correct):** The Income Tax Act 2007 is enormous. Do NOT try to ingest the whole thing. The above parts are sufficient for personal income tax.

URL: `legislation.govt.nz/act/public/2007/0097/latest/*`

### 2B. Tax Administration Act 1994 (existing in design — confirmed)

Selected parts relevant to individual taxpayers (filing obligations, penalties, disputes).

URL: `legislation.govt.nz/act/public/1994/0166/latest/*`

### 2C. Student Loan Scheme Act 2011 (NOT in design — should be added)

Repayment thresholds, rates, overseas-based borrower obligations. Relevant selected sections.

URL: `legislation.govt.nz/act/public/2011/0062/latest/*`

### 2D. KiwiSaver Act 2006 (NOT in design — should be added)

Contribution rates, employer obligations, government contributions, opt-out rules. Especially important given the Budget 2025 changes.

URL: `legislation.govt.nz/act/public/2006/0040/latest/*`

### 2E. Recent Amendment Acts (NOT in design — should be added)

These are critical for staying current. Key recent ones:

| Act | Content |
|-----|---------|
| Income Tax (FamilyBoost) Amendment Act 2025 | New childcare tax credit |
| Taxation (Budget Measures) Act 2025 | Investment boost, KiwiSaver changes |
| Taxation (Budget Measures) Act 2024 | Tax rate changes effective Jul 2024 and Apr 2025 |
| Taxation (Annual Rates for 2024–25, Emergency Response, and Remedial Matters) Act 2025 | Various remedial measures |
| Taxation (Annual Rates for 2025–26, Compliance Simplification, and Remedial Matters) Bill | Currently before Parliament |

---

## Tier 3 — External/Secondary Sources

### 3A. ACC (NOT in design — should be added)

| Source | URL | Content | Notes |
|--------|-----|---------|-------|
| ACC Levy Guidebook (annual) | `acc.co.nz/assets/business/Levy-Guidebook-2025-2026.pdf` | PDF | Official ACC levy rates, maximum liable earnings, classification units. The earners' levy rate comes from ACC, not IRD. |
| ACC levies overview | `acc.co.nz/for-business/understanding-levies-if-you-work-or-own-a-business` | HTML | Explains earners' levy (flat rate for all workers), work levy (industry-specific), working safer levy. |
| Levy changes | `acc.co.nz/for-business/received-an-invoice/levy-changes-for-businesses` | HTML | Upcoming changes to levy system. |

**Key data point:** The earners' levy is set by ACC, not IRD. For 2025-26 it's 1.67% (GST inclusive) up to $152,790. For 2026-27, it's increasing and the max liable earnings rises to $156,641. The IRD Payroll Calculations spec includes the ACC levy, but the ACC guidebook is the authoritative source for the rate itself.

### 3B. Tax Policy (existing in design — confirmed, low priority)

| Source | URL | Content |
|--------|-----|---------|
| Tax policy site | `taxpolicy.ird.govt.nz/*` | Discussion documents, RIS documents, Budget policy announcements. Useful for understanding *why* rules exist and what's changing, but not for current rules. |

### 3C. Budget Documents (NOT in design — useful for "what's changing")

| Source | URL | Content |
|--------|-----|---------|
| Budget.govt.nz | `budget.govt.nz/budget/2025/*` | Budget announcements including KiwiSaver factsheets. Useful when users ask "what's changing?" |

---

## Sources I Considered but Recommend Against Ingesting

| Source | Why Not |
|--------|---------|
| Third-party tax calculators (calculate.co.nz, paycalculator.co.nz, etc.) | Not authoritative. Could contain errors. Use for validation only. |
| KPMG/EY/Deloitte tax summaries | Good for context but potentially misleading if they simplify incorrectly. Copyright issues. |
| Immigration NZ tax guidance | Too high-level, already covered by IRD's own pages. |
| NZ Law Society/CA ANZ publications | Behind paywalls, copyright concerns. |
| Entire Income Tax Act 2007 | Way too large. Selective ingestion per the design doc is correct. |
| Historical TIBs (pre-2020) | Likely to contain superseded information. Focus on recent 3-5 years. |

---

## Observations and Recommendations

### 1. The Payroll Calculations Spec is your most important source
The IRD publishes an annual "Payroll Calculations and Business Rules Specification" PDF that is the **machine-readable specification** for PAYE, ACC levy, KiwiSaver, and student loan deductions. This is what all payroll software in NZ implements against. It contains exact formulas, rounding rules, edge cases for extra pays, and worked examples. This should be Tier 0, and the deterministic calculators should be implemented directly from this spec.

### 2. Budget 2025 creates time-sensitivity
Major KiwiSaver changes are being phased in: 3.5% default from April 2026, 4% from April 2028. Government contribution halved from July 2025. These are actively being legislated and some details may shift. The RAG system needs to handle "what are the current rules" vs "what's changing" clearly.

### 3. WfF, KiwiSaver, and Student Loans are separate IRD website sections
The current design only lists `ird.govt.nz/income-tax/income-tax-for-individuals/*` but three major topics that are in-scope live under different URL paths: `/working-for-families/`, `/kiwisaver/`, and `/student-loans/`. The crawler configuration needs to include these.

### 4. The ACC earners' levy comes from ACC, not IRD
While IRD publishes the levy rate in its payroll spec, the authoritative source for the rate is ACC itself. The ACC Levy Guidebook (annual PDF) should be ingested.

### 5. QWBAs are excellent RAG content
"Questions We've Been Asked" on taxtechnical.ird.govt.nz are already in Q&A format with detailed explanations. They're ideal for RAG retrieval and the design doc doesn't mention them specifically.

### 6. FamilyBoost is a gap in the scope
The Income Tax (FamilyBoost) Amendment Act 2025 introduced a new childcare tax credit. It's administered by IRD, applies to families with young children, and is income-tested. It's arguably in-scope for a personal income tax system but isn't mentioned in the design doc.

### 7. Re-crawl frequency should vary by source type
- IRD guidance pages: Monthly (as in design doc)
- Payroll Calculations Spec: Check annually (new version each April)
- ACC Levy Guidebook: Check annually (new version each April)
- Legislation: Check quarterly (amendments happen at irregular intervals)
- Budget announcements: Manual trigger (as in design doc)
- Tax Technical (TIBs, QWBAs): Monthly (new items published regularly)
