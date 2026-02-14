# taxtechnical.ird.govt.nz — Crawling Strategy for NZ Tax RAG

> Research date: 2026-02-14

## 1. Site Overview

`taxtechnical.ird.govt.nz` is IRD's **Tax Technical** site — the Commissioner's official interpretation of NZ tax law. It's distinct from the main `ird.govt.nz` guidance site. Content here is more detailed, legally authoritative, and aimed at tax professionals.

The site uses a **Coveo-powered search** backend with faceted filtering by publication type. Content is available as both HTML pages (at clean URL paths) and as downloadable PDFs (at media paths). The HTML pages are lightweight wrappers containing a summary, issue date, and link to the full PDF. **For RAG purposes, the PDFs contain the substantive content.**

---

## 2. URL Structure & Patterns

### 2.1 HTML Pages (clean URLs)

Publication type pages follow this pattern:

```
https://www.taxtechnical.ird.govt.nz/{publication-type}/{year}/{identifier}
```

| Publication Type | URL Path Segment | Example |
|---|---|---|
| Interpretation Statements | `/interpretation-statements/` | `/interpretation-statements/2024/is-24-10` |
| Questions We've Been Asked | `/questions-we-ve-been-asked/` | `/questions-we-ve-been-asked/2025/qb-25-11` |
| Operational Statements | `/operational-statements/` | `/operational-statements/os-1302-section-17-notices` |
| Fact Sheets | `/fact-sheets/` | `/fact-sheets/2024/is-24-10-fs-2` |
| Overviews | `/overviews/` | `/overviews/gifting` |
| Case Summaries | `/case-summaries/` | `/case-summaries/2026/csum-26-01` |
| Commissioner's Statements | `/commissioner-s-statements/` | `/commissioner-s-statements/2026/cs-26-01` |
| Determinations | `/determinations/` | `/determinations/emergency-events/2026/det-26-01` |
| Tax Information Bulletins | `/tib/` | `/tib/volume-37---2025/tib-vol37-no11` |
| New Legislation articles | `/new-legislation/act-articles/` | various nested paths |
| Interpretation Guidelines | (PDFs only, no clean URL path observed) | — |

### 2.2 PDF Paths (full content)

PDFs follow a media path pattern:

```
https://www.taxtechnical.ird.govt.nz/-/media/project/ir/tt/pdfs/{type}/{year-or-subdir}/{filename}.pdf
```

Examples:
- `/-/media/project/ir/tt/pdfs/interpretation-statements/2024/is-24-10.pdf`
- `/-/media/project/ir/tt/pdfs/questions-we-ve-been-asked/2025/qb-25-15.pdf`
- `/-/media/project/ir/tt/pdfs/tib/volume-37---2025/tib-vol37-no11.pdf`
- `/-/media/project/ir/tt/pdfs/operational-statements/2021/os-21-04.pdf`
- `/-/media/project/ir/tt/pdfs/interpretation-guidelines/ig1601.pdf`

### 2.3 TIB Volumes

Tax Information Bulletins are organised by volume (year) and number (month). Recent pattern:

```
/tib/volume-{vol}---{year}/tib-vol{vol}-no{num}
```

| Volume | Year | Issues |
|---|---|---|
| Vol 38 | 2026 | No 1 (Feb 2026) — current |
| Vol 37 | 2025 | No 1–11 (Feb–Dec 2025) |
| Vol 36 | 2024 | No 1–11 |

TIBs are *compilation documents* — each contains multiple items (new legislation commentary, interpretation statements, QWBAs, determinations, etc.). The individual items are also published as standalone HTML/PDF at their own URLs.

**Recommendation:** Ingest the standalone items (IS, QB, etc.) rather than the TIBs themselves, to avoid duplication. Use TIBs as an index to discover items, not as primary content.

---

## 3. Publication Types — Relevance to Personal Income Tax

### 3.1 HIGH PRIORITY — Ingest These

#### Interpretation Statements (IS)

The Commissioner's most authoritative published interpretation. These are detailed, legally reasoned, and often 20–100+ pages. Filter for personal income tax relevance.

**Recent high-relevance items:**

| ID | Title | Date | Relevance |
|---|---|---|---|
| IS 24/10 | Income tax – Share investments | Dec 2024 | Individual investors: dividends, share sales, FIF rules |
| IS 25/16 | Tax residence | May 2025 | Core: when are you an NZ tax resident? |
| IS 25/17 | Tax residence – government service rule | May 2025 | Supplement to IS 25/16 |
| IS 25/06 | Cash-settled employee share scheme | Mar 2025 | Employment income: ESS benefits |
| IS 25/08 | Implications of change of use of dwelling | Apr 2025 | Rental income, mixed-use assets |
| IS 25/18 | Money/property received from overseas | Sep 2025 | Foreign trusts, overseas gifts |
| IS 25/25 | Income tax – business activity | Dec 2025 | When is activity a "business"? |
| IS 23/11 | When gifts are assessable income | Dec 2023 | Personal income: gift taxation |
| IS 24/01 | Taxation of trusts | Feb 2024 | Trust income for individuals |

**Crawl rule:** `/interpretation-statements/{2020..2026}/*` — filter post-crawl by income tax relevance. Exclude GST-only, company-only, and international-only statements.

#### Questions We've Been Asked (QWBAs)

Already in Q&A format — ideal for RAG. The Tax Counsel Office answers specific questions with worked examples.

**Recent high-relevance items:**

| ID | Title | Date | Relevance |
|---|---|---|---|
| QB 25/01 | Rental income – renting a room to a flatmate | Apr 2025 | Individual rental income |
| QB 25/07 | Gift cards/products as trade rebates | May 2025 | Employment income, PAYE |
| QB 25/11 | Bright-line start date for 2-year test | May 2025 | Property sale income |
| QB 25/12 | Bright-line test – subdivided section | May 2025 | Property sale income |
| QB 25/15 | Rollover relief – transfers between associated persons | May 2025 | Property sale income |
| QB 18/13 | Tax treatment of allowances to farm workers | Jun 2018 | Employment income, PAYE |
| QB 18/02–05 | Insurance premiums paid by employers (series) | Feb 2018 | Employment income, PAYE, FBT |

**Crawl rule:** `/questions-we-ve-been-asked/{2018..2026}/*` — wider date range because QWBAs remain valid until superseded.

#### Fact Sheets

Short summaries of longer items — excellent for RAG retrieval due to conciseness.

**Crawl rule:** `/fact-sheets/{2020..2026}/*`

#### Overviews

Topic-level index pages that link to all relevant technical guidance on a subject. Useful both as content and as a discovery mechanism.

**Crawl rule:** `/overviews/*`

### 3.2 MEDIUM PRIORITY — Ingest Selectively

#### New Legislation Commentary

Commentary on legislative changes, published inside TIBs. Particularly important for:
- Tax rate/threshold changes (Budget 2024: personal thresholds from Jul 2024)
- KiwiSaver changes (Budget 2025)
- FamilyBoost introduction
- Bright-line test changes (Jul 2024)

**Strategy:** Don't crawl the full `/new-legislation/` tree (it contains all legislation going back decades). Instead, ingest only TIB new-legislation articles from 2024 onwards that relate to personal income tax changes.

#### Operational Statements (OS)

Commissioner's operational approach. Some are relevant to individuals:
- OS 18/01: Kilometre rates for motor vehicle use (deductions)
- OS 21/04: Non-resident employer PAYE obligations

**Crawl rule:** Cherry-pick specific OS items rather than crawl all. Most are administrative/procedural.

#### Interpretation Guidelines (IG)

Only a few exist. Key one:
- IG 16/01: Employee or independent contractor? (determining employment status for tax)

**Crawl rule:** Specific items only (there are very few).

### 3.3 LOW PRIORITY — Probably Skip

| Type | Reason to Skip |
|---|---|
| Case Summaries | Useful for context but not for answering typical tax questions |
| Commissioner's Statements | Mostly operational/procedural |
| Determinations | Mostly FIF/FDR determinations for specific funds, depreciation rates, livestock values — not personal income tax |
| Revenue Alerts | Tax avoidance warnings — niche |
| Binding Rulings | Entity-specific (BR Prd = private, BR Pub = public). Some public rulings relevant but very detailed |
| PIB Reviews | Historical — superseded by modern guidance |

---

## 4. Recommended Crawl Configuration

### 4.1 Seed URLs — Crawl Targets

```yaml
# config/sources_taxtechnical.yaml

taxtechnical:
  base_url: "https://www.taxtechnical.ird.govt.nz"
  
  # Strategy: Crawl HTML index pages to discover items, 
  # then download the linked PDFs for full content.
  
  crawl_paths:
    # HIGH PRIORITY
    - path: "/interpretation-statements/"
      year_range: [2020, 2026]
      content_filter: "income_tax_individual"  # post-crawl filter
      
    - path: "/questions-we-ve-been-asked/"
      year_range: [2018, 2026]
      content_filter: "income_tax_individual"
      
    - path: "/fact-sheets/"
      year_range: [2020, 2026]
      
    - path: "/overviews/"
      # No year filter — these are evergreen index pages
    
    # MEDIUM PRIORITY  
    - path: "/operational-statements/"
      # Cherry-pick list rather than full crawl
      specific_items:
        - "os-1801"   # kilometre rates
        - "2021/os-21-04"  # non-resident employer PAYE
    
    # TIBs — use as discovery index only
    - path: "/tib/"
      volumes: ["volume-36---2024", "volume-37---2025", "volume-38---2026"]
      extract: "new_legislation_commentary_only"
  
  # Rate limiting
  rate_limit: "1req/sec"
  respect_robots: true
  
  # PDF download
  download_pdfs: true
  pdf_base_path: "/-/media/project/ir/tt/pdfs/"
```

### 4.2 Content Filtering Rules

Not all interpretation statements are relevant to personal income tax. Apply these filters post-crawl to decide what to ingest:

**INCLUDE if title or content matches ANY of:**
- "income tax" + ("individual" | "employee" | "employment" | "personal" | "salary" | "wages" | "PAYE")
- "tax residence" | "tax resident"
- "share investments" | "FIF" | "foreign investment fund" (individual context)
- "rental income" | "bright-line" | "property" (individual context)
- "KiwiSaver" | "student loan" | "Working for Families" | "FamilyBoost"
- "donation" | "tax credit" | "IETC"
- "employment status" | "employee or independent contractor"
- "ACC" | "earner's levy"
- "PIE" | "prescribed investor rate" | "RWT"
- "gift" + "income" (individual context)
- "insurance" + "employer" + "PAYE"
- sections CE, CW, CB 6–6A, Part L, Part M, Part R, Schedule 1

**EXCLUDE if title or content matches ALL of:**
- "GST" only (no income tax angle)
- "company" | "corporate" only (no individual angle)  
- "trust" only (no individual beneficiary angle)
- "charity" | "donee organisation" only
- "FDR determination" for specific funds (these are entity-specific)
- "depreciation determination" (asset-specific)
- "binding ruling" (entity-specific, unless public and relevant)
- "international" only (DTAs, transfer pricing, CFC rules)

### 4.3 Freshness & Re-crawl Strategy

| Content Type | Re-crawl Frequency | Rationale |
|---|---|---|
| Interpretation Statements | Monthly | New ones published ~monthly |
| QWBAs | Monthly | New ones published ~monthly |
| Fact Sheets | Monthly | Tied to IS/QB publications |
| Overviews | Quarterly | Updated infrequently |
| TIBs | Monthly | New volume each month |
| New Legislation | After Budget / new Act | Event-driven |

**Change detection:** Compare content hash of HTML page. If changed, re-download PDF and re-ingest.

---

## 5. Chunking Strategy for Tax Technical Content

### 5.1 Interpretation Statements (PDFs, 20–100+ pages)

These have a standard structure:
1. Summary (1–2 pages)
2. Introduction / scope
3. Analysis (bulk of content, with numbered paragraphs)
4. Examples (worked scenarios)
5. Appendix (legislative provisions)

**Chunking approach:**
- **Summary** → standalone chunk (very high retrieval value)
- **Analysis** → chunk by numbered paragraph groups, respecting section headings. Prepend the IS identifier + section heading to each chunk.
- **Examples** → each example is a standalone chunk, tagged as `type: example`
- **Appendix** → skip (raw legislation text, better sourced from legislation.govt.nz)

### 5.2 QWBAs (PDFs, 5–30 pages)

Structure:
1. Question (1 paragraph)
2. Answer (1–2 paragraphs)
3. Explanation/Analysis
4. Examples

**Chunking approach:**
- **Question + Answer** → one chunk (the money chunk — this is what RAG will retrieve)
- **Explanation** → chunk by section heading
- **Examples** → each example is a standalone chunk

### 5.3 Fact Sheets (PDFs, 2–10 pages)

Short enough to be a single chunk in most cases. If >1500 tokens, split at section boundaries.

### 5.4 TIB New Legislation Commentary

Chunk by article boundary (each article covers one legislative change). Prepend the Act name and section reference.

---

## 6. Metadata Enrichment

For each ingested item, extract and store:

```python
@dataclass
class TaxTechnicalMetadata:
    # Standard fields
    source_url: str               # HTML page URL
    pdf_url: str                  # Direct PDF URL  
    source_type: str              # "interpretation_statement" | "qwba" | "fact_sheet" | etc.
    document_title: str
    identifier: str               # "IS 24/10" | "QB 25/01" | etc.
    issue_date: date
    last_crawled: datetime
    
    # Tax-specific fields
    tax_type: str                 # "income_tax" | "gst" | "mixed"
    applicable_audience: str      # "individual" | "employer" | "business" | "general"
    legislation_refs: list[str]   # ["s CE 1", "s CW 17", "Part L"]
    supersedes: list[str]         # IDs of items this replaces
    superseded_by: str | None     # ID if this item has been replaced
    related_items: list[str]      # IDs of related publications
    tib_reference: str | None     # "Vol 37 No 1, February 2025"
    
    # Content classification
    topics: list[str]             # ["employment_income", "PAYE", "allowances"]
    tax_years_applicable: list[str]  # ["2024-25", "2025-26"]
```

---

## 7. Key Observations for the RAG System

### 7.1 Superseded Content Is a Real Risk

Tax technical items are sometimes replaced by newer versions. For example:
- QB 18/16 (bright-line, subdivided section) → replaced by QB 25/12 (for disposals from Jul 2024)
- QB 15/09 (insurance premiums) → replaced by QB 18/04

**The system must track supersession.** Each item's HTML page states what it replaces ("This QWBA replaces..."). The crawler should extract this and store it as metadata. During retrieval, superseded items should be deprioritised or excluded.

### 7.2 QWBAs Are RAG Gold

The Question + Answer format maps perfectly to semantic retrieval. A user asking "Can I claim deductions for renting a room to a flatmate?" will get a near-perfect semantic match on QB 25/01's question text. The design doc should call these out as priority content.

### 7.3 Fact Sheets Fill a Gap

For very long ISs (e.g., IS 24/10 on share investments at 48 pages), the fact sheets provide a concise version that's much better for RAG retrieval. Ingest both, but the fact sheet will often be the better retrieval target.

### 7.4 The Publications Search Page Uses Coveo

The `/publications` page loads results via Coveo search API (JavaScript-rendered). A traditional HTTP crawler won't see the publication list. Two options:
1. **Use Coveo API directly** — the search endpoint is accessible and supports filtering by publication type and date
2. **Maintain a manual seed list** — curate URLs of relevant items (more reliable, less automated)

**Recommendation:** Use approach (1) for discovery, then crawl the discovered URLs. The Coveo endpoint returns structured JSON with titles, dates, types, and URLs — ideal for building the seed list programmatically.

### 7.5 PDF vs HTML

The HTML pages are thin wrappers. The real content is in the PDFs. For RAG ingestion:
- Crawl HTML pages for **metadata** (title, date, type, related items, supersession info)
- Download PDFs for **content** (the actual analysis, examples, and guidance)

---

## 8. Estimated Corpus Size

| Content Type | Estimated Count (relevant) | Avg Pages | Estimated Chunks |
|---|---|---|---|
| Interpretation Statements | ~30 relevant (of ~200 total) | 30 | ~600 |
| QWBAs | ~40 relevant (of ~150 total) | 10 | ~300 |
| Fact Sheets | ~20 | 4 | ~60 |
| Overviews | ~5 | 2 | ~15 |
| New Legislation Commentary | ~15 articles | 5 | ~60 |
| Operational Statements | ~3 | 15 | ~30 |
| **Total** | **~113 items** | — | **~1,065 chunks** |

This is manageable and would add approximately 1,000 chunks to the RAG corpus — roughly 20% of the total estimated 5K chunks across all sources.

---

## 9. Implementation Priority

1. **Phase 1a:** Crawl all QWBAs from 2020–2026, filter for income tax relevance (~40 items). These are the highest-value RAG content.
2. **Phase 1b:** Crawl Fact Sheets from 2020–2026 (~20 items).
3. **Phase 1c:** Crawl Interpretation Statements from 2020–2026, filter for relevance (~30 items).
4. **Phase 2:** Crawl Overviews and selected Operational Statements.
5. **Phase 2:** Crawl TIB new legislation commentary for 2024–2026.
6. **Ongoing:** Monthly re-crawl of all paths to pick up new publications.