# Pinterest Factory — Product & Technical Spec

## 1) Purpose
Pinterest Factory is a Streamlit dashboard that helps food bloggers batch-produce Pinterest-ready pin copy and assets from existing recipe content.

- **Primary job-to-be-done**: turn a batch of recipe URLs (or manual entries) into:
  - short, high-performing **hook text** variants (multiple angles per recipe)
  - a **Pinterest SEO description**
  - **pin images** generated from recipe photos + templates
  - optional **export to Notion** for tracking production workflow

## 2) Target users & use cases
- **Food blogger / recipe site owner**: wants faster pin production for a backlog of posts.
- **Content VA / social media manager**: needs a repeatable workflow that produces consistent output and can be tracked in Notion/Canva.

Typical flow:
1. Paste a blog homepage URL → select recipes to include (or fill in a few manually).
2. Generate hooks + description for each recipe.
3. Generate and download pins (ZIP), or export copy for Canva bulk-create.
4. Push everything into a Notion database to track “To Canva → Scheduled → Posted”.

## 3) Scope (what this project is)
### In scope today
- **Step 1 — Batch intake** (`components/intake.py`)
  - Manual entry for 1–10 recipes
  - Optional web scraping to discover recipes from a site and load selections into the batch
  - Batch “lock” concept so later steps have stable inputs
  - Nutrition facts extraction is supported for scraped recipes (calories/protein/carbs/fat) when available
- **Step 2 — AI copy engine** (`components/ai_engine.py`, `utils/groq_client.py`)
  - Groq API connection check using `GROQ_API_KEY`
  - Generate **5 hooks per recipe** across fixed “angles”
  - Generate **1 short SEO description** per recipe
  - Inline editing with persistence in Streamlit session state
- **Step 3 — Pin generation** (`components/pin_generator.py`)
  - Fetch a recipe image via `og:image`/`twitter:image` scraping from the recipe URL
  - Generate 1000×1500 pins using 3 built-in Pillow templates
  - Preview grid + ZIP download of PNG outputs
- **Step 4 — Notion sync** (`components/notion_sync.py`)
  - Push one Notion page per (recipe × hook angle)
  - Requires `NOTION_TOKEN` and `NOTION_DATABASE_ID`
  - Includes a detailed setup guide for required Notion schema

### Explicit non-goals (for now)
- Posting or scheduling directly to Pinterest
- Multi-user authentication / shared workspaces
- Full CMS integration (WordPress plugin, etc.)
- Pixel-perfect design tooling (this stays “good enough” template-based unless roadmap says otherwise)

## 4) Success criteria
### Product success
- A user can go from “site URL” → “downloadable copy + pins” in under ~10 minutes for a 5–10 recipe batch.
- Output is “usable without rewriting” (minor edits only) and consistent with Pinterest best practices:
  - hooks are short (target ≤ 8 words)
  - descriptions are short (target ≤ 150 chars preview-friendly)

### Engineering success
- Scraper is resilient across common food blog setups (sitemap + schema.org Recipe JSON-LD).
- Groq failures degrade gracefully (fallback hooks/description), so the workflow doesn’t dead-end.
- Exports are deterministic and traceable (stable filenames, consistent row structure).

## 5) Current architecture
### High-level components
- **UI**: Streamlit in `app.py` (tab router; session state is the “backend”)
- **Scraping**: `utils/web_scraper.py` (sitemap discovery + recipe extraction + heuristics)
- **LLM**: `utils/groq_client.py` (Groq Chat Completions; prompt templates; fallback outputs)
- **Pins**: `components/pin_generator.py` (image fetch + Pillow-based templates + ZIP export)
- **Notion**: `components/notion_sync.py` (Notion API calls; database schema expectations)

### Session state (core data contract)
Defined/seeded in `app.py`:
- `batch_locked: bool`
- `recipes: list[dict]`
- `hooks: dict[str, dict[str, str]]` (recipe name → angle → hook text)
- `descriptions: dict[str, str]` (recipe name → description)
- `notion_log: list[str]`
- `ai_generated: bool`

Additional keys used by individual tabs:
- Intake: `num_recipes`, `recipe_data`, `scraped_recipes`, widget keys like `name_0`, `url_0`, etc.
- Pin generation: `generated_pins`

### Primary workflow (data flow)
1. **Intake** produces `recipes[]` (each recipe dict typically has: `name`, `url`, `time`, `ingredients`, `benefit`; scraped recipes may include `nutrition_facts`).
2. **AI engine** reads `recipes[]` and populates `hooks[name][angle]` + `descriptions[name]`.
3. **Pin generation** reads `recipes[]` + `hooks` and generates images.
4. **Notion sync** reads `recipes[]` + `hooks` + `descriptions` and creates Notion pages.

## 6) External dependencies & configuration
### Required (for AI features)
- `GROQ_API_KEY`
- Optional: `GROQ_MODEL` (default `llama-3.1-8b-instant`)

### Optional
- `NOTION_TOKEN`
- `NOTION_DATABASE_ID`

### Python deps (summary)
See `requirements.txt` for the source of truth.
- Streamlit, Pandas
- Requests, BeautifulSoup
- Groq client
- Pillow
- ultimate-sitemap-parser, recipe-scrapers
- Selenium + webdriver-manager (used by `wake_app.py` to “wake” Streamlit Cloud apps)

## 7) Outputs (what the app produces)
- **Hook variants**: 5 angles per recipe, editable
- **SEO descriptions**: 1 per recipe, editable
- **Pin images**: PNG pins (1000×1500) downloadable as a ZIP
- **Notion rows**: one row per hook
- **CSV export**: there is an exporter module at `components/export.py` that formats Canva Bulk Create CSVs, but it is not currently wired into the main `app.py` router

## 8) Known gaps / tech debt (current repo state)
These are observations from the codebase today that are worth tracking:
- **Export tab wiring**: `components/export.py` exists but is not routed from `app.py`, so users may not see Canva bulk export unless integrated.
- **Angles source-of-truth**: `components/notion_sync.py` imports `ANGLES` from `utils.ollama_client`, while the app’s AI path uses `utils/groq_client.ANGLES`. This can drift if one changes.
- **Branding stamp hardcode**: `components/pin_generator.py` stamps `nobscooking.com` directly, which should become configurable.
- **Debug prints**: pin generation uses many `print("DEBUG: ...")` statements; useful during development but noisy in production logs.

## 9) Roadmap (future improvements)
This is intentionally opinionated and grouped by “what unlocks the next level”.

### Near-term (quality-of-life, 1–2 sessions)
- **Wire up Canva export in the UI**: add a “Step 3b: Export CSV” or include `render_export()` in the Step 3 tab.
- **Single source of truth for `ANGLES`**: define once (e.g., `utils/constants.py`) and import everywhere.
- **Make branding configurable**: `BRAND_DOMAIN`, `BRAND_COLOR`, “show stamp” toggle.
- **Better filename strategy for pins**: slugify recipe + angle; keep stable ordering.
- **Cache recipe image fetches**: avoid re-downloading across reruns; handle timeouts more gracefully.

### Medium-term (capability upgrades)
- **Template system**: allow users to choose from templates + tweak colors/font sizes safely.
- **Better image selection**: pick the largest/most “hero” image; fallback to schema.org `image` field when present.
- **Scraping UX**: show scrape progress and allow filtering (by category, keyword, “has nutrition facts”, etc.).
- **Prompt controls**: user-selectable tone/voice presets; per-site style profiles.
- **Batch persistence**: save/load batches from disk (local) or a lightweight DB (SQLite) so work survives browser refreshes.

### Longer-term (automation + scale)
- **Pinterest scheduler integration** (optional): export-ready board/metadata templates or API integration if feasible.
- **Multi-account / multi-brand support**: profiles for multiple sites/brands with separate settings and templates.
- **Metrics loop**: track pin performance (impressions/clicks) and recommend which angles/templates to reuse.

## 10) Milestones (definition of done)
Suggested checkpoints you can mark off:
- **M0 — Usable MVP**: intake → generate hooks/desc → export copy OR pins without errors for a 5-recipe batch.
- **M1 — Production-ready exports**: CSV export is visible, stable, and validated; Notion sync is robust.
- **M2 — Custom branding + templates**: non-hardcoded branding; user-selectable template options.
- **M3 — Persistence**: saved batches, reproducible reruns, minimal accidental state loss.

## 11) Notes for contributors
- **Keep the workflow linear**: later steps should guard on earlier steps being complete (`batch_locked`, hooks present, etc.).
- **Prefer graceful degradation**: if a feature depends on external APIs (Groq/Notion), it should fail with clear guidance and preserve the rest of the workflow.

## 12) Keeping this spec updated (process)
`spec.md` is treated as a **living contract** between the code and the intended product. Update it in the same change whenever you modify:

- **User-visible behavior**: new tabs/steps, changed UX, new outputs
- **Data contracts**: session state keys, recipe dict schema, hook/angle formats
- **Integrations/config**: env vars, secrets, external APIs (Groq/Notion/scraping)
- **Exports**: CSV columns, file naming, pin dimensions/templates
- **Roadmap**: when an item is started, shipped, or de-scoped
