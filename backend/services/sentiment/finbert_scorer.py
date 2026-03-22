"""
FinBERT sentiment scorer.

Uses the ProsusAI/finbert model (finance-tuned BERT) to score news headlines.
Model is downloaded once on first use and cached in ~/.cache/huggingface.

Output labels → scores:
  positive →  +score  (0 to +1)
  negative →  -score  (-1 to 0)
  neutral  →   0

The Docker image mounts a volume for the HuggingFace cache so the model
persists across container restarts.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from core.logging import get_logger
from services.sentiment.news_fetcher import NewsItem

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

MODEL_NAME = "ProsusAI/finbert"

# Lazy-loaded — model loads on first call, not at import time
_pipeline = None
_lock = threading.Lock()


def _get_pipeline():
    """Thread-safe lazy loader for the FinBERT inference pipeline."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    with _lock:
        if _pipeline is not None:
            return _pipeline
        logger.info("Loading FinBERT model (first run may take ~30s to download)...")
        try:
            from transformers import pipeline
            _pipeline = pipeline(
                "text-classification",
                model=MODEL_NAME,
                # Use CPU — GPU not assumed in this deployment
                device=-1,
                # Return all label scores so we can compute a signed float
                top_k=None,
            )
            logger.info("FinBERT model loaded successfully")
        except Exception as exc:
            logger.error("FinBERT load failed", extra={"error": str(exc)})
            raise
    return _pipeline


def score_headline(headline: str) -> float:
    """
    Score a single headline.

    Returns a float in [-1.0, +1.0]:
      +1.0 = maximally positive
      -1.0 = maximally negative
       0.0 = neutral
    """
    if not headline or not headline.strip():
        return 0.0

    try:
        pipe = _get_pipeline()
        # Truncate to 512 tokens (BERT limit)
        results = pipe(headline[:512])
        # results is [[{label, score}, ...]]
        label_scores = {r["label"].lower(): r["score"] for r in results[0]}

        positive = label_scores.get("positive", 0.0)
        negative = label_scores.get("negative", 0.0)
        # neutral contributes 0

        return round(positive - negative, 4)
    except Exception as exc:
        logger.warning("FinBERT scoring failed", extra={"error": str(exc)})
        return 0.0


def score_items(items: list[NewsItem]) -> list[NewsItem]:
    """
    Score a list of NewsItems in-place and return them.
    Batches titles to avoid repeated model calls.
    """
    if not items:
        return items

    titles = [item.title[:512] for item in items]

    try:
        pipe = _get_pipeline()
        batch_results = pipe(titles, batch_size=16)
        for item, result in zip(items, batch_results):
            label_scores = {r["label"].lower(): r["score"] for r in result}
            positive = label_scores.get("positive", 0.0)
            negative = label_scores.get("negative", 0.0)
            item.sentiment_score = round(positive - negative, 4)
    except Exception as exc:
        logger.error("Batch FinBERT scoring failed", extra={"error": str(exc)})
        for item in items:
            item.sentiment_score = 0.0

    return items
