"""
Reddit scraping helpers using Reddit's public JSON endpoints.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import requests

USER_AGENT = "SignalFactory/1.0 (marketing research tool)"
BASE_HEADERS = {"User-Agent": USER_AGENT}


def scrape_reddit_posts(
    query: str,
    *,
    subreddit: str = "",
    sort: str = "relevance",
    limit: int = 25,
) -> list[dict[str, Any]]:
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        return []

    limit = max(1, min(limit, 100))
    if subreddit.strip():
        url = (
            f"https://www.reddit.com/r/{subreddit.strip()}/search.json"
            f"?q={quote_plus(cleaned_query)}&restrict_sr=1&sort={sort}&limit={limit}"
        )
    else:
        url = f"https://www.reddit.com/search.json?q={quote_plus(cleaned_query)}&sort={sort}&limit={limit}"

    response = requests.get(url, headers=BASE_HEADERS, timeout=20)
    response.raise_for_status()
    payload = response.json()

    children = payload.get("data", {}).get("children", [])
    posts: list[dict[str, Any]] = []
    for child in children:
        data = child.get("data", {})
        posts.append(
            {
                "title": data.get("title", ""),
                "subreddit": data.get("subreddit", ""),
                "author": data.get("author", ""),
                "score": data.get("score", 0),
                "num_comments": data.get("num_comments", 0),
                "url": f"https://www.reddit.com{data.get('permalink', '')}" if data.get("permalink") else "",
                "selftext": (data.get("selftext", "") or "")[:600],
                "created_utc": data.get("created_utc"),
                "over_18": data.get("over_18", False),
            }
        )
    return posts
