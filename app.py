"""
Food Factory dashboard.
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
    page_title="Food Factory",
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
    "reddit_drafts": [],
    "active_voice_profile": "",
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
        "blurb": "Research community language, generate Reddit-native drafts, and shape more human content angles.",
    },
    "Scheduler Hub": {
        "icon": "🗓️",
        "blurb": "Run the cross-platform publishing queue for Pinterest scheduling and Reddit post delivery.",
    },
    "Voice Lab": {
        "icon": "🧠",
        "blurb": "Train reusable tone, story, and lingo profiles that shape content across every platform.",
    },
    "Content Planner": {
        "icon": "🧩",
        "blurb": "Turn recipes, voice profiles, and campaign intent into a structured cross-platform posting plan.",
    },
}

from components.ai_engine import render_ai_engine
from components.intake import render_intake
from components.notion_sync import render_notion_sync
from components.pin_generator import render_pin_generator
from components.reddit_scraper import render_reddit_scraper
from components.scheduler_hub import render_scheduler_hub
from components.content_planner import render_content_planner
from components.voice_lab import render_voice_lab

st.markdown(
    """
    <div style="padding:18px 20px;border-radius:18px;background:
    linear-gradient(135deg,#fff7ed 0%,#fef3c7 40%,#ecfccb 100%);
    border:1px solid rgba(15,23,42,.08);margin-bottom:18px;">
        <div style="font-size:30px;font-weight:700;color:#172554;">Food Factory</div>
        <div style="font-size:15px;color:#334155;margin-top:4px;">
            Multi-platform marketing workflows for Pinterest, Reddit, and the next tools you add.
        </div>
        <div style="font-size:13px;color:#475569;margin-top:8px;">
            Built around story, memory, platform lingo, and publishing rhythm instead of generic one-click AI output.
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
elif active_tool == "Reddit Radar":
    col1, col2, col3 = st.columns(3)
    col1.metric("Posts in results", len(st.session_state.get("reddit_posts", [])))
    col2.metric("Subreddits surfaced", len({p.get('subreddit', '') for p in st.session_state.get("reddit_posts", []) if p.get('subreddit')}))
    col3.metric("Drafts ready", len(st.session_state.get("reddit_drafts", [])))

    st.divider()
    render_reddit_scraper()
else:
    if active_tool == "Scheduler Hub":
        render_scheduler_hub()
    elif active_tool == "Content Planner":
        render_content_planner()
    else:
        render_voice_lab()
