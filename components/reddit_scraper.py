"""
Reddit research workspace driven by blog recipes.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from utils.groq_client import generate_hook_packages
from utils.rag_memory import query_similar_market_signals, store_market_signals
from utils.reddit_scraper import build_recipe_reddit_query, scrape_reddit_posts
from utils.sitemap_memory import clear_all_urls, get_processed_count
from utils.voice_profiles import list_profiles, profile_to_prompt_context
from utils.web_scraper import scrape_recipes_from_website_with_memory, validate_url


def _format_post_rows(posts: list[dict]) -> list[dict]:
    rows = []
    for post in posts:
        created = post.get("created_utc")
        created_at = ""
        if created:
            created_at = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        rows.append(
            {
                "Recipe": post.get("recipe_name", ""),
                "Title": post.get("title", ""),
                "Subreddit": post.get("subreddit", ""),
                "Score": post.get("score", 0),
                "Comments": post.get("num_comments", 0),
                "Author": post.get("author", ""),
                "Created": created_at,
                "URL": post.get("url", ""),
                "Snippet": post.get("selftext", ""),
            }
        )
    return rows


def _recipe_label(recipe: dict) -> str:
    return f"{recipe.get('name', 'Untitled')} · {recipe.get('time', 'No time found')}"


def _generate_reddit_drafts(recipes: list[dict], subreddit: str, storyline: str) -> list[dict]:
    drafts: list[dict] = []
    for recipe in recipes:
        query = build_recipe_reddit_query(recipe, storyline=storyline)
        context = query_similar_market_signals(query, top_k=8)
        packages = generate_hook_packages(recipe, trend_context=context, platform="reddit", storyline=storyline)
        if not packages:
            continue
        package = packages[0]
        drafts.append(
            {
                "recipe_name": recipe.get("name", ""),
                "subreddit": subreddit,
                "title": package.get("hook", ""),
                "body": package.get("description", ""),
                "query": query,
                "source_url": recipe.get("url", ""),
                "kind": "link" if recipe.get("url") else "self",
            }
        )
    return drafts


def render_reddit_scraper() -> None:
    st.subheader("Reddit Radar")
    st.caption("Start from recipes on your food blog, then scrape Reddit for real audience language around those recipes.")
    voice_profiles = list_profiles()
    active_profile_name = st.session_state.get("active_voice_profile", "")
    active_profile = next((profile for profile in voice_profiles if profile.get("name") == active_profile_name), None)

    if "reddit_recipe_candidates" not in st.session_state:
        st.session_state.reddit_recipe_candidates = []

    with st.expander("🌐 Scrape Recipes from Food Blog", expanded=not st.session_state.reddit_recipe_candidates):
        website_url = st.text_input(
            "Food blog URL",
            key="reddit_blog_url",
            placeholder="https://yourfoodblog.com",
            help="Scrape recipe pages first, then use those recipes as Reddit research seeds.",
        )

        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            max_recipes = st.slider("Max recipes", min_value=5, max_value=40, value=15, step=5, key="reddit_max_recipes")
        with col2:
            use_memory = st.checkbox(
                "Use saved scraper memory",
                value=False,
                key="reddit_use_memory",
                help="Leave this off for a fresh scrape, same as the Pinterest workflow.",
            )
        with col3:
            st.metric("Saved URLs", get_processed_count())

        scrape_col, reset_col = st.columns([3, 1])
        with scrape_col:
            if st.button("🔍 Scrape Blog Recipes", type="primary", use_container_width=True, disabled=not website_url):
                if not validate_url(website_url):
                    st.error("Please enter a valid URL including `https://`.")
                else:
                    with st.spinner("Scraping recipes from your blog..."):
                        try:
                            recipes = scrape_recipes_from_website_with_memory(
                                website_url,
                                max_recipes=max_recipes,
                                use_processed_memory=use_memory,
                            )
                        except Exception as exc:
                            st.error(f"Recipe scrape failed: {exc}")
                        else:
                            st.session_state.reddit_recipe_candidates = recipes
                            if recipes:
                                st.success(f"Found {len(recipes)} recipes to use for Reddit research.")
                            else:
                                st.warning("No recipes found from that blog scrape.")
                            st.rerun()

        with reset_col:
            if st.button("🧹 Reset Memory", use_container_width=True, key="reddit_reset_memory"):
                clear_all_urls()
                st.success("Saved scraper memory cleared.")
                st.rerun()

    recipe_candidates = st.session_state.get("reddit_recipe_candidates", [])
    locked_batch = st.session_state.get("recipes", [])

    source_options: dict[str, list[dict]] = {}
    if recipe_candidates:
        source_options["Fresh blog scrape"] = recipe_candidates
    if locked_batch:
        source_options["Pinterest batch"] = locked_batch

    if not source_options:
        st.info("Scrape recipes from your blog above, or build a Pinterest batch first, to use recipe-based Reddit research.")
        return

    source_name = st.radio(
        "Recipe source",
        options=list(source_options.keys()),
        horizontal=True,
        key="reddit_recipe_source",
    )
    recipes = source_options[source_name]

    recipe_map = {_recipe_label(recipe): recipe for recipe in recipes}
    selected_labels = st.multiselect(
        "Select recipes to research on Reddit",
        options=list(recipe_map.keys()),
        default=list(recipe_map.keys())[: min(5, len(recipe_map))],
        key="reddit_recipe_multiselect",
    )

    colq1, colq2, colq3 = st.columns([2, 1, 1])
    with colq1:
        subreddit = st.text_input(
            "Subreddit (optional)",
            key="reddit_subreddit_input",
            placeholder="e.g. recipes",
            help="Leave blank to search across Reddit, or narrow to one subreddit.",
        )
    with colq2:
        sort = st.selectbox("Sort", options=["relevance", "new", "top", "comments"], index=0, key="reddit_sort")
    with colq3:
        limit = st.slider("Posts per recipe", min_value=5, max_value=30, value=10, step=5, key="reddit_limit")

    manual_hint = st.text_input(
        "Optional extra query hint",
        key="reddit_manual_hint",
        placeholder="e.g. meal prep, picky eaters, air fryer",
        help="Adds an extra angle to each recipe query without replacing the recipe-driven search.",
    )

    storyline = st.text_input(
        "Storyline / framing",
        key="reddit_storyline",
        placeholder="e.g. weeknight rescue, healthy comfort, budget meal prep",
        help="Used to shape both the Reddit research query and the eventual post draft tone.",
    )
    if active_profile:
        st.caption(f"Active Voice Profile: {active_profile.get('name', '')}")
        profile_context = profile_to_prompt_context(active_profile)
        storyline = f"{storyline} | {profile_context}" if storyline else profile_context

    if st.button("💬 Scrape Reddit Posts", use_container_width=True, disabled=not selected_labels):
        selected_recipes = [recipe_map[label] for label in selected_labels]
        all_posts: list[dict] = []
        with st.spinner("Pulling Reddit discussions for selected recipes..."):
            for recipe in selected_recipes:
                query = build_recipe_reddit_query(recipe, storyline=storyline)
                if manual_hint.strip():
                    query = f"{query} {manual_hint.strip()}".strip()
                try:
                    posts = scrape_reddit_posts(query, subreddit=subreddit, sort=sort, limit=limit)
                except Exception as exc:
                    st.warning(f"Failed for {recipe.get('name', 'recipe')}: {exc}")
                    continue

                for post in posts:
                    post["recipe_name"] = recipe.get("name", "")
                    post["recipe_query"] = query
                    post["query"] = query
                    post["source"] = "reddit"
                    post["description"] = post.get("selftext", "")
                all_posts.extend(posts)

        store_market_signals(all_posts, platform="reddit")
        st.session_state.reddit_posts = all_posts
        st.session_state.reddit_last_query = manual_hint.strip()
        if all_posts:
            st.success(f"Found {len(all_posts)} Reddit posts across {len(selected_labels)} recipe searches.")
        else:
            st.warning("No Reddit posts found for the selected recipes.")
        st.rerun()

    posts = st.session_state.get("reddit_posts", [])
    if not posts:
        st.info("Select recipes, then run Reddit scraping to populate audience research.")
        return

    df = pd.DataFrame(_format_post_rows(posts))
    st.divider()
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Download reddit_research.csv",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="reddit_research.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.divider()
    if st.button(
        "✍️ Generate Reddit Drafts",
        use_container_width=True,
        disabled=not selected_labels or not subreddit.strip(),
    ):
        selected_recipes = [recipe_map[label] for label in selected_labels]
        drafts = _generate_reddit_drafts(selected_recipes, subreddit.strip(), storyline.strip() or manual_hint.strip())
        st.session_state.reddit_drafts = drafts
        if drafts:
            st.success(f"Generated {len(drafts)} Reddit draft(s) ready for scheduling.")
        else:
            st.warning("Could not generate Reddit drafts from the selected recipes.")
        st.rerun()

    drafts = st.session_state.get("reddit_drafts", [])
    if drafts:
        st.subheader("Reddit Drafts")
        for draft in drafts:
            with st.expander(f"r/{draft.get('subreddit', '')} · {draft.get('recipe_name', '')}", expanded=False):
                st.markdown(f"**Title:** {draft.get('title', '')}")
                st.markdown(f"**Body:** {draft.get('body', '')}")
                st.caption(f"Post type: {draft.get('kind', 'self')} | Query: {draft.get('query', '')}")

    st.divider()
    st.subheader("Language Signal")
    for post in posts[:10]:
        title = post.get("title", "")
        subreddit_name = post.get("subreddit", "")
        recipe_name = post.get("recipe_name", "")
        with st.expander(f"{recipe_name} · r/{subreddit_name} · {title}", expanded=False):
            st.caption(post.get("url", ""))
            st.write(post.get("selftext", "") or "No self post text captured for this result.")
