"""
Pinterest intake workspace.
"""

from __future__ import annotations

import traceback

import pandas as pd
import streamlit as st

from utils.sitemap_memory import clear_all_urls, get_processed_count
from utils.web_scraper import ScraperInputError, scrape_recipes_from_website_with_memory, validate_url

BENEFITS = [
    "Quick Weeknight",
    "High Protein",
    "Budget Friendly",
    "No Oven",
    "One Pan",
    "Meal Prep",
    "Vegan",
    "Vegetarian",
    "Comfort Food",
    "Date Night",
    "Healthy",
    "Spicy",
    "Custom...",
]


def _init_state() -> None:
    defaults = {
        "num_recipes": 5,
        "recipe_data": [],
        "show_scraper": True,
        "scraped_recipes": [],
        "scrape_source_url": "",
        "scrape_message": "",
        "selected_recipe_metadata": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _clear_batch() -> None:
    for key, value in {
        "recipe_data": [],
        "recipes": [],
        "hooks": {},
        "descriptions": {},
        "hook_packages": {},
        "pin_descriptions": {},
        "generated_pins": [],
        "ai_generated": False,
        "batch_locked": False,
        "num_recipes": 5,
        "scraped_recipes": [],
        "scrape_source_url": "",
        "scrape_message": "",
        "selected_recipe_metadata": {},
    }.items():
        st.session_state[key] = value


def _load_selected(selections: list[dict]) -> None:
    for i in range(10):
        for key_suffix in ("name_", "url_", "time_", "ing_", "benefit_sel_", "benefit_custom_"):
            st.session_state.pop(f"{key_suffix}{i}", None)

    for i, recipe in enumerate(selections):
        st.session_state[f"name_{i}"] = recipe.get("name", "")
        st.session_state[f"url_{i}"] = recipe.get("url", "")
        st.session_state[f"time_{i}"] = recipe.get("time", "")
        st.session_state[f"ing_{i}"] = recipe.get("ingredients", "")
        st.session_state[f"benefit_sel_{i}"] = recipe.get("benefit", BENEFITS[0])

    st.session_state.selected_recipe_metadata = {
        f"{recipe.get('name', '').strip().lower()}::{recipe.get('url', '').strip()}": recipe.copy()
        for recipe in selections
    }
    st.session_state.recipe_data = selections.copy()
    st.session_state.num_recipes = max(len(selections), 1)
    st.session_state.batch_locked = False
    st.session_state.ai_generated = False
    st.session_state.show_scraper = False
    st.session_state.scraped_recipes = []


def _render_scraped_results(recipes: list[dict]) -> None:
    if not recipes:
        return

    st.subheader("Scraped Recipes")
    st.caption("Fresh results from the current scrape run.")

    options: dict[str, dict] = {}
    for recipe in recipes:
        label = f"{recipe.get('name', 'Untitled')} · {recipe.get('time', 'No time found')}"
        options[label] = recipe

    selected_labels = st.multiselect(
        "Select recipes to load",
        options=list(options.keys()),
        key="recipe_multiselect",
    )

    selections = [options[label] for label in selected_labels]
    st.write(f"**{len(selections)} recipes selected**")

    if st.button("Load selected into batch", disabled=not selections, key="load_scraped_btn"):
        _load_selected(selections)
        st.success(f"Loaded {len(selections)} recipe(s) into the batch form.")
        st.rerun()


def render_intake() -> None:
    _init_state()

    st.subheader("Pinterest Batch Intake")
    st.caption("Scrape a food site or enter recipes manually, then lock the batch for Pinterest copy and pin generation.")

    with st.expander("🌐 Scrape Recipes from Website", expanded=st.session_state.show_scraper):
        st.caption("Fresh-run scraping is the default so old sitemap memory does not block new recipe discovery.")

        website_url = st.text_input(
            "Website URL",
            key="pinterest_scrape_url",
            placeholder="https://yourfoodblog.com",
            help="Enter the main domain for the recipe blog you want to scrape.",
        )

        col_a, col_b, col_c = st.columns([2, 2, 1])
        with col_a:
            max_recipes = st.slider("Max recipes", min_value=5, max_value=50, value=20, step=5)
        with col_b:
            use_memory = st.checkbox(
                "Use saved scraper memory",
                value=False,
                help="Leave this off for a clean scrape. Turn it on only if you want to skip URLs already scraped before.",
            )
        with col_c:
            st.metric("Saved URLs", get_processed_count())

        col_scrape, col_reset = st.columns([3, 1])
        with col_scrape:
            if st.button("🔍 Scrape Recipes", disabled=not website_url, use_container_width=True):
                if not validate_url(website_url):
                    st.error("Please enter a valid URL including `https://`.")
                else:
                    st.session_state.scraped_recipes = []
                    st.session_state.scrape_source_url = website_url
                    with st.spinner("Scraping recipes from website..."):
                        try:
                            scraped = scrape_recipes_from_website_with_memory(
                                website_url,
                                max_recipes=max_recipes,
                                use_processed_memory=use_memory,
                            )
                        except ScraperInputError as exc:
                            st.error(str(exc))
                        except Exception as exc:
                            st.error(f"Scraping failed: {exc}")
                            with st.expander("Debug details"):
                                st.code(traceback.format_exc())
                        else:
                            st.session_state.show_scraper = True
                            st.session_state.scraped_recipes = scraped
                            if scraped:
                                st.session_state.scrape_message = f"Found {len(scraped)} recipes from {website_url}."
                            else:
                                st.session_state.scrape_message = (
                                    "No recipes found in this run. Try leaving memory off, checking the domain, "
                                    "or scraping a recipe subdirectory."
                                )
                            st.rerun()

        with col_reset:
            if st.button("🧹 Reset Memory", use_container_width=True):
                clear_all_urls()
                st.success("Saved scraper memory cleared.")
                st.rerun()

        if st.session_state.scrape_message:
            if st.session_state.scraped_recipes:
                st.success(st.session_state.scrape_message)
            else:
                st.warning(st.session_state.scrape_message)

        _render_scraped_results(st.session_state.scraped_recipes)

    st.divider()

    col_left, col_right = st.columns([2, 1])
    with col_left:
        st.slider(
            "Number of recipes in this batch",
            min_value=1,
            max_value=10,
            step=1,
            key="num_recipes",
        )
    with col_right:
        st.button("🗑 Clear batch", use_container_width=True, on_click=_clear_batch)

    st.divider()

    form_data: list[dict] = []
    for i in range(st.session_state.num_recipes):
        st.markdown(f"**Recipe {i + 1}**")
        c1, c2 = st.columns([2, 2])
        c3, c4, c5 = st.columns([1, 1, 2])

        name = c1.text_input("Recipe name", key=f"name_{i}", placeholder="e.g. Garlic Butter Pasta")
        url = c2.text_input("URL (optional)", key=f"url_{i}", placeholder="https://example.com/recipe")
        time_value = c3.text_input("Cook time", key=f"time_{i}", placeholder="25 mins")
        ingredients = c4.text_input("Ingredient count", key=f"ing_{i}", placeholder="7")

        benefit_sel = c5.selectbox("Key benefit / tag", options=BENEFITS, index=0, key=f"benefit_sel_{i}")
        benefit = c5.text_input("Enter custom tag", key=f"benefit_custom_{i}") if benefit_sel == "Custom..." else benefit_sel

        form_data.append(
            {
                "name": name.strip(),
                "url": url.strip(),
                "time": time_value.strip(),
                "ingredients": ingredients.strip(),
                "benefit": benefit.strip(),
            }
        )

        if i < st.session_state.num_recipes - 1:
            st.divider()

    st.divider()
    col_lock, col_status = st.columns([1, 3])
    with col_lock:
        lock_clicked = st.button("🔒 Lock Batch", type="primary", use_container_width=True)

    if lock_clicked:
        valid = [recipe for recipe in form_data if recipe["name"]]
        if not valid:
            st.error("Add at least 1 recipe name before locking.")
        else:
            metadata_map = st.session_state.get("selected_recipe_metadata", {})
            enriched = []
            for recipe in valid:
                key = f"{recipe.get('name', '').strip().lower()}::{recipe.get('url', '').strip()}"
                base = metadata_map.get(key, {}).copy()
                base.update(recipe)
                enriched.append(base)

            st.session_state.recipes = enriched
            st.session_state.recipe_data = enriched
            st.session_state.batch_locked = True
            st.session_state.ai_generated = False
            st.session_state.hooks = {}
            st.session_state.descriptions = {}
            st.session_state.hook_packages = {}
            st.session_state.pin_descriptions = {}
            with col_status:
                st.success(f"Batch locked with {len(enriched)} recipe(s).")

    if st.session_state.batch_locked and st.session_state.get("recipes"):
        with col_status:
            st.info("Batch locked and ready for the Pinterest AI copy engine.")

        preview_df = pd.DataFrame(st.session_state.recipes)[["name", "time", "ingredients", "benefit", "url"]]
        preview_df.columns = ["Recipe", "Cook Time", "Ingredients", "Benefit", "URL"]
        st.subheader("Locked Batch Preview")
        st.dataframe(preview_df, use_container_width=True, hide_index=True)
