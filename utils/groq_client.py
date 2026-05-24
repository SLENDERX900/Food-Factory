"""
Platform-aware Groq copy generation.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

FALLBACK_ANGLES = ["Time-Saver", "Lazy Dinner", "Weeknight Hero", "Ingredient Count", "Core Method"]

PLATFORM_GUIDES = {
    "pinterest": {
        "system": (
            "You are a performance marketer for Pinterest. Write native Pinterest hooks "
            "with trend-aware phrasing, clear benefits, curiosity, and search-friendly wording."
        ),
        "hook_style": "6-8 words, visual, benefit-led, clicky without sounding spammy",
        "description_style": "15-25 words, keyword-rich, useful, pin-description ready",
        "lingo": [
            "save-worthy",
            "weeknight win",
            "better than takeout",
            "lazy-girl dinner",
            "high-protein",
            "meal-prep friendly",
            "cozy comfort food",
        ],
    },
    "reddit": {
        "system": (
            "You are a performance marketer for Reddit. Write hooks that feel human, "
            "specific, community-native, and non-corporate."
        ),
        "hook_style": "8-14 words, honest, sharp, curiosity-led, not ad-speak",
        "description_style": "20-40 words, conversational, context-rich, no hype fluff",
        "lingo": [
            "actually worth it",
            "low-key",
            "OP-level",
            "people were split on this",
            "surprisingly good",
            "hot take",
            "here's the thing",
        ],
    },
}


def check_connection() -> tuple[bool, str]:
    if not GROQ_API_KEY:
        return False, "GROQ_API_KEY not set."
    try:
        client = Groq(api_key=GROQ_API_KEY)
        client.models.list()
        return True, GROQ_MODEL
    except Exception as exc:
        return False, f"Groq API error: {exc}"


def _generate(prompt: str, *, system_prompt: str, model: str | None = None, max_tokens: int = 900) -> str:
    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=model or GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        max_tokens=max_tokens,
        top_p=0.95,
    )
    return (response.choices[0].message.content or "").strip()


def _extract_dynamic_angles(recipe: dict[str, Any], trend_context: list[dict[str, Any]]) -> list[str]:
    angles: list[str] = []
    name = recipe.get("name", "").lower()
    benefit = recipe.get("benefit", "").lower()
    time_text = recipe.get("time", "").lower()

    if any(x in time_text for x in ("15", "20", "30", "quick", "fast", "min")):
        angles.append("Lightning-Fast")
    if any(x in name or x in benefit for x in ("easy", "simple", "lazy", "beginner", "foolproof")):
        angles.append("Effortless")
    if any(x in name or x in benefit for x in ("healthy", "protein", "keto", "low-carb")):
        angles.append("Health-Boost")
    if any(x in name for x in ("chicken", "beef", "salmon", "shrimp", "tofu", "steak")):
        angles.append("Protein-Packed")
    if any(x in name or x in benefit for x in ("crispy", "crunchy", "golden", "juicy")):
        angles.append("Texture-Perfect")
    if any(x in name or x in benefit for x in ("sheet-pan", "one-pan", "one pot", "skillet")):
        angles.append("Minimal-Cleanup")
    if any(x in benefit for x in ("family", "kid", "crowd", "picky")):
        angles.append("Family-Approved")
    if any(x in name or x in benefit for x in ("budget", "pantry", "cheap", "affordable")):
        angles.append("Budget-Smart")

    trend_text = " ".join(f"{item.get('title', '')} {item.get('description', '')}" for item in trend_context[:6]).lower()
    if "better than takeout" in trend_text:
        angles.append("Takeout-Beater")
    if "high protein" in trend_text:
        angles.append("Macro-Friendly")
    if "comfort" in trend_text or "cozy" in trend_text:
        angles.append("Cozy-Craving")

    for fallback in ("Time-Saver", "Weeknight-Hero", "Ingredient-Win", "Core-Method", "Big-Flavor"):
        if fallback not in angles:
            angles.append(fallback)
        if len(angles) >= 5:
            break
    return angles[:5]


def _extract_trend_lingo(trend_context: list[dict[str, Any]], platform: str) -> list[str]:
    seeds = list(PLATFORM_GUIDES.get(platform, PLATFORM_GUIDES["pinterest"])["lingo"])
    corpus = " ".join(f"{item.get('title', '')} {item.get('description', '')}" for item in trend_context[:10])
    candidates = re.findall(r"\b[a-zA-Z][a-zA-Z\-']{3,20}\b", corpus.lower())
    stop_words = {
        "this",
        "that",
        "with",
        "from",
        "your",
        "into",
        "recipe",
        "dinner",
        "easy",
        "best",
        "food",
        "make",
        "made",
        "more",
        "than",
        "just",
    }
    seen = set()
    for token in candidates:
        if token in stop_words or token in seen:
            continue
        seen.add(token)
        if len(seeds) >= 12:
            break
        seeds.append(token)
    return seeds[:12]


def _extract_json_list(raw: str) -> list[dict[str, Any]] | None:
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end])
    except Exception:
        return None
    return data if isinstance(data, list) else None


def generate_hook_packages(
    recipe: dict[str, Any],
    trend_context: list[dict[str, Any]] | None = None,
    model: str | None = None,
    *,
    platform: str = "pinterest",
) -> list[dict[str, Any]]:
    trend_context = trend_context or []
    platform_key = platform if platform in PLATFORM_GUIDES else "pinterest"
    guide = PLATFORM_GUIDES[platform_key]
    angles = _extract_dynamic_angles(recipe, trend_context)
    lingo = _extract_trend_lingo(trend_context, platform_key)

    trend_lines = []
    for item in trend_context[:8]:
        title = item.get("title", "").strip()
        description = item.get("description", "").strip()
        if title or description:
            trend_lines.append(f"- {title[:120]} | {description[:160]}")
    trend_block = "\n".join(trend_lines) if trend_lines else "- No external trend examples available"

    prompt = f"""Create {platform_key.title()} marketing copy packages for this recipe.

PLATFORM:
{platform_key.title()}

PLATFORM BEHAVIOR:
- Hook style: {guide['hook_style']}
- Description style: {guide['description_style']}
- Native lingo ideas: {", ".join(lingo)}

RECIPE:
- Name: {recipe.get("name", "")}
- Time: {recipe.get("time", "")}
- Benefit: {recipe.get("benefit", "")}
- Ingredients: {recipe.get("ingredient_names", recipe.get("ingredients", ""))}
- Keywords: {recipe.get("meta_keywords", "")}
- Voice sample: {recipe.get("blog_content_sample", "")[:350]}

REAL TREND SIGNALS:
{trend_block}

ANGLES TO COVER:
{chr(10).join(f"{i + 1}. {angle}" for i, angle in enumerate(angles))}

RULES:
1. Sound current, native, and trend-aware.
2. Reuse winning phrasing patterns from the trend signals without copying them.
3. Make the hook specific to this recipe.
4. Avoid generic filler, cheesy ad-speak, and robotic phrasing.
5. Return only valid JSON.

JSON SHAPE:
[
  {{
    "angle": "Lightning-Fast",
    "hook": "hook text",
    "description": "description text",
    "vibe_prompt": "short visual direction"
  }}
]
"""

    try:
        raw = _generate(prompt, system_prompt=guide["system"], model=model)
        parsed = _extract_json_list(raw)
        if parsed and len(parsed) >= 5:
            return parsed[:5]
    except Exception as exc:
        print(f"GROQ DEBUG: generation failed for {recipe.get('name', '')}: {exc}", flush=True)

    name = recipe.get("name", "Recipe")

    def fallback(angle: str) -> dict[str, str]:
        lower = angle.lower()
        if "fast" in lower or "time" in lower:
            return {
                "hook": "Dinner sorted in under 30",
                "description": f"Quick {name} with big payoff and weeknight energy people actually save.",
                "vibe_prompt": "speedy weeknight food hero",
            }
        if "protein" in lower or "health" in lower:
            return {
                "hook": "High-protein comfort that still hits",
                "description": f"{name} that feels indulgent but still fits a smart, high-protein dinner plan.",
                "vibe_prompt": "macro-friendly cozy plate",
            }
        if "texture" in lower:
            return {
                "hook": "Crispy outside, worth the hype",
                "description": f"{name} with texture-first appeal, golden edges, and serious save-worthy payoff.",
                "vibe_prompt": "crispy close-up food shot",
            }
        return {
            "hook": f"{name} but make it irresistible",
            "description": f"A trend-ready angle for {name} with native phrasing and clear payoff.",
            "vibe_prompt": "appetizing social-first food image",
        }

    return [{"angle": angle, **fallback(angle)} for angle in angles]


def generate_hooks(
    recipe: dict[str, Any],
    trend_context: list[dict[str, Any]] | None = None,
    model: str | None = None,
    *,
    platform: str = "pinterest",
) -> dict[str, str]:
    packages = generate_hook_packages(recipe, trend_context=trend_context, model=model, platform=platform)
    return {item.get("angle", f"Angle-{idx}"): item.get("hook", "") for idx, item in enumerate(packages)}


def generate_description(
    recipe: dict[str, Any],
    trend_context: list[dict[str, Any]] | None = None,
    model: str | None = None,
    *,
    platform: str = "pinterest",
) -> str:
    packages = generate_hook_packages(recipe, trend_context=trend_context, model=model, platform=platform)
    return (packages[0].get("description", "") if packages else "").strip()


ANGLES = FALLBACK_ANGLES
