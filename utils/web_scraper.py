"""
Utilities for scraping recipe sites.

The scraper now prefers fresh runs over persistent skip-memory so a previous
session does not make a new scrape look empty.
"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from recipe_scrapers import scrape_html
from usp.tree import sitemap_tree_for_homepage

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

RECIPE_PATH_HINTS = (
    "/recipe",
    "/recipes/",
    "/recipe/",
    "/cook/",
    "/food/",
    "/dish/",
    "/meal/",
)

RECIPE_SITEMAP_HINTS = (
    "recipe",
    "recipes",
    "post-sitemap",
    "posts",
)

NON_RECIPE_URL_HINTS = (
    "/tag/",
    "/tags/",
    "/category/",
    "/categories/",
    "/author/",
    "/page/",
    "/search/",
    "/wp-content/",
    "/feed",
    "/index.php",
)

FOOD_INDICATORS = {
    "chicken",
    "beef",
    "pork",
    "salmon",
    "shrimp",
    "tofu",
    "pasta",
    "rice",
    "salad",
    "soup",
    "pizza",
    "burger",
    "taco",
    "curry",
    "cake",
    "cookie",
    "bread",
    "muffin",
    "brownie",
    "lasagna",
    "steak",
    "noodle",
    "potato",
    "garlic",
}


def validate_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)
    except Exception:
        return False


def normalize_base_url(url: str) -> str:
    return url.rstrip("/")


def is_likely_recipe_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(hint in path for hint in RECIPE_PATH_HINTS) or any(word in path for word in FOOD_INDICATORS)


def _looks_like_non_recipe_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    if any(hint in path for hint in NON_RECIPE_URL_HINTS):
        return True
    slug = path.strip("/").split("/")
    if not slug:
        return True
    # Archive/listing pages are usually very shallow.
    if len(slug) <= 1 and not is_likely_recipe_url(url):
        return True
    return False


def _score_recipe_url(url: str) -> int:
    path = urlparse(url).path.lower()
    score = 0
    if any(hint in path for hint in RECIPE_PATH_HINTS):
        score += 6
    if any(word in path for word in FOOD_INDICATORS):
        score += 4
    if _looks_like_non_recipe_url(url):
        score -= 8

    slug_parts = [part for part in path.strip("/").split("/") if part]
    if len(slug_parts) >= 2:
        score += 2
    if len(slug_parts) >= 3:
        score += 1
    if re.search(r"/\d{4}/\d{2}/", path):
        score += 2
    if path.count("-") >= 2:
        score += 1
    return score


def is_valid_recipe_name(name: str) -> bool:
    cleaned = (name or "").strip()
    if not cleaned:
        return False
    if cleaned.lower() in {"unknown recipe", "home", "homepage"}:
        return False
    if len(cleaned) < 4:
        return False
    return True


def format_duration(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, int):
        return f"{value} mins"

    text = str(value).strip()
    iso_match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", text)
    if iso_match:
        hours = int(iso_match.group(1) or 0)
        minutes = int(iso_match.group(2) or 0)
        if hours and minutes:
            return f"{hours} hr {minutes} mins"
        if hours:
            return "1 hr" if hours == 1 else f"{hours} hrs"
        if minutes:
            return "1 min" if minutes == 1 else f"{minutes} mins"
    return text


def determine_benefit(name: str, time_text: str, ingredient_count: int | None, content: str) -> str:
    haystack = f"{name} {time_text} {content}".lower()
    if any(term in haystack for term in ("one pan", "one-pot", "sheet pan", "skillet")):
        return "One Pan"
    if any(term in haystack for term in ("vegan", "plant-based")):
        return "Vegan"
    if any(term in haystack for term in ("vegetarian", "meatless")):
        return "Vegetarian"
    if any(term in haystack for term in ("healthy", "high protein", "low carb", "protein")):
        return "Healthy"
    if any(term in haystack for term in ("meal prep", "make ahead", "freezer")):
        return "Meal Prep"
    if any(term in haystack for term in ("spicy", "hot honey", "chili", "jalapeno", "jalapeño")):
        return "Spicy"
    if ingredient_count and ingredient_count <= 5:
        return "Budget Friendly"

    minutes = extract_minutes(time_text)
    if minutes is not None and minutes <= 30:
        return "Quick Weeknight"
    return "Comfort Food" if any(term in haystack for term in ("creamy", "cozy", "comfort")) else "Quick Weeknight"


def extract_minutes(time_text: str) -> int | None:
    if not time_text:
        return None
    text = time_text.lower()
    hour_match = re.search(r"(\d+)\s*(?:hr|hrs|hour|hours)", text)
    min_match = re.search(r"(\d+)\s*(?:min|mins|minute|minutes)", text)
    hours = int(hour_match.group(1)) if hour_match else 0
    minutes = int(min_match.group(1)) if min_match else 0
    if not hour_match and not min_match:
        digits = re.search(r"(\d+)", text)
        return int(digits.group(1)) if digits else None
    return (hours * 60) + minutes


def _meta_content(soup: BeautifulSoup, **attrs: str) -> str:
    tag = soup.find("meta", attrs=attrs)
    return (tag.get("content", "") or "").strip() if tag else ""


def _get_json_ld_blocks(soup: BeautifulSoup) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict):
                blocks.append(item)
    return blocks


def _find_recipe_schema(soup: BeautifulSoup) -> dict[str, Any] | None:
    for item in _get_json_ld_blocks(soup):
        item_type = item.get("@type", [])
        if isinstance(item_type, str):
            item_type = [item_type]
        if "Recipe" in item_type:
            return item
        graph = item.get("@graph", [])
        if isinstance(graph, list):
            for child in graph:
                child_type = child.get("@type", [])
                if isinstance(child_type, str):
                    child_type = [child_type]
                if "Recipe" in child_type:
                    return child
    return None


def _extract_title(soup: BeautifulSoup, schema: dict[str, Any] | None) -> str:
    if schema and schema.get("name"):
        return str(schema["name"]).strip()

    title_selectors = [
        "h1.entry-title",
        "h1.post-title",
        "h1.recipe-title",
        "h1",
    ]
    for selector in title_selectors:
        node = soup.select_one(selector)
        text = node.get_text(" ", strip=True) if node else ""
        if is_valid_recipe_name(text):
            return text

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    title = re.split(r"[\-|·|•|:]", title)[0].strip()
    return title


def _extract_image_url(soup: BeautifulSoup, page_url: str, schema: dict[str, Any] | None) -> str:
    if schema:
        image = schema.get("image")
        if isinstance(image, str):
            return image
        if isinstance(image, list) and image:
            first = image[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get("url", "")
        if isinstance(image, dict):
            return image.get("url", "")

    for attrs in (
        {"property": "og:image"},
        {"name": "twitter:image"},
    ):
        value = _meta_content(soup, **attrs)
        if value:
            return urljoin(page_url, value)

    img = soup.find("img")
    if img and img.get("src"):
        return urljoin(page_url, img["src"])
    return ""


def _extract_ingredients(scraper: Any, schema: dict[str, Any] | None) -> tuple[list[str], str]:
    ingredients: list[str] = []
    try:
        ingredients = [item.strip() for item in scraper.ingredients() if item and item.strip()]
    except Exception:
        ingredients = []

    if not ingredients and schema:
        schema_ingredients = schema.get("recipeIngredient", [])
        if isinstance(schema_ingredients, list):
            ingredients = [str(item).strip() for item in schema_ingredients if str(item).strip()]

    return ingredients, ", ".join(ingredients[:5])


def _extract_description(scraper: Any, soup: BeautifulSoup, schema: dict[str, Any] | None) -> str:
    for getter in (
        lambda: scraper.description(),
        lambda: schema.get("description", "") if schema else "",
        lambda: _meta_content(soup, name="description"),
        lambda: _meta_content(soup, property="og:description"),
    ):
        try:
            value = getter()
        except Exception:
            value = ""
        if value:
            return str(value).strip()
    return ""


def _extract_method_snippet(scraper: Any) -> str:
    try:
        instructions = scraper.instructions()
    except Exception:
        instructions = ""

    if isinstance(instructions, list):
        return " ".join(str(step).strip() for step in instructions[:2] if step).strip()[:220]
    return str(instructions).strip()[:220]


def extract_with_recipe_scrapers(url: str, headers: dict | None = None) -> dict[str, Any] | None:
    headers = headers or DEFAULT_HEADERS
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
    except Exception as exc:
        print(f"[SCRAPER] Request failed for {url}: {exc}", flush=True)
        return None

    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    schema = _find_recipe_schema(soup)

    try:
        scraper = scrape_html(html, org_url=url)
    except TypeError:
        scraper = scrape_html(html, url)
    except Exception as exc:
        print(f"[SCRAPER] recipe-scrapers init failed for {url}: {exc}", flush=True)
        scraper = None

    title = ""
    prep_time = ""
    cook_time = ""
    total_time = ""

    if scraper:
        try:
            title = scraper.title() or ""
        except Exception:
            title = ""
        try:
            prep_time = format_duration(scraper.prep_time())
        except Exception:
            prep_time = ""
        try:
            cook_time = format_duration(scraper.cook_time())
        except Exception:
            cook_time = ""
        try:
            total_time = format_duration(scraper.total_time())
        except Exception:
            total_time = ""

    title = title or _extract_title(soup, schema)
    if not is_valid_recipe_name(title):
        return None

    ingredients, ingredient_names = _extract_ingredients(scraper, schema) if scraper else _extract_ingredients(_NullScraper(), schema)
    ingredient_count = len(ingredients) if ingredients else None
    description = _extract_description(scraper or _NullScraper(), soup, schema)
    method_snippet = _extract_method_snippet(scraper or _NullScraper())
    image_url = _extract_image_url(soup, url, schema)
    meta_keywords = _meta_content(soup, name="keywords")
    og_title = _meta_content(soup, property="og:title")

    time_value = total_time or " / ".join(part for part in (prep_time, cook_time) if part)
    benefit = determine_benefit(title, time_value, ingredient_count, f"{description} {method_snippet}")

    return {
        "name": title,
        "url": url,
        "prep_time": prep_time,
        "cook_time": cook_time,
        "total_time": total_time,
        "time": time_value,
        "ingredients": str(ingredient_count or ""),
        "ingredient_count": ingredient_count or "",
        "ingredient_names": ingredient_names,
        "benefit": benefit,
        "description": description,
        "method_snippet": method_snippet,
        "meta_keywords": meta_keywords,
        "meta_description": _meta_content(soup, name="description"),
        "og_title": og_title,
        "blog_content_sample": f"{description} {method_snippet}".strip(),
        "image_url": image_url,
    }


class _NullScraper:
    def description(self) -> str:
        return ""

    def instructions(self) -> str:
        return ""

    def ingredients(self) -> list[str]:
        return []


def fallback_homepage_scraping(base_url: str, max_recipes: int, headers: dict | None = None) -> list[dict[str, Any]]:
    headers = headers or DEFAULT_HEADERS
    try:
        response = requests.get(base_url, headers=headers, timeout=20)
        response.raise_for_status()
    except Exception as exc:
        print(f"[SCRAPER] Homepage fallback failed for {base_url}: {exc}", flush=True)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    candidates: list[str] = []
    for link in soup.find_all("a", href=True):
        candidate = urljoin(base_url, link["href"])
        if validate_url(candidate) and is_likely_recipe_url(candidate):
            candidates.append(candidate)

    deduped = list(dict.fromkeys(candidates))[: max_recipes * 2]
    recipes: list[dict[str, Any]] = []
    for url in deduped:
        recipe = extract_with_recipe_scrapers(url, headers=headers)
        if recipe:
            recipes.append(recipe)
        if len(recipes) >= max_recipes:
            break
        time.sleep(0.15)
    return recipes


def _extract_xml_urls(xml_text: str) -> tuple[list[str], list[str]]:
    page_urls: list[str] = []
    sitemap_urls: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return page_urls, sitemap_urls

    for element in root.iter():
        tag = element.tag.lower()
        if tag.endswith("loc") and element.text:
            value = element.text.strip()
            parent_tag = ""
            parent = None
            # ElementTree has no parent pointers, infer from root tag when possible.
            if root.tag.lower().endswith("sitemapindex"):
                parent_tag = "sitemap"
            elif root.tag.lower().endswith("urlset"):
                parent_tag = "url"
            if parent_tag == "sitemap":
                sitemap_urls.append(value)
            else:
                page_urls.append(value)
    return page_urls, sitemap_urls


def _common_sitemap_urls(base_url: str) -> list[str]:
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return [
        f"{origin}/robots.txt",
        f"{origin}/sitemap.xml",
        f"{origin}/sitemap_index.xml",
        f"{origin}/wp-sitemap.xml",
        f"{origin}/post-sitemap.xml",
        f"{origin}/recipe-sitemap.xml",
    ]


def _discover_sitemap_urls(base_url: str, headers: dict | None = None) -> list[str]:
    headers = headers or DEFAULT_HEADERS
    discovered: list[str] = []
    candidates = _common_sitemap_urls(base_url)

    robots_url = candidates[0]
    try:
        response = requests.get(robots_url, headers=headers, timeout=15)
        if response.ok:
            for line in response.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    if sitemap_url:
                        discovered.append(sitemap_url)
    except Exception:
        pass

    discovered.extend(candidates[1:])
    return list(dict.fromkeys(discovered))


def _discover_recipe_urls_from_xml(base_url: str, max_urls: int = 200, headers: dict | None = None) -> list[str]:
    headers = headers or DEFAULT_HEADERS
    sitemap_urls = _discover_sitemap_urls(base_url, headers=headers)
    queue = list(sitemap_urls)
    visited: set[str] = set()
    recipe_candidates: list[str] = []

    while queue and len(recipe_candidates) < max_urls * 3:
        sitemap_url = queue.pop(0)
        if sitemap_url in visited:
            continue
        visited.add(sitemap_url)
        try:
            response = requests.get(sitemap_url, headers=headers, timeout=20)
            response.raise_for_status()
        except Exception:
            continue

        page_urls, nested_sitemaps = _extract_xml_urls(response.text)
        for nested in nested_sitemaps:
            nested_lower = nested.lower()
            if any(hint in nested_lower for hint in RECIPE_SITEMAP_HINTS):
                queue.insert(0, nested)
            else:
                queue.append(nested)

        for url in page_urls:
            if validate_url(url):
                recipe_candidates.append(url)

    ranked_urls = sorted(
        {url for url in recipe_candidates if not _looks_like_non_recipe_url(url)},
        key=lambda item: (_score_recipe_url(item), len(urlparse(item).path)),
        reverse=True,
    )
    ranked_urls = [url for url in ranked_urls if _score_recipe_url(url) >= 2]
    return ranked_urls[:max_urls]


def _discover_recipe_urls(base_url: str, max_urls: int = 200) -> list[str]:
    scored_urls: list[str] = []

    try:
        tree = sitemap_tree_for_homepage(base_url)
        pages = list(tree.all_pages())
        scored_urls.extend(page.url for page in pages if page.url)
    except Exception as exc:
        print(f"[SCRAPER] USP sitemap discovery failed for {base_url}: {exc}", flush=True)

    try:
        scored_urls.extend(_discover_recipe_urls_from_xml(base_url, max_urls=max_urls, headers=DEFAULT_HEADERS))
    except Exception as exc:
        print(f"[SCRAPER] XML sitemap discovery failed for {base_url}: {exc}", flush=True)

    ranked_urls = sorted(
        {url for url in scored_urls if validate_url(url)},
        key=lambda item: (_score_recipe_url(item), len(urlparse(item).path)),
        reverse=True,
    )
    filtered_urls = [url for url in ranked_urls if _score_recipe_url(url) >= 2]
    return filtered_urls[:max_urls]


def scrape_recipes_from_website(
    base_url: str,
    max_recipes: int = 50,
    *,
    use_processed_memory: bool = False,
    reset_processed_on_empty: bool = True,
) -> list[dict[str, Any]]:
    base_url = normalize_base_url(base_url)
    print(f"[SCRAPER] Starting scrape for {base_url}", flush=True)

    if not validate_url(base_url):
        return []

    try:
        recipe_urls = _discover_recipe_urls(base_url, max_urls=max_recipes * 6)
    except Exception as exc:
        print(f"[SCRAPER] Sitemap discovery failed for {base_url}: {exc}", flush=True)
        recipe_urls = []

    if not recipe_urls:
        return fallback_homepage_scraping(base_url, max_recipes, DEFAULT_HEADERS)

    selected_urls = recipe_urls
    if use_processed_memory:
        try:
            from utils.sitemap_memory import has_url
        except ImportError:
            from sitemap_memory import has_url

        filtered = [url for url in recipe_urls if not has_url(url)]
        if not filtered and reset_processed_on_empty:
            print("[SCRAPER] All sitemap URLs were previously remembered; retrying fresh.", flush=True)
        else:
            selected_urls = filtered

    recipes: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_urls: set[str] = set()

    try:
        from utils.sitemap_memory import mark_url
    except ImportError:
        from sitemap_memory import mark_url

    for url in selected_urls:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        recipe = extract_with_recipe_scrapers(url, headers=DEFAULT_HEADERS)
        if not recipe:
            continue

        key = recipe["name"].strip().lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        recipes.append(recipe)

        if use_processed_memory:
            mark_url(url)

        if len(recipes) >= max_recipes:
            break
        time.sleep(0.15)

    return recipes


def scrape_recipes_from_website_with_memory(
    base_url: str,
    max_recipes: int = 50,
    *,
    use_processed_memory: bool = False,
) -> list[dict[str, Any]]:
    return scrape_recipes_from_website(
        base_url,
        max_recipes=max_recipes,
        use_processed_memory=use_processed_memory,
        reset_processed_on_empty=True,
    )


def get_all_recipe_urls(base_url: str, max_urls: int = 30) -> list[str]:
    if not validate_url(base_url):
        return []
    try:
        return _discover_recipe_urls(normalize_base_url(base_url), max_urls=max_urls)
    except Exception:
        return []


def scrape_recipes_from_urls(urls: list[str]) -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for url in urls:
        if not validate_url(url):
            continue
        recipe = extract_with_recipe_scrapers(url, headers=DEFAULT_HEADERS)
        if not recipe:
            continue
        key = recipe["name"].strip().lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        recipes.append(recipe)
    return recipes
