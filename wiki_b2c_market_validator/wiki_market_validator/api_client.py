"""Wikimedia REST API and Wikidata client with SQLite caching, redirect handling, and bot filtering."""

import datetime
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "MarketDemandValidatorBot/1.0 (https://github.com/wiki-market-validator; contact@example.com) "
    "BasedOnPythonRequests/2.31.0"
)
WIKIMEDIA_AQS_BASE = "https://wikimedia.org/api/rest_v1"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"


class WikimediaClient:
    """Production client for Wikimedia Analytics API and Wikidata cross-lingual mapping."""

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        cache_db_path: Optional[str] = None,
        timeout: int = 15,
        max_retries: int = 3,
        rate_limit_delay: float = 0.05,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0.0

        if cache_db_path is None:
            # Default to .wiki_cache.sqlite in the skill directory or current working dir
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cache_db_path = os.path.join(base_dir, ".wiki_cache.sqlite")

        self.cache_db_path = cache_db_path
        self._init_cache()

    def _init_cache(self) -> None:
        """Initialize SQLite caching schema."""
        os.makedirs(os.path.dirname(self.cache_db_path), exist_ok=True)
        conn = sqlite3.connect(self.cache_db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_cache (
                    cache_key TEXT PRIMARY KEY,
                    url TEXT,
                    response_json TEXT,
                    status_code INTEGER,
                    created_at REAL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _get_cache(self, cache_key: str) -> Optional[Tuple[int, Dict[str, Any]]]:
        """Retrieve cached JSON response if present."""
        conn = None
        try:
            conn = sqlite3.connect(self.cache_db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status_code, response_json FROM api_cache WHERE cache_key = ?",
                (cache_key,),
            )
            row = cursor.fetchone()
            if row:
                return row[0], json.loads(row[1])
        except Exception as e:
            logger.warning("Cache read failed for key %s: %s", cache_key, e)
        finally:
            if conn:
                conn.close()
        return None

    def _set_cache(self, cache_key: str, url: str, status_code: int, data: Dict[str, Any]) -> None:
        """Store JSON response into SQLite cache."""
        conn = None
        try:
            conn = sqlite3.connect(self.cache_db_path)
            conn.execute(
                """
                INSERT OR REPLACE INTO api_cache (cache_key, url, response_json, status_code, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (cache_key, url, json.dumps(data, ensure_ascii=False), status_code, time.time()),
            )
            conn.commit()
        except Exception as e:
            logger.warning("Cache write failed for key %s: %s", cache_key, e)
        finally:
            if conn:
                conn.close()

    def _request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
    ) -> Tuple[int, Dict[str, Any]]:
        """Perform HTTP GET request with retries, rate-limiting, and caching."""
        # Normalize params for cache key
        param_str = json.dumps(params or {}, sort_keys=True)
        raw_key = f"{url}?{param_str}"
        cache_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        if use_cache:
            cached = self._get_cache(cache_key)
            if cached is not None:
                return cached

        # Enforce polite rate limit
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)

        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        retries = 0

        while retries <= self.max_retries:
            try:
                self.last_request_time = time.time()
                response = requests.get(url, params=params, headers=headers, timeout=self.timeout)

                # Handle HTTP 429 Rate Limiting
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = float(retry_after) if retry_after else (2 ** retries + 1.0)
                    logger.warning("Rate limited (HTTP 429). Retrying after %.1fs...", wait_time)
                    time.sleep(wait_time)
                    retries += 1
                    continue

                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception:
                        data = {"raw_text": response.text}
                    if use_cache:
                        self._set_cache(cache_key, url, response.status_code, data)
                    return response.status_code, data

                if response.status_code in (404, 400):
                    # Definite client error / not found
                    try:
                        data = response.json()
                    except Exception:
                        data = {"error": response.text}
                    if use_cache:
                        self._set_cache(cache_key, url, response.status_code, data)
                    return response.status_code, data

                # Server error 5xx, retry with exponential backoff
                if 500 <= response.status_code < 600:
                    retries += 1
                    time.sleep(2 ** retries)
                    continue

                # Any other response
                return response.status_code, {"error": response.text}

            except (requests.RequestException, Exception) as e:
                retries += 1
                if retries > self.max_retries:
                    logger.error("Request failed for %s: %s", url, e)
                    return 599, {"error": str(e)}
                time.sleep(2 ** retries)

        return 599, {"error": "Exceeded max retries"}

    def get_canonical_title(self, project: str, title: str, use_cache: bool = True) -> str:
        """Resolve redirects to get canonical Wikipedia page title."""
        lang = project.split(".")[0]
        url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "titles": title,
            "redirects": 1,
            "format": "json",
        }
        status, data = self._request(url, params=params, use_cache=use_cache)
        if status == 200 and "query" in data and "pages" in data["query"]:
            pages = data["query"]["pages"]
            page = next(iter(pages.values()))
            if "title" in page and page.get("pageid", 0) > 0:
                return page["title"].replace(" ", "_")
        return title.replace(" ", "_")

    def search_articles(
        self, lang: str, query: str, limit: int = 5, use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """Search Wikipedia in a given language for related articles."""
        url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
        }
        status, data = self._request(url, params=params, use_cache=use_cache)
        results = []
        if status == 200 and "query" in data and "search" in data["query"]:
            for item in data["query"]["search"]:
                results.append(
                    {
                        "title": item["title"],
                        "pageid": item["pageid"],
                        "wordcount": item.get("wordcount", 0),
                        "snippet": re.sub(r"<[^>]+>", "", item.get("snippet", "")),
                    }
                )
        return results

    def resolve_multilingual_titles(
        self,
        source_title: str,
        source_lang: str = "en",
        target_langs: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Cross-lingual entity bridge using Wikidata sitelinks.
        Returns a dict:
        {
           'pl': {'title': '...', 'is_exact': True, 'sitelink': '...'},
           'cs': {'title': '...', 'is_exact': True, 'sitelink': '...'},
        }
        """
        if target_langs is None:
            target_langs = ["en", "uk", "pl", "cs", "de", "es"]

        # Step 1: Query Wikidata for the entity sitelinks
        site = f"{source_lang}wiki"
        params = {
            "action": "wbgetentities",
            "sites": site,
            "titles": source_title.replace("_", " "),
            "props": "sitelinks",
            "format": "json",
        }
        status, data = self._request(WIKIDATA_API, params=params, use_cache=use_cache)

        resolved: Dict[str, Dict[str, Any]] = {}
        sitelinks: Dict[str, Any] = {}

        if status == 200 and "entities" in data:
            entity = next(iter(data["entities"].values()))
            if "sitelinks" in entity:
                sitelinks = entity["sitelinks"]

        # Step 2: Map to target languages
        for lang in target_langs:
            key = f"{lang}wiki"
            if key in sitelinks:
                title = sitelinks[key]["title"]
                resolved[lang] = {
                    "title": title.replace(" ", "_"),
                    "is_exact": True,
                    "source": "wikidata_sitelink",
                }
            else:
                # Sitelink not found in this language edition
                # Fallback: Search the target wiki for best matching article
                search_res = self.search_articles(lang, source_title.replace("_", " "), limit=1, use_cache=use_cache)
                if search_res:
                    resolved[lang] = {
                        "title": search_res[0]["title"].replace(" ", "_"),
                        "is_exact": False,
                        "source": "wiki_search_fallback",
                        "snippet": search_res[0]["snippet"],
                    }
                else:
                    resolved[lang] = {
                        "title": source_title.replace(" ", "_"),
                        "is_exact": False,
                        "source": "unresolved_original",
                    }

        return resolved

    def get_article_pageviews(
        self,
        project: str,
        article: str,
        start_date: str,
        end_date: str,
        agent: str = "user",
        granularity: str = "daily",
        use_cache: bool = True,
    ) -> Tuple[str, pd.DataFrame, Dict[str, Any]]:
        """
        Fetch per-article pageviews from Wikimedia Analytics REST API.
        
        Args:
            project: e.g. 'uk.wikipedia.org' or 'pl.wikipedia.org'
            article: raw article title (will be encoded properly)
            start_date: 'YYYYMMDD'
            end_date: 'YYYYMMDD'
            agent: 'user' (default, human traffic), 'all-agents', 'spider', 'automated'
            granularity: 'daily' or 'monthly'
            use_cache: whether to use SQLite cache
            
        Returns:
            status: 'SUCCESS', 'PAGE_NOT_FOUND', or 'INSUFFICIENT_DATA'
            df: DataFrame with ['date', 'views']
            metadata: dict with summary stats & flags
        """
        # Ensure project has domain
        if "." not in project:
            project = f"{project}.wikipedia.org"

        # Canonicalize title & URL-encode
        canonical = self.get_canonical_title(project, article, use_cache=use_cache)
        encoded_article = urllib.parse.quote(canonical.replace(" ", "_"), safe="")

        start_clean = start_date.replace("-", "")[:8]
        end_clean = end_date.replace("-", "")[:8]

        url = (
            f"{WIKIMEDIA_AQS_BASE}/metrics/pageviews/per-article/"
            f"{project}/all-access/{agent}/{encoded_article}/{granularity}/{start_clean}00/{end_clean}00"
        )

        status_code, data = self._request(url, use_cache=use_cache)

        if status_code == 404 or "items" not in data or not data["items"]:
            return (
                "PAGE_NOT_FOUND",
                pd.DataFrame(columns=["date", "views"]),
                {"project": project, "article": canonical, "error": "Article not found or zero recorded views"},
            )

        items = data["items"]
        rows = []
        for it in items:
            ts_str = it["timestamp"][:8]
            dt = datetime.datetime.strptime(ts_str, "%Y%m%d").date()
            rows.append({"date": dt, "views": int(it.get("views", 0))})

        df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

        # Validate minimum data requirements
        n_days = len(df)
        mean_views = df["views"].mean() if n_days > 0 else 0

        metadata = {
            "project": project,
            "canonical_title": canonical,
            "agent": agent,
            "n_days": n_days,
            "total_views": int(df["views"].sum()),
            "mean_views": float(mean_views),
            "max_views": int(df["views"].max()) if n_days > 0 else 0,
            "start_date": str(df["date"].min()) if n_days > 0 else start_date,
            "end_date": str(df["date"].max()) if n_days > 0 else end_date,
        }

        # Check edge case: low data
        if n_days < 30 or mean_views < 10.0:
            metadata["warning"] = (
                f"Low data volume: {n_days} days recorded, average {mean_views:.1f} views/day. "
                "Confidence in statistical trend is restricted."
            )
            return "INSUFFICIENT_DATA", df, metadata

        return "SUCCESS", df, metadata

    def get_bot_audit(
        self,
        project: str,
        article: str,
        start_date: str,
        end_date: str,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Audit bot vs human traffic for an article over the period.
        Calculates P_bot = (Views_all - Views_user) / Views_all.
        """
        _, df_user, meta_user = self.get_article_pageviews(
            project, article, start_date, end_date, agent="user", use_cache=use_cache
        )
        _, df_all, meta_all = self.get_article_pageviews(
            project, article, start_date, end_date, agent="all-agents", use_cache=use_cache
        )

        user_views = meta_user.get("total_views", 0)
        all_views = meta_all.get("total_views", 0)

        if all_views > 0:
            bot_views = max(0, all_views - user_views)
            bot_ratio = bot_views / all_views
        else:
            bot_views = 0
            bot_ratio = 0.0

        return {
            "user_views": user_views,
            "all_views": all_views,
            "bot_views": bot_views,
            "bot_ratio": round(bot_ratio, 4),
            "is_bot_heavy": bot_ratio > 0.40,
        }

    def get_aggregate_project_pageviews(
        self,
        project: str,
        start_date: str,
        end_date: str,
        granularity: str = "monthly",
        use_cache: bool = True,
    ) -> Tuple[str, pd.DataFrame, Dict[str, Any]]:
        """
        Fetch macro platform traffic for the entire language project.
        Allows calculating relative attention market share.
        """
        if "." not in project:
            project = f"{project}.wikipedia.org"

        start_clean = start_date.replace("-", "")[:8]
        end_clean = end_date.replace("-", "")[:8]

        url = (
            f"{WIKIMEDIA_AQS_BASE}/metrics/pageviews/aggregate/"
            f"{project}/all-access/user/{granularity}/{start_clean}00/{end_clean}00"
        )
        status_code, data = self._request(url, use_cache=use_cache)

        if status_code != 200 or "items" not in data:
            return (
                "ERROR",
                pd.DataFrame(columns=["date", "views"]),
                {"project": project, "error": data.get("error", "Failed aggregate fetch")},
            )

        rows = []
        for it in data["items"]:
            ts_str = it["timestamp"][:8]
            dt = datetime.datetime.strptime(ts_str, "%Y%m%d").date()
            rows.append({"date": dt, "views": int(it.get("views", 0))})

        df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        return "SUCCESS", df, {"project": project, "total_aggregate_views": int(df["views"].sum())}

    def get_article_edits(
        self,
        project: str,
        article: str,
        start_date: str,
        end_date: str,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Fetch monthly revisions/edits count to assess community interest and maintenance.
        """
        if "." not in project:
            project = f"{project}.wikipedia.org"

        canonical = self.get_canonical_title(project, article, use_cache=use_cache)
        encoded_article = urllib.parse.quote(canonical.replace(" ", "_"), safe="")

        start_clean = start_date.replace("-", "")[:8]
        end_clean = end_date.replace("-", "")[:8]

        url = (
            f"{WIKIMEDIA_AQS_BASE}/metrics/edits/per-page/"
            f"{project}/{encoded_article}/user/monthly/{start_clean}00/{end_clean}00"
        )
        status_code, data = self._request(url, use_cache=use_cache)

        total_edits = 0
        if status_code == 200 and "items" in data and data["items"]:
            results = data["items"][0].get("results", [])
            for res in results:
                total_edits += int(res.get("edits", 0))

        return {
            "canonical_title": canonical,
            "total_edits": total_edits,
            "edit_activity_level": "High" if total_edits > 50 else ("Medium" if total_edits > 10 else "Low"),
        }
