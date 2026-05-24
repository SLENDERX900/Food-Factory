"""
Persistent cross-platform scheduling queue.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

QUEUE_PATH = Path("data/post_schedule_queue.json")


def _ensure_file() -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not QUEUE_PATH.exists():
        QUEUE_PATH.write_text("[]", encoding="utf-8")


def _read() -> list[dict[str, Any]]:
    _ensure_file()
    try:
        return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write(items: list[dict[str, Any]]) -> None:
    _ensure_file()
    QUEUE_PATH.write_text(json.dumps(items, indent=2, ensure_ascii=True), encoding="utf-8")


def list_queue() -> list[dict[str, Any]]:
    items = _read()
    return sorted(items, key=lambda item: item.get("scheduled_for", ""))


def add_job(
    *,
    platform: str,
    recipe_name: str,
    title: str,
    body: str,
    destination: str,
    scheduled_for: datetime,
    source_url: str = "",
    image_url: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    items = _read()
    job = {
        "id": str(uuid.uuid4()),
        "platform": platform,
        "recipe_name": recipe_name,
        "title": title,
        "body": body,
        "destination": destination,
        "source_url": source_url,
        "image_url": image_url,
        "scheduled_for": scheduled_for.astimezone(timezone.utc).isoformat(),
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "platform_post_id": "",
        "notion_page_id": "",
        "last_error": "",
        "metadata": metadata or {},
    }
    items.append(job)
    _write(items)
    return job


def update_job(job_id: str, **updates: Any) -> dict[str, Any] | None:
    items = _read()
    updated = None
    for item in items:
        if item.get("id") == job_id:
            item.update(updates)
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            updated = item
            break
    _write(items)
    return updated


def delete_job(job_id: str) -> None:
    items = [item for item in _read() if item.get("id") != job_id]
    _write(items)


def due_jobs(now: datetime | None = None) -> list[dict[str, Any]]:
    current = now or datetime.now(timezone.utc)
    items = []
    for item in list_queue():
        if item.get("status") not in {"queued", "failed"}:
            continue
        try:
            scheduled_for = datetime.fromisoformat(item["scheduled_for"])
        except Exception:
            continue
        if scheduled_for <= current:
            items.append(item)
    return items
