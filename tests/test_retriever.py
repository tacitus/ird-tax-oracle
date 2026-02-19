"""Tests for RRF fusion logic and HybridRetriever.search()."""

from unittest.mock import AsyncMock, call

import pytest

from src.db.models import RetrievalResult
from src.rag.retriever import HybridRetriever, rrf_fuse

_RRF_K = 60


def _make_result(content: str, url: str = "https://ird.govt.nz/a") -> RetrievalResult:
    return RetrievalResult(
        content=content,
        section_title=None,
        source_url=url,
        source_title="Test",
        score=0.0,
    )


def test_rrf_fuse_single_list() -> None:
    """Items only in one list get scored by their rank."""
    semantic = [_make_result("chunk A"), _make_result("chunk B")]
    keyword: list[RetrievalResult] = []

    results = rrf_fuse(semantic, keyword, top_k=2)

    assert len(results) == 2
    assert results[0].content == "chunk A"
    assert results[1].content == "chunk B"
    # rank 0 => 1/(60+1), rank 1 => 1/(60+2)
    assert results[0].score > results[1].score


def test_rrf_fuse_overlap_boosts_rank() -> None:
    """A chunk appearing in both lists gets a higher combined score."""
    shared = _make_result("shared chunk")
    only_semantic = _make_result("only semantic", url="https://ird.govt.nz/b")

    semantic = [only_semantic, shared]  # shared is rank 1
    keyword = [shared]  # shared is rank 0

    results = rrf_fuse(semantic, keyword, top_k=2)

    # shared should be ranked first because it appears in both lists
    assert results[0].content == "shared chunk"
    # Verify combined score: 1/(60+2) + 1/(60+1) > 1/(60+1)
    expected_shared = 1.0 / (_RRF_K + 2) + 1.0 / (_RRF_K + 1)
    expected_only = 1.0 / (_RRF_K + 1)
    assert abs(results[0].score - expected_shared) < 1e-9
    assert abs(results[1].score - expected_only) < 1e-9


def test_rrf_fuse_respects_top_k() -> None:
    """Only top_k results are returned."""
    items = [_make_result(f"chunk {i}", url=f"https://ird.govt.nz/{i}") for i in range(10)]
    results = rrf_fuse(items, [], top_k=3)
    assert len(results) == 3


def test_rrf_fuse_empty_lists() -> None:
    """Empty input lists return empty results."""
    results = rrf_fuse([], [], top_k=5)
    assert results == []


# --- HybridRetriever.search() tests ---


def _make_db_row(
    content: str = "Tax info",
    source_url: str = "https://ird.govt.nz/a",
    distance: float = 0.2,
    rank: float = 0.8,
) -> dict:  # type: ignore[type-arg]
    """Build a dict matching asyncpg Row for semantic/keyword queries."""
    return {
        "content": content,
        "section_title": "Section",
        "tax_year": None,
        "source_url": source_url,
        "source_title": "Test Doc",
        "source_type": "ird_guidance",
        "distance": distance,
        "rank": rank,
    }


@pytest.mark.asyncio
async def test_search_calls_embed_and_both_searches(
    mock_embedder: AsyncMock, mock_db_pool: AsyncMock
) -> None:
    """search() calls embedder and runs both semantic + keyword queries."""
    retriever = HybridRetriever(mock_db_pool, mock_embedder)
    await retriever.search("PAYE rates")

    mock_embedder.embed_query.assert_awaited_once_with("PAYE rates")
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    assert conn.fetch.await_count == 2


@pytest.mark.asyncio
async def test_search_returns_fused_results(
    mock_embedder: AsyncMock, mock_db_pool: AsyncMock
) -> None:
    """Results from both queries are fused via RRF."""
    semantic_row = _make_db_row(content="Semantic hit", source_url="https://ird.govt.nz/s")
    keyword_row = _make_db_row(content="Keyword hit", source_url="https://ird.govt.nz/k")

    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetch.side_effect = [[semantic_row], [keyword_row]]

    retriever = HybridRetriever(mock_db_pool, mock_embedder)
    results = await retriever.search("test query", top_k=5)

    assert len(results) == 2
    contents = {r.content for r in results}
    assert "Semantic hit" in contents
    assert "Keyword hit" in contents


@pytest.mark.asyncio
async def test_search_empty_results(
    mock_embedder: AsyncMock, mock_db_pool: AsyncMock
) -> None:
    """No hits from either query returns empty list."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetch.side_effect = [[], []]

    retriever = HybridRetriever(mock_db_pool, mock_embedder)
    results = await retriever.search("obscure query")

    assert results == []


# --- Filter passthrough tests ---


def _str_args(fetch_call: call) -> list[str]:
    """Extract string positional args from a conn.fetch call (skip numpy arrays)."""
    return [a for a in fetch_call[0] if isinstance(a, str)]


@pytest.mark.asyncio
async def test_search_with_source_type_filter(
    mock_embedder: AsyncMock, mock_db_pool: AsyncMock
) -> None:
    """source_type filter is passed through to SQL queries."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetch.side_effect = [[], []]

    retriever = HybridRetriever(mock_db_pool, mock_embedder)
    await retriever.search("PAYE rates", source_type="legislation")

    for fetch_call in conn.fetch.call_args_list:
        sql = fetch_call[0][0]
        str_params = _str_args(fetch_call)
        assert "s.source_type = $3" in sql
        assert "legislation" in str_params


@pytest.mark.asyncio
async def test_search_with_tax_year_filter(
    mock_embedder: AsyncMock, mock_db_pool: AsyncMock
) -> None:
    """tax_year filter is passed through to SQL queries."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetch.side_effect = [[], []]

    retriever = HybridRetriever(mock_db_pool, mock_embedder)
    await retriever.search("tax brackets", tax_year="2025-26")

    for fetch_call in conn.fetch.call_args_list:
        sql = fetch_call[0][0]
        str_params = _str_args(fetch_call)
        assert "c.tax_year = $3" in sql
        assert "2025-26" in str_params


@pytest.mark.asyncio
async def test_search_with_both_filters(
    mock_embedder: AsyncMock, mock_db_pool: AsyncMock
) -> None:
    """Both filters are passed through with correct parameter numbering."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetch.side_effect = [[], []]

    retriever = HybridRetriever(mock_db_pool, mock_embedder)
    await retriever.search("rates", source_type="ird_guidance", tax_year="2024-25")

    for fetch_call in conn.fetch.call_args_list:
        sql = fetch_call[0][0]
        str_params = _str_args(fetch_call)
        assert "s.source_type = $3" in sql
        assert "c.tax_year = $4" in sql
        assert "ird_guidance" in str_params
        assert "2024-25" in str_params


@pytest.mark.asyncio
async def test_search_without_filters_no_extra_params(
    mock_embedder: AsyncMock, mock_db_pool: AsyncMock
) -> None:
    """Without filters, SQL has no extra $3/$4 params."""
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetch.side_effect = [[], []]

    retriever = HybridRetriever(mock_db_pool, mock_embedder)
    await retriever.search("basic query")

    for fetch_call in conn.fetch.call_args_list:
        args = fetch_call[0]
        sql = args[0]
        assert "$3" not in sql
        assert "$4" not in sql
