"""
Notion helpers for scheduling calendar sync and lightweight forecasting.
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")
NOTION_API_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"


def notion_enabled() -> bool:
    return bool(NOTION_TOKEN and NOTION_DATABASE_ID)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION,
    }


def _rich_text(value: str) -> dict[str, Any]:
    return {"rich_text": [{"text": {"content": value[:2000]}}]} if value else {"rich_text": []}


def _title(value: str) -> dict[str, Any]:
    return {"title": [{"text": {"content": value[:2000]}}]}


def _safe_select(value: str) -> dict[str, Any]:
    return {"select": {"name": value}} if value else {"select": None}


def build_schedule_properties(job: dict[str, Any]) -> dict[str, Any]:
    metadata = job.get("metadata", {}) or {}
    scheduled_for = job.get("scheduled_for", "")
    post_mode = "Auto" if job.get("platform") == "pinterest" else "Manual Reminder"
    return {
        "Recipe Name": _title(job.get("recipe_name", "Untitled")),
        "Platform": _safe_select(job.get("platform", "").title()),
        "Hook": _rich_text(job.get("title", "")),
        "Description": _rich_text(job.get("body", "")),
        "Status": _safe_select(_status_label(job)),
        "Recipe URL": {"url": job.get("source_url", "")} if job.get("source_url") else None,
        "Scheduled At": {"date": {"start": scheduled_for}} if scheduled_for else None,
        "Destination": _rich_text(job.get("destination", "")),
        "Job ID": _rich_text(job.get("id", "")),
        "Post Mode": _safe_select(post_mode),
        "Angle": _safe_select(metadata.get("angle", "")) if metadata.get("angle") else None,
        "Platform Post ID": _rich_text(job.get("platform_post_id", "")),
        "Last Error": _rich_text(job.get("last_error", "")),
    }


def _clean_properties(properties: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in properties.items():
        if value is None:
            continue
        cleaned[key] = value
    return cleaned


def _status_label(job: dict[str, Any]) -> str:
    status = job.get("status", "")
    if status == "scheduled_remote":
        return "Scheduled"
    if status == "published":
        return "Posted"
    if status == "failed":
        return "Needs Review"
    if job.get("platform") == "reddit":
        return "Reminder Set"
    return "Queued"


def create_schedule_entry(job: dict[str, Any]) -> tuple[bool, str, str]:
    if not notion_enabled():
        return False, "Notion not configured", ""
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": _clean_properties(build_schedule_properties(job)),
    }
    try:
        response = requests.post(f"{NOTION_BASE}/pages", headers=_headers(), json=payload, timeout=20)
        if response.status_code in (200, 201):
            page_id = response.json().get("id", "")
            return True, "created", page_id
        return False, response.text[:200], ""
    except Exception as exc:
        return False, str(exc), ""


def update_schedule_entry(page_id: str, job: dict[str, Any]) -> tuple[bool, str]:
    if not notion_enabled() or not page_id:
        return False, "Notion not configured or page missing"
    payload = {"properties": _clean_properties(build_schedule_properties(job))}
    try:
        response = requests.patch(f"{NOTION_BASE}/pages/{page_id}", headers=_headers(), json=payload, timeout=20)
        if response.status_code == 200:
            return True, "updated"
        return False, response.text[:200]
    except Exception as exc:
        return False, str(exc)


def query_upcoming_schedule(days: int = 14) -> list[dict[str, Any]]:
    if not notion_enabled():
        return []
    start = datetime.now(timezone.utc).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    payload = {
        "filter": {
            "and": [
                {"property": "Scheduled At", "date": {"on_or_after": start}},
                {"property": "Scheduled At", "date": {"on_or_before": end}},
            ]
        },
        "page_size": 100,
    }
    try:
        response = requests.post(
            f"{NOTION_BASE}/databases/{NOTION_DATABASE_ID}/query",
            headers=_headers(),
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception:
        return []


def summarize_upcoming_by_platform(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for entry in entries:
        props = entry.get("properties", {})
        platform = (((props.get("Platform") or {}).get("select") or {}).get("name") or "Unknown").strip()
        counts[platform] += 1
    return dict(counts)


def recipe_names_from_entries(entries: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for entry in entries:
        title_parts = (((entry.get("properties", {}).get("Recipe Name") or {}).get("title")) or [])
        if title_parts:
            names.append("".join(part.get("plain_text", "") for part in title_parts).strip())
    return [name for name in names if name]


def forecast_recipe_candidates(current_recipes: list[dict[str, Any]], upcoming_recipe_names: list[str], limit: int = 5) -> list[str]:
    scheduled = {name.strip().lower() for name in upcoming_recipe_names}
    candidates = []
    for recipe in current_recipes:
        name = recipe.get("name", "").strip()
        if name and name.lower() not in scheduled:
            candidates.append(name)
        if len(candidates) >= limit:
            break
    return candidates
