"""
Signal Factory dashboard.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

CHROMA_DIR = Path("data/chroma")
if CHROMA_DIR.exists():
    try:
        total_size = sum(f.stat().st_size for f in CHROMA_DIR.rglob("*") if f.is_file())
        if total_size > 10 * 1024 * 1024:
            shutil.rmtree(CHROMA_DIR, ignore_errors=True)
            print("Cleared large ChromaDB cache (>10MB) on startup")
    except Exception:
        shutil.rmtree(CHROMA_DIR, ignore_errors=True)

load_dotenv()

st.set_page_config(
    page_title="Signal Factory",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DEFAULTS = {
    "batch_locked": False,
    "recipes": [],
    "hooks": {},
    "descriptions": {},
    "notion_log": [],
    "ai_generated": False,
    "active_tool": "Pinterest Studio",
    "reddit_posts": [],
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

TOOLS = {
    "Pinterest Studio": {
        "icon": "📌",
        "blurb": "Recipe scraping, hook generation, pin production, scheduling, and Notion sync.",
    },
    "Reddit Radar": {
        "icon": "💬",
        "blurb": "Scrape relevant Reddit discussions and surface community language, angles, and demand signals.",
    },
}

from components.ai_engine import render_ai_engine
from components.intake import render_intake
from components.notion_sync import render_notion_sync
from components.pin_generator import render_pin_generator
from components.reddit_scraper import render_reddit_scraper

st.markdown(
    """
    <div style="padding:18px 20px;border-radius:18px;background:
    linear-gradient(135deg,#fff7ed 0%,#fef3c7 40%,#ecfccb 100%);
    border:1px solid rgba(15,23,42,.08);margin-bottom:18px;">
        <div style="font-size:30px;font-weight:700;color:#172554;">Signal Factory</div>
        <div style="font-size:15px;color:#334155;margin-top:4px;">
            Multi-platform marketing workflows for Pinterest, Reddit, and the next tools you add.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

tool_cols = st.columns(len(TOOLS))
for idx, (tool_name, meta) in enumerate(TOOLS.items()):
    with tool_cols[idx]:
        st.markdown(f"**{meta['icon']} {tool_name}**")
        st.caption(meta["blurb"])
        if st.button(
            "Open Workspace" if st.session_state.active_tool != tool_name else "Current Workspace",
            key=f"tool_{tool_name}",
            type="primary" if st.session_state.active_tool == tool_name else "secondary",
            use_container_width=True,
            disabled=st.session_state.active_tool == tool_name,
        ):
            st.session_state.active_tool = tool_name
            st.rerun()

st.divider()

active_tool = st.session_state.active_tool

if active_tool == "Pinterest Studio":
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Recipes in batch", len(st.session_state.recipes))
    col2.metric("Hooks generated", sum(len(v) for v in st.session_state.hooks.values()))
    col3.metric("Pins ready", sum(len(v) for v in st.session_state.hooks.values()))
    col4.metric("Synced to Notion", len([line for line in st.session_state.notion_log if "✅" in line]))

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📋 Intake",
            "🤖 Copy Engine",
            "🎨 Pin Builder",
            "🗂️ Sync + Schedule",
        ]
    )
    with tab1:
        render_intake()
    with tab2:
        render_ai_engine()
    with tab3:
        render_pin_generator()
    with tab4:
        render_notion_sync()
else:
    col1, col2, col3 = st.columns(3)
    col1.metric("Posts in results", len(st.session_state.get("reddit_posts", [])))
    col2.metric("Subreddits surfaced", len({p.get('subreddit', '') for p in st.session_state.get("reddit_posts", []) if p.get('subreddit')}))
    col3.metric("Saved query", 1 if st.session_state.get("reddit_last_query") else 0)

    st.divider()
    render_reddit_scraper()
