"""Unit tests for WikimediaClient, caching, redirect handling, and low data thresholds."""

import os
import tempfile
import pandas as pd
import pytest

from wiki_market_validator.api_client import WikimediaClient


def test_sqlite_cache_persistence():
    """Verify SQLite cache stores and retrieves JSON payloads correctly."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        temp_db = f.name

    try:
        client = WikimediaClient(cache_db_path=temp_db)
        test_key = "test_cache_hash_123"
        test_url = "https://example.com/api/test"
        payload = {"items": [{"views": 100}, {"views": 150}]}

        client._set_cache(test_key, test_url, 200, payload)

        status, retrieved = client._get_cache(test_key)
        assert status == 200
        assert retrieved == payload
    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)


def test_insufficient_data_threshold():
    """When article has fewer than 30 days of data, client should flag INSUFFICIENT_DATA."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        temp_db = f.name

    try:
        client = WikimediaClient(cache_db_path=temp_db)
        # Mock 10 days of data in cache
        start_date = "20240101"
        end_date = "20240110"
        mock_items = [
            {"timestamp": f"2024010{i}00", "views": 25} for i in range(1, 10)
        ]
        url = (
            f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"en.wikipedia.org/all-access/user/TestArticle/daily/{start_date}00/{end_date}00"
        )
        # Cache mock response
        import hashlib, json
        cache_key = hashlib.sha256(f"{url}?{{}}".encode("utf-8")).hexdigest()
        client._set_cache(cache_key, url, 200, {"items": mock_items})

        # Also mock canonical title
        canon_url = "https://en.wikipedia.org/w/api.php?{\"action\": \"query\", \"format\": \"json\", \"redirects\": 1, \"titles\": \"TestArticle\"}"
        canon_key = hashlib.sha256(canon_url.encode("utf-8")).hexdigest()
        client._set_cache(canon_key, canon_url, 200, {"query": {"pages": {"1": {"title": "TestArticle", "pageid": 1}}}})

        status, df, meta = client.get_article_pageviews("en.wikipedia.org", "TestArticle", start_date, end_date)
        assert status == "INSUFFICIENT_DATA"
        assert meta["n_days"] < 30
        assert "warning" in meta
    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)
