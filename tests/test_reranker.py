"""Tests for the cross-encoder reranker."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest

from src.db.models import RetrievalResult
from src.rag.reranker import CrossEncoderReranker


def _make_result(content: str, score: float = 0.5) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=uuid4(),
        content=content,
        section_title=None,
        source_url=f"https://ird.govt.nz/{content[:5]}",
        source_title="Test",
        score=score,
    )


@pytest.fixture
def mock_cross_encoder() -> MagicMock:
    """Mock CrossEncoder that returns controllable scores."""
    mock = MagicMock()
    return mock


@pytest.fixture
def reranker(mock_cross_encoder: MagicMock) -> CrossEncoderReranker:
    """CrossEncoderReranker with a mocked model."""
    with patch("src.rag.reranker.CrossEncoder", return_value=mock_cross_encoder):
        rr = CrossEncoderReranker()
    return rr


def test_rerank_reorders_by_score(
    reranker: CrossEncoderReranker,
    mock_cross_encoder: MagicMock,
) -> None:
    """Results are reordered by cross-encoder score."""
    results = [
        _make_result("low relevance", score=0.8),
        _make_result("high relevance", score=0.3),
        _make_result("medium relevance", score=0.5),
    ]
    # Cross-encoder gives different ordering than the original
    mock_cross_encoder.predict.return_value = np.array([0.1, 0.9, 0.5])

    reranked = reranker.rerank("tax question", results, top_k=3)

    assert len(reranked) == 3
    assert reranked[0].content == "high relevance"
    assert reranked[1].content == "medium relevance"
    assert reranked[2].content == "low relevance"


def test_rerank_respects_top_k(
    reranker: CrossEncoderReranker,
    mock_cross_encoder: MagicMock,
) -> None:
    """Only top_k results are returned."""
    results = [_make_result(f"chunk {i}") for i in range(5)]
    mock_cross_encoder.predict.return_value = np.array([0.5, 0.1, 0.9, 0.3, 0.7])

    reranked = reranker.rerank("query", results, top_k=2)

    assert len(reranked) == 2
    assert reranked[0].content == "chunk 2"  # score 0.9
    assert reranked[1].content == "chunk 4"  # score 0.7


def test_rerank_empty_results(reranker: CrossEncoderReranker) -> None:
    """Empty input returns empty output."""
    reranked = reranker.rerank("query", [], top_k=5)
    assert reranked == []


def test_rerank_updates_score(
    reranker: CrossEncoderReranker,
    mock_cross_encoder: MagicMock,
) -> None:
    """Result scores are updated to the cross-encoder score."""
    results = [_make_result("chunk", score=0.5)]
    mock_cross_encoder.predict.return_value = np.array([0.85])

    reranked = reranker.rerank("query", results, top_k=1)

    assert reranked[0].score == pytest.approx(0.85)


def test_rerank_preserves_metadata(
    reranker: CrossEncoderReranker,
    mock_cross_encoder: MagicMock,
) -> None:
    """Reranking preserves all fields except score."""
    result = _make_result("important tax info", score=0.3)
    original_id = result.chunk_id
    original_url = result.source_url
    mock_cross_encoder.predict.return_value = np.array([0.9])

    reranked = reranker.rerank("query", [result], top_k=1)

    assert reranked[0].chunk_id == original_id
    assert reranked[0].source_url == original_url
    assert reranked[0].content == "important tax info"


def test_rerank_passes_correct_pairs(
    reranker: CrossEncoderReranker,
    mock_cross_encoder: MagicMock,
) -> None:
    """Query-content pairs are correctly formed for the model."""
    results = [
        _make_result("first chunk"),
        _make_result("second chunk"),
    ]
    mock_cross_encoder.predict.return_value = np.array([0.5, 0.5])

    reranker.rerank("my query", results, top_k=2)

    call_args = mock_cross_encoder.predict.call_args[0][0]
    assert call_args == [
        ("my query", "first chunk"),
        ("my query", "second chunk"),
    ]
