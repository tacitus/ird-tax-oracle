"""Tests for RRF fusion logic in the hybrid retriever."""

from src.db.models import RetrievalResult
from src.rag.retriever import rrf_fuse

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
