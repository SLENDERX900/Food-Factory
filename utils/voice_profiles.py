"""
Persistent voice and storyline profiles for cross-platform content generation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROFILE_PATH = Path("data/voice_profiles.json")

DEFAULT_PROFILES = [
    {
        "name": "Weeknight Rescue",
        "storyline": "fast relief for busy people who still want real food",
        "occasion": "weekday dinner rush",
        "tone": "grounded, practical, warm",
        "lingo": ["weeknight win", "low-lift", "actually doable", "save this"],
        "cta_style": "gentle encouragement",
    },
    {
        "name": "Cozy Comfort",
        "storyline": "food that feels like comfort without sounding cheesy",
        "occasion": "rainy nights, cold season, staying in",
        "tone": "cozy, sensory, intimate",
        "lingo": ["cozy dinner", "hits every time", "comfort food energy", "worth making"],
        "cta_style": "nostalgic pull",
    },
    {
        "name": "Better Than Takeout",
        "storyline": "restaurant-style payoff with home kitchen credibility",
        "occasion": "Friday nights, fakeaway, craving-driven posts",
        "tone": "confident, tempting, punchy",
        "lingo": ["better than takeout", "cheaper at home", "craveable", "repeat immediately"],
        "cta_style": "challenge the scroll",
    },
    {
        "name": "Meal Prep Momentum",
        "storyline": "future-you planning with smart effort and payoff",
        "occasion": "Sunday prep, gym routine, busy weeks",
        "tone": "smart, motivating, low-drama",
        "lingo": ["prep once", "weekday sorted", "high-protein", "actually filling"],
        "cta_style": "make life easier",
    },
]


def _ensure_file() -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not PROFILE_PATH.exists():
        PROFILE_PATH.write_text(json.dumps(DEFAULT_PROFILES, indent=2), encoding="utf-8")


def list_profiles() -> list[dict[str, Any]]:
    _ensure_file()
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else DEFAULT_PROFILES
    except Exception:
        return DEFAULT_PROFILES


def save_profiles(profiles: list[dict[str, Any]]) -> None:
    _ensure_file()
    PROFILE_PATH.write_text(json.dumps(profiles, indent=2, ensure_ascii=True), encoding="utf-8")


def upsert_profile(profile: dict[str, Any]) -> None:
    profiles = list_profiles()
    incoming_name = profile.get("name", "").strip()
    if not incoming_name:
        return

    replaced = False
    for index, item in enumerate(profiles):
        if item.get("name", "").strip().lower() == incoming_name.lower():
            profiles[index] = profile
            replaced = True
            break
    if not replaced:
        profiles.append(profile)
    save_profiles(profiles)


def delete_profile(name: str) -> None:
    profiles = [profile for profile in list_profiles() if profile.get("name", "").strip().lower() != name.strip().lower()]
    save_profiles(profiles)


def profile_to_prompt_context(profile: dict[str, Any] | None) -> str:
    if not profile:
        return ""
    lingo = ", ".join(profile.get("lingo", []))
    return (
        f"Profile: {profile.get('name', '')} | "
        f"Storyline: {profile.get('storyline', '')} | "
        f"Occasion: {profile.get('occasion', '')} | "
        f"Tone: {profile.get('tone', '')} | "
        f"Lingo: {lingo} | "
        f"CTA style: {profile.get('cta_style', '')}"
    ).strip()
