"""
Reddit posting client.

Uses Reddit script-app OAuth for direct posting. Scheduling itself is handled
locally by the app queue.
"""

from __future__ import annotations

import os
from typing import Any

import requests

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME", "")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "SignalFactory/1.0 by /u/yourusername")

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
SUBMIT_URL = "https://oauth.reddit.com/api/submit"


def check_reddit_posting_config() -> tuple[bool, str]:
    required = {
        "REDDIT_CLIENT_ID": REDDIT_CLIENT_ID,
        "REDDIT_CLIENT_SECRET": REDDIT_CLIENT_SECRET,
        "REDDIT_USERNAME": REDDIT_USERNAME,
        "REDDIT_PASSWORD": REDDIT_PASSWORD,
        "REDDIT_USER_AGENT": REDDIT_USER_AGENT,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        return False, f"Missing: {', '.join(missing)}"
    return True, "Ready"


def _get_access_token() -> str:
    response = requests.post(
        TOKEN_URL,
        auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
        data={"grant_type": "password", "username": REDDIT_USERNAME, "password": REDDIT_PASSWORD},
        headers={"User-Agent": REDDIT_USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    token = response.json().get("access_token", "")
    if not token:
        raise RuntimeError("Reddit access token missing from response")
    return token


def submit_reddit_post(*, subreddit: str, title: str, body: str, url: str = "") -> tuple[bool, str]:
    ok, message = check_reddit_posting_config()
    if not ok:
        return False, message

    try:
        token = _get_access_token()
        payload: dict[str, Any] = {
            "sr": subreddit,
            "title": title[:300],
            "kind": "self",
            "text": body[:40000],
            "resubmit": True,
            "sendreplies": True,
            "api_type": "json",
        }
        if url:
            payload["kind"] = "link"
            payload["url"] = url
            payload.pop("text", None)

        response = requests.post(
            SUBMIT_URL,
            headers={"Authorization": f"bearer {token}", "User-Agent": REDDIT_USER_AGENT},
            data=payload,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        errors = data.get("json", {}).get("errors", [])
        if errors:
            return False, str(errors)
        post_url = data.get("json", {}).get("data", {}).get("url", "") or "submitted"
        return True, post_url
    except Exception as exc:
        return False, str(exc)
