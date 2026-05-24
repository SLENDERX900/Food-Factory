"""
Reddit research workspace.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from utils.reddit_scraper import scrape_reddit_posts


def _format_post_rows(posts: list[dict]) -> list[dict]:
    rows = []
    for post in posts:
        created = post.get("created_utc")
        created_at = ""
        if created:
            created_at = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        rows.append(
            {
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


def render_reddit_scraper() -> None:
    st.subheader("Reddit Radar")
    st.caption("Scrape relevant Reddit posts to understand objections, pain points, phrasing, and community-native language.")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        query = st.text_input(
            "Search topic",
            key="reddit_query_input",
            placeholder="e.g. easy high protein dinner",
            help="Use the exact customer language or topic you want to research.",
        )
    with col2:
        subreddit = st.text_input(
            "Subreddit (optional)",
            key="reddit_subreddit_input",
            placeholder="e.g. recipes",
        )
    with col3:
        sort = st.selectbox("Sort", options=["relevance", "new", "top", "comments"], index=0, key="reddit_sort")

    limit = st.slider("Post limit", min_value=10, max_value=100, value=25, step=5, key="reddit_limit")

    if st.button("💬 Scrape Reddit Posts", type="primary", use_container_width=True, disabled=not query.strip()):
        with st.spinner("Pulling Reddit results..."):
            try:
                posts = scrape_reddit_posts(query, subreddit=subreddit, sort=sort, limit=limit)
            except Exception as exc:
                st.error(f"Reddit scrape failed: {exc}")
            else:
                st.session_state.reddit_posts = posts
                st.session_state.reddit_last_query = query
                if posts:
                    st.success(f"Found {len(posts)} relevant Reddit posts.")
                else:
                    st.warning("No Reddit posts found for that query.")
                st.rerun()

    posts = st.session_state.get("reddit_posts", [])
    if not posts:
        st.info("Run a query to populate Reddit discussions here.")
        return

    rows = _format_post_rows(posts)
    df = pd.DataFrame(rows)

    st.divider()
    st.dataframe(df, use_container_width=True, hide_index=True)

    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download reddit_research.csv",
        data=csv_data,
        file_name="reddit_research.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.divider()
    st.subheader("Language Signal")
    for post in posts[:8]:
        title = post.get("title", "")
        subreddit_name = post.get("subreddit", "")
        snippet = post.get("selftext", "")
        with st.expander(f"r/{subreddit_name} · {title}", expanded=False):
            st.caption(post.get("url", ""))
            st.write(snippet or "No self post text captured for this result.")
