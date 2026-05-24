"""
Pinterest scheduling + Notion status sync helpers.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time as dt_time, timedelta, timezone

import requests

PINTEREST_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", "")
PINTEREST_BOARD_ID = os.getenv("PINTEREST_BOARD_ID", "")
PINTEREST_API_BASE = "https://api.pinterest.com/v5"

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_API_VERSION = "2022-06-28"


def build_schedule_slots(
    count: int,
    start_dt: datetime | None = None,
    *,
    posts_per_day: int = 1,
    start_date: date | None = None,
    first_hour_utc: int = 14,
) -> list[datetime]:
    base = start_dt
    if base is None:
        chosen_date = start_date or (datetime.now(timezone.utc) + timedelta(days=1)).date()
        base = datetime.combine(chosen_date, dt_time(hour=first_hour_utc, tzinfo=timezone.utc))

    slots: list[datetime] = []
    spacing_hours = max(1, 12 // max(posts_per_day, 1))
    for index in range(count):
        day_offset = index // posts_per_day
        slot_in_day = index % posts_per_day
        slots.append(base + timedelta(days=day_offset, hours=slot_in_day * spacing_hours))
    return slots


def schedule_pin(title: str, description: str, link: str, image_url: str, publish_at: datetime) -> tuple[bool, str]:
    if not PINTEREST_TOKEN or not PINTEREST_BOARD_ID:
        return False, "Pinterest credentials missing"
    body = {
        "board_id": PINTEREST_BOARD_ID,
        "title": title[:100],
        "description": description[:800],
        "link": link,
        "media_source": {"source_type": "image_url", "url": image_url},
        "publish_at": publish_at.isoformat(),
    }
    headers = {"Authorization": f"Bearer {PINTEREST_TOKEN}", "Content-Type": "application/json"}
    try:
        resp = requests.post(f"{PINTEREST_API_BASE}/pins", headers=headers, json=body, timeout=30)
        if resp.status_code in (200, 201):
            return True, resp.json().get("id", "scheduled")
        return False, f"{resp.status_code}: {resp.text[:200]}"
    except Exception as exc:
        return False, str(exc)


def update_notion_item_scheduled(page_id: str, scheduled_ts: datetime) -> tuple[bool, str]:
    if not NOTION_TOKEN:
        return False, "Notion token missing"
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION,
    }
    payload = {
        "properties": {
            "Status": {"select": {"name": "Scheduled"}},
            "Scheduled At": {"date": {"start": scheduled_ts.isoformat()}},
        }
    }
    try:
        resp = requests.patch(url, headers=headers, json=payload, timeout=20)
        if resp.status_code == 200:
            return True, "updated"
        return False, f"{resp.status_code}: {resp.text[:200]}"
    except Exception as exc:
        return False, str(exc)
