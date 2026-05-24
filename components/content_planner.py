"""
Content Planner workspace.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from utils.groq_client import generate_hook_packages
from utils.post_scheduler import add_job
from utils.rag_memory import query_similar_market_signals
from utils.voice_profiles import list_profiles, profile_to_prompt_context
from utils.notion_planner import notion_enabled, create_schedule_entry
from utils.scheduler import build_schedule_slots


def _selected_profile_context() -> str:
    profiles = list_profiles()
    active_name = st.session_state.get("active_voice_profile", "")
    profile = next((item for item in profiles if item.get("name") == active_name), None)
    return profile_to_prompt_context(profile)


def _sync_planned_job_to_notion(job: dict) -> None:
    if not notion_enabled():
        return
    ok, _, page_id = create_schedule_entry(job)
    if ok and page_id:
        job["notion_page_id"] = page_id


def _queue_plan_to_scheduler(
    plan_rows: list[dict],
    pinterest_packages: dict[str, list[dict]],
    reddit_drafts: list[dict],
    start_date,
    posts_per_day: int,
    first_hour: int,
) -> tuple[int, int]:
    pinterest_posts = []
    reddit_posts = []

    for row in plan_rows:
        recipe_name = row.get("Recipe", "")
        packages = pinterest_packages.get(recipe_name, [])
        if packages:
            package = packages[0]
            pinterest_posts.append(
                {
                    "recipe_name": recipe_name,
                    "title": package.get("hook", ""),
                    "body": package.get("description", ""),
                    "destination": row.get("Pinterest Destination", "") or "Pinterest board",
                    "source_url": row.get("Recipe URL", ""),
                    "image_url": row.get("Image URL", "") or row.get("Recipe URL", ""),
                    "metadata": {
                        "angle": package.get("angle", ""),
                        "campaign_intent": row.get("Intent", ""),
                        "planning_window": row.get("Window", ""),
                    },
                }
            )

    for draft in reddit_drafts:
        reddit_posts.append(
            {
                "recipe_name": draft.get("recipe_name", ""),
                "title": draft.get("title", ""),
                "body": draft.get("body", ""),
                "destination": draft.get("subreddit", "") or "set-subreddit",
                "source_url": draft.get("source_url", ""),
                "image_url": "",
                "metadata": {
                    "query": draft.get("query", ""),
                    "kind": draft.get("kind", "self"),
                    "campaign_intent": next((row.get("Intent", "") for row in plan_rows if row.get("Recipe", "") == draft.get("recipe_name", "")), ""),
                },
            }
        )

    all_posts = [("pinterest", post) for post in pinterest_posts] + [("reddit", post) for post in reddit_posts]
    slots = build_schedule_slots(
        len(all_posts),
        start_date=start_date,
        posts_per_day=posts_per_day,
        first_hour_utc=first_hour,
    )

    pinterest_count = 0
    reddit_count = 0
    for idx, (platform, post) in enumerate(all_posts):
        job = add_job(platform=platform, scheduled_for=slots[idx], **post)
        _sync_planned_job_to_notion(job)
        if platform == "pinterest":
            pinterest_count += 1
        else:
            reddit_count += 1
    return pinterest_count, reddit_count


def render_content_planner() -> None:
    st.subheader("Content Planner")
    st.caption("Plan campaign intent, storyline, and cross-platform post direction before scheduling.")

    recipes = st.session_state.get("recipes", [])
    if not recipes:
        st.info("Lock a recipe batch first so the planner has recipes to work with.")
        return

    recipe_options = {f"{recipe.get('name', '')} · {recipe.get('time', '')}": recipe for recipe in recipes}
    selected_labels = st.multiselect(
        "Choose recipes to plan",
        options=list(recipe_options.keys()),
        default=list(recipe_options.keys())[: min(3, len(recipe_options))],
        key="planner_recipe_selection",
    )

    col1, col2 = st.columns(2)
    with col1:
        campaign_intent = st.selectbox(
            "Campaign intent",
            options=["Traffic", "Engagement", "Saveability", "Authority", "Community Conversation"],
            key="planner_campaign_intent",
        )
    with col2:
        planning_window = st.selectbox(
            "Planning window",
            options=["This week", "Next week", "Two-week push"],
            key="planner_window",
        )

    storyline = st.text_input(
        "Storyline / campaign narrative",
        key="planner_storyline",
        placeholder="e.g. high-protein back-to-school dinners that still feel craveable",
    )
    col_dest1, col_dest2 = st.columns(2)
    with col_dest1:
        default_pinterest_destination = st.text_input(
            "Default Pinterest board label",
            key="planner_pinterest_destination",
            placeholder="e.g. Weeknight Dinners Board",
        )
    with col_dest2:
        default_reddit_subreddit = st.text_input(
            "Default subreddit",
            key="planner_reddit_destination",
            placeholder="e.g. recipes",
        )
    profile_context = _selected_profile_context()
    if profile_context:
        st.caption(f"Active Voice Profile: {st.session_state.get('active_voice_profile', '')}")

    if st.button("Build Content Plan", type="primary", use_container_width=True, disabled=not selected_labels):
        selected_recipes = [recipe_options[label] for label in selected_labels]
        plan_rows = []
        pinterest_seed_packages = {}
        reddit_seed_drafts = []

        for recipe in selected_recipes:
            query = " ".join(
                part for part in [
                    recipe.get("name", ""),
                    recipe.get("benefit", ""),
                    recipe.get("ingredient_names", ""),
                    storyline,
                    profile_context,
                    campaign_intent,
                ] if part
            )
            context = query_similar_market_signals(query, top_k=8)
            pinterest_packages = generate_hook_packages(
                recipe,
                trend_context=context,
                platform="pinterest",
                storyline=f"{storyline} | Intent: {campaign_intent} | {profile_context}".strip(" |"),
            )
            reddit_packages = generate_hook_packages(
                recipe,
                trend_context=context,
                platform="reddit",
                storyline=f"{storyline} | Intent: {campaign_intent} | {profile_context}".strip(" |"),
            )
            pinterest_seed_packages[recipe.get("name", "")] = pinterest_packages
            if reddit_packages:
                reddit_seed_drafts.append(
                    {
                        "recipe_name": recipe.get("name", ""),
                        "title": reddit_packages[0].get("hook", ""),
                        "body": reddit_packages[0].get("description", ""),
                        "query": query,
                        "source_url": recipe.get("url", ""),
                        "kind": "link" if recipe.get("url") else "self",
                        "subreddit": default_reddit_subreddit.strip(),
                    }
                )

            plan_rows.append(
                {
                    "Recipe": recipe.get("name", ""),
                    "Recipe URL": recipe.get("url", ""),
                    "Image URL": recipe.get("image_url", ""),
                    "Intent": campaign_intent,
                    "Window": planning_window,
                    "Pinterest Destination": default_pinterest_destination.strip(),
                    "Reddit Destination": default_reddit_subreddit.strip(),
                    "Pinterest angle": pinterest_packages[0].get("angle", "") if pinterest_packages else "",
                    "Pinterest hook": pinterest_packages[0].get("hook", "") if pinterest_packages else "",
                    "Reddit angle": reddit_packages[0].get("angle", "") if reddit_packages else "",
                    "Reddit draft title": reddit_packages[0].get("hook", "") if reddit_packages else "",
                }
            )

        st.session_state.content_plan_rows = plan_rows
        st.session_state.planned_pinterest_packages = pinterest_seed_packages
        st.session_state.reddit_drafts = reddit_seed_drafts
        st.session_state.content_plan_meta = {
            "campaign_intent": campaign_intent,
            "planning_window": planning_window,
            "storyline": storyline,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        st.success("Content plan built. Reddit drafts are ready for Scheduler Hub, and the plan is summarized below.")
        st.rerun()

    plan_rows = st.session_state.get("content_plan_rows", [])
    if not plan_rows:
        return

    st.divider()
    st.dataframe(pd.DataFrame(plan_rows), use_container_width=True, hide_index=True)
    editable_rows = []
    st.markdown("**Destination Assignment**")
    st.caption("Set where each recipe should go before sending the plan to the scheduler.")
    for row in plan_rows:
        with st.expander(f"{row.get('Recipe', '')}", expanded=False):
            p_dest = st.text_input(
                "Pinterest board label",
                value=row.get("Pinterest Destination", ""),
                key=f"planner_pin_dest_{row.get('Recipe', '')}",
                placeholder="e.g. High Protein Recipes",
            )
            r_dest = st.text_input(
                "Subreddit",
                value=row.get("Reddit Destination", ""),
                key=f"planner_reddit_dest_{row.get('Recipe', '')}",
                placeholder="e.g. recipes",
            )
            updated_row = row.copy()
            updated_row["Pinterest Destination"] = p_dest.strip()
            updated_row["Reddit Destination"] = r_dest.strip()
            editable_rows.append(updated_row)
    if editable_rows:
        st.session_state.content_plan_rows = editable_rows
        st.session_state.reddit_drafts = [
            {
                **draft,
                "subreddit": next(
                    (
                        row.get("Reddit Destination", "")
                        for row in editable_rows
                        if row.get("Recipe", "") == draft.get("recipe_name", "")
                    ),
                    draft.get("subreddit", ""),
                ),
            }
            for draft in st.session_state.get("reddit_drafts", [])
        ]
        plan_rows = editable_rows

    meta = st.session_state.get("content_plan_meta", {})
    st.caption(
        f"Intent: {meta.get('campaign_intent', '')} | Window: {meta.get('planning_window', '')} | "
        f"Storyline: {meta.get('storyline', '') or 'None'}"
    )

    st.divider()
    st.subheader("Queue This Plan")
    default_date = (datetime.now(timezone.utc) + timedelta(days=1)).date()
    c1, c2, c3 = st.columns(3)
    with c1:
        schedule_start_date = st.date_input("Start date (UTC)", value=default_date, key="planner_schedule_start")
    with c2:
        posts_per_day = st.slider("Posts per day", min_value=1, max_value=6, value=2, key="planner_posts_per_day")
    with c3:
        first_hour = st.slider("First hour UTC", min_value=0, max_value=23, value=14, key="planner_first_hour")

    if st.button("Queue Planned Content to Scheduler", type="primary", use_container_width=True):
        pinterest_count, reddit_count = _queue_plan_to_scheduler(
            plan_rows,
            st.session_state.get("planned_pinterest_packages", {}),
            st.session_state.get("reddit_drafts", []),
            schedule_start_date,
            posts_per_day,
            first_hour,
        )
        st.success(
            f"Queued {pinterest_count} Pinterest job(s) and {reddit_count} Reddit reminder job(s) from the current plan."
        )
