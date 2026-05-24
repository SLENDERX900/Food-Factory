"""
components/notion_sync.py — Tab 4: Notion Tracker Sync
Pushes each generated pin to a Notion database.
Reads NOTION_TOKEN and NOTION_DATABASE_ID from .env
"""

import os
import time
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st
from utils.scheduler import build_schedule_slots, schedule_pin, update_notion_item_scheduled

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")
NOTION_API_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"


def _notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION,
    }


def _check_notion_auth() -> tuple[bool, str]:
    """Verify token and database exist."""
    if not NOTION_TOKEN:
        return False, "NOTION_TOKEN not set in .env"
    if not NOTION_DATABASE_ID:
        return False, "NOTION_DATABASE_ID not set in .env"

    try:
        resp = requests.get(
            f"{NOTION_BASE}/databases/{NOTION_DATABASE_ID}",
            headers=_notion_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            db_title = resp.json().get("title", [{}])[0].get("plain_text", "Untitled")
            return True, f"Connected to database: **{db_title}**"
        elif resp.status_code == 401:
            return False, "Invalid NOTION_TOKEN — check your integration token"
        elif resp.status_code == 404:
            return False, "Database not found — check NOTION_DATABASE_ID and that your integration has access"
        else:
            return False, f"Notion API error {resp.status_code}: {resp.text[:200]}"
    except requests.ConnectionError:
        return False, "Cannot reach Notion API — check internet connection"
    except Exception as e:
        return False, str(e)


def _create_page(recipe_name: str, angle: str, hook: str, description: str, recipe_url: str) -> tuple[bool, str, str]:
    """Create one Notion page (row) for a single pin."""
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Recipe Name": {
                "title": [{"text": {"content": recipe_name}}]
            },
            "Hook": {
                "rich_text": [{"text": {"content": hook[:2000]}}]
            },
            "Angle": {
                "select": {"name": angle}
            },
            "Description": {
                "rich_text": [{"text": {"content": description[:2000]}}]
            },
            "Status": {
                "select": {"name": "To Canva"}
            },
            "Recipe URL": {
                "url": recipe_url if recipe_url else None
            },
        },
    }

    # Remove null URL property — Notion rejects null url
    if not recipe_url:
        del payload["properties"]["Recipe URL"]

    try:
        resp = requests.post(
            f"{NOTION_BASE}/pages",
            headers=_notion_headers(),
            json=payload,
            timeout=15,
        )
        if resp.status_code in (200, 201):
            page_id = resp.json().get("id", "")
            return True, f"✅ Created: **{recipe_name}** · {angle} (ID: {page_id[:8]}...)", page_id
        else:
            error = resp.json().get("message", resp.text[:200])
            return False, f"❌ Failed: **{recipe_name}** · {angle} — {error}", ""
    except Exception as e:
        return False, f"❌ Error: **{recipe_name}** · {angle} — {e}", ""


def render_notion_sync():
    st.subheader("Notion Tracker Sync")
    st.caption("Push all generated pins to your Notion database as individual rows. Use Scheduler Hub for the shared publishing queue.")

    # ── Auth check ────────────────────────────────────────────────────────────
    auth_ok, auth_msg = _check_notion_auth()
    if auth_ok:
        st.success(f"✅ Notion auth OK · {auth_msg}")
    else:
        st.error(f"❌ Notion not configured — {auth_msg}")

        with st.expander("📖 How to set up Notion integration", expanded=True):
            render_notion_setup_guide()
        return

    st.divider()

    # ── Guard checks ──────────────────────────────────────────────────────────
    if not st.session_state.get("batch_locked") or not st.session_state.get("recipes"):
        st.warning("⚠️ No batch locked. Go to **Step 1** first.")
        return

    if not st.session_state.get("hooks"):
        st.warning("⚠️ No hooks generated yet. Go to **Step 2** first.")
        return

    recipes = st.session_state.recipes
    hooks = st.session_state.hooks
    descriptions = st.session_state.descriptions

    # Count total pins to push
    total_pins = sum(len(hooks.get(r["name"], {})) for r in recipes)

    # ── Sync controls ─────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns([1, 1, 2])
    col1.metric("Recipes", len(recipes))
    col2.metric("Pins to push", total_pins)

    st.divider()

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        sync_clicked = st.button(
            "🗂️ Sync to Notion",
            type="primary",
            use_container_width=True,
        )
    with col_info:
        st.caption(
            "Creates one Notion page per hook. "
            "Each page gets: Recipe Name, Hook, Angle, Description, Status = 'To Canva', URL."
        )

    # ── Sync execution ────────────────────────────────────────────────────────
    if sync_clicked:
        st.session_state.notion_log = []
        st.session_state.notion_pages = {}
        progress = st.progress(0, text="Syncing to Notion...")
        log_placeholder = st.empty()

        completed = 0
        for recipe in recipes:
            name = recipe["name"]
            url = recipe.get("url", "")
            desc = descriptions.get(name, "")
            recipe_hooks = hooks.get(name, {})

            for angle, hook_text in recipe_hooks.items():
                if not hook_text.strip():
                    continue
                success, msg, page_id = _create_page(name, angle, hook_text, desc, url)
                st.session_state.notion_log.append(msg)
                if success and page_id:
                    st.session_state.notion_pages[f"{name}::{angle}"] = page_id
                completed += 1
                pct = int((completed / total_pins) * 100)
                progress.progress(pct, text=f"Syncing {name} · {angle}...")
                log_placeholder.info(f"Last: {msg}")
                time.sleep(0.35)  # Notion API rate limit: ~3 req/sec

        progress.progress(100, text="Sync complete!")
        successes = len([l for l in st.session_state.notion_log if "✅" in l])
        failures = len([l for l in st.session_state.notion_log if "❌" in l])
        log_placeholder.empty()

        if failures == 0:
            st.success(f"✅ All {successes} pins synced to Notion successfully.")
        else:
            st.warning(f"Sync complete — {successes} succeeded, {failures} failed.")

    st.divider()
    st.subheader("Pinterest Scheduling")
    st.caption("Schedule pins to Pinterest and update the related Notion rows to `Scheduled`.")

    total_packages = sum(len(st.session_state.get("hook_packages", {}).get(r["name"], [])) for r in recipes)
    col_sched1, col_sched2, col_sched3 = st.columns(3)
    with col_sched1:
        default_date = (datetime.now(timezone.utc) + timedelta(days=1)).date()
        schedule_start_date = st.date_input("Start date (UTC)", value=default_date, key="schedule_start_date")
    with col_sched2:
        posts_per_day = st.slider("Posts per day", min_value=1, max_value=6, value=2, step=1, key="posts_per_day")
    with col_sched3:
        first_hour = st.slider("First post hour UTC", min_value=0, max_value=23, value=14, step=1, key="first_post_hour_utc")

    if st.button("📅 Schedule Pins + Mark Notion Scheduled", use_container_width=True):
        packages = st.session_state.get("hook_packages", {})
        notion_pages = st.session_state.get("notion_pages", {})
        pin_descriptions = st.session_state.get("pin_descriptions", {})
        schedule_log = []
        slots = build_schedule_slots(
            max(total_packages, 1),
            posts_per_day=posts_per_day,
            start_date=schedule_start_date,
            first_hour_utc=first_hour,
        )
        idx = 0
        for recipe in recipes:
            name = recipe["name"]
            for pkg in packages.get(name, [])[:5]:
                angle = pkg.get("angle", "")
                hook = pkg.get("hook", "")
                desc = pin_descriptions.get(name, {}).get(angle) or pkg.get("description", "")
                image_url = recipe.get("image_url", "") or recipe.get("url", "")
                slot = slots[idx % len(slots)]
                ok, sched_msg = schedule_pin(hook, desc, recipe.get("url", ""), image_url, slot)
                if ok:
                    page_id = notion_pages.get(f"{name}::{angle}")
                    if page_id:
                        n_ok, n_msg = update_notion_item_scheduled(page_id, slot)
                        status = n_msg if n_ok else f"update failed ({n_msg})"
                        schedule_log.append(f"{name} · {angle}: Pinterest scheduled ({sched_msg}); Notion {status}")
                    else:
                        schedule_log.append(f"{name} · {angle}: Pinterest scheduled ({sched_msg}); Notion page missing")
                else:
                    schedule_log.append(f"{name} · {angle}: schedule failed ({sched_msg})")
                idx += 1
        st.session_state.schedule_log = schedule_log

    if st.session_state.get("schedule_log"):
        st.subheader("Scheduling log")
        for line in st.session_state.schedule_log:
            st.write(line)

    # ── Show sync log ─────────────────────────────────────────────────────────
    if st.session_state.get("notion_log"):
        st.subheader("Sync log")
        successes = [l for l in st.session_state.notion_log if "✅" in l]
        failures = [l for l in st.session_state.notion_log if "❌" in l]

        if successes:
            with st.expander(f"✅ Successful ({len(successes)})", expanded=len(failures) == 0):
                for msg in successes:
                    st.markdown(msg)

        if failures:
            with st.expander(f"❌ Failed ({len(failures)})", expanded=True):
                for msg in failures:
                    st.markdown(msg)
                st.caption("Common causes: property name mismatch, Select option not in database, rate limit hit.")

    st.divider()

    # Setup guide always accessible
    with st.expander("📖 Notion database setup guide"):
        render_notion_setup_guide()


def render_notion_setup_guide():
    st.markdown("""
### Notion Database Setup — exact property configuration

Your Notion database must have these **exact property names and types**.
Capitalisation matters. Copy the names exactly as shown.

---

#### Required properties

| Property name | Type | Notes |
|---|---|---|
| `Recipe Name` | **Title** | Every Notion database has this by default — just rename it |
| `Hook` | **Text** (Rich text) | The pin hook text |
| `Angle` | **Select** | Dynamic angles based on recipe content (e.g., Lightning-Fast, Protein-Packed, Minimal-Cleanup) |
| `Description` | **Text** (Rich text) | SEO description |
| `Status` | **Select** | Add options: To Canva, In Canva, Queued, Reminder Set, Scheduled, Posted, Needs Review |
| `Recipe URL` | **URL** | Recipe page link |
| `Scheduled At` | **Date** | Optional but recommended for Pinterest scheduling sync |
| `Platform` | **Select** | Pinterest, Reddit |
| `Destination` | **Text** (Rich text) | Board or subreddit |
| `Job ID` | **Text** (Rich text) | Internal scheduler job id |
| `Post Mode` | **Select** | Auto, Manual Reminder |
| `Platform Post ID` | **Text** (Rich text) | Pinterest response id if available |
| `Last Error` | **Text** (Rich text) | Sync or scheduling error details |

---

#### Step-by-step setup

**1. Create a new full-page database in Notion**
- New page → `/table` → Full page
- Name it: `Pinterest Factory`

**2. Rename the default `Name` column to `Recipe Name`**
- Click the column header → Rename

**3. Add each property above**
- Click `+` at the right of the column headers
- Select the correct type for each

**4. For `Angle` Select — these are dynamically generated based on recipe:**
Common examples include:
- `Lightning-Fast` · `Effortless` · `Health-Boost`
- `Protein-Packed` · `Texture-Perfect` · `Minimal-Cleanup`
- `Carb-Comfort` · `Family-Approved` · `Slow-Cooked`
- `Big-Flavor` · `Fresh-Bright` · `Budget-Smart`

_Angles are determined by recipe characteristics + Pinterest trends_

**5. For `Status` Select — add these options:**
- `To Canva`
- `In Canva`
- `Queued`
- `Reminder Set`
- `Scheduled`
- `Posted`
- `Needs Review`

---

#### Connect your integration

**1. Create an integration**
- Go to [notion.so/my-integrations](https://www.notion.so/my-integrations)
- Click `+ New integration`
- Name: `Pinterest Factory`
- Capabilities: Read content, Update content, Insert content
- Copy the **Internal Integration Token** → paste into `.env` as `NOTION_TOKEN`

**2. Share the database with your integration**
- Open your Pinterest Factory database in Notion
- Click `...` (top right) → `Connections` → find your integration → connect it

**3. Get the Database ID**
- Open the database as a full page
- Copy the URL — it looks like: `https://notion.so/yourworkspace/`**`abc123def456...`**`?v=...`
- The 32-character string between `/` and `?v=` is your Database ID
- Paste it into `.env` as `NOTION_DATABASE_ID`

---

#### .env file

```
NOTION_TOKEN=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
    """)
