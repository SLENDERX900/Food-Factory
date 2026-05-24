"""
components/ai_engine.py — Tab 2: AI Copy Engine
Connects to Groq API, generates hooks + descriptions, renders editable text boxes.
All output is saved back to st.session_state so edits persist across tabs.
"""

import streamlit as st
from utils.groq_client import (
    check_connection,
    generate_description,
    generate_hook_packages,
    GROQ_MODEL,
)
from utils.pinterest_trends import collect_trending_pins
from utils.rag_memory import query_similar_market_signals, store_market_signals, store_trending_pins
from utils.reddit_scraper import build_recipe_reddit_query, scrape_reddit_posts
from utils.voice_profiles import list_profiles, profile_to_prompt_context


def _clean_hook_text(hook_text: str) -> str:
    filler_phrases = [
        'Here are the 5 Pinterest hooks:',
        'Here are 5 Pinterest hooks:',
        'Here are the hooks:',
        'Here are hooks:',
        'Pinterest hooks:',
        'hooks:',
        'Here are',
        'Pinterest',
        '1.', '2.', '3.', '4.', '5.',
        '-', '*',
    ]
    cleaned = hook_text
    for phrase in filler_phrases:
        cleaned = cleaned.replace(phrase, '')
        cleaned = cleaned.replace(phrase.capitalize(), '')
        cleaned = cleaned.replace(phrase.upper(), '')

    lines = cleaned.split('\n')
    cleaned_lines = []
    for line in lines:
        line_lower = line.lower()
        if not any(phrase in line_lower for phrase in ['here are', 'pinterest hooks', 'hooks:']):
            cleaned_lines.append(line.strip())

    cleaned_lines = [line for line in cleaned_lines if line and len(line) > 3]
    return cleaned_lines[0] if cleaned_lines else hook_text


def render_ai_engine():
    st.subheader("AI Copy Engine")
    st.caption("Generates trend-aware Pinterest hooks and descriptions using Groq with platform-native lingo.")

    # ── Groq connection check ───────────────────────────────────────────────
    with st.container():
        col_status, col_model = st.columns([3, 1])
        with col_status:
            ok, msg = check_connection()
            if ok:
                st.success(f"✅ Groq connected · model: `{msg}`")
            else:
                st.error(f"❌ Groq API error — {msg}")
                st.code("# Add to .env file:\nGROQ_API_KEY=gsk_xxxxxxxxxxxx", language="bash")
                st.stop()
        with col_model:
            st.caption(f"Model: `{GROQ_MODEL}`")

    st.divider()

    # ── Guard: batch must be locked ───────────────────────────────────────────
    if not st.session_state.get("batch_locked") or not st.session_state.get("recipes"):
        st.warning("⚠️ No batch locked yet. Go to **Step 1 → Batch Intake** and lock your recipes first.")
        return

    recipes = st.session_state.recipes
    voice_profiles = list_profiles()
    active_profile_name = st.session_state.get("active_voice_profile", "")
    active_profile = next((profile for profile in voice_profiles if profile.get("name") == active_profile_name), None)
    profile_context = profile_to_prompt_context(active_profile)

    col_story_1, col_story_2 = st.columns([2, 1])
    with col_story_1:
        storyline_preset = st.selectbox(
            "Storyline",
            options=[
                "Weeknight rescue",
                "Cozy comfort",
                "Better than takeout",
                "Healthy but satisfying",
                "Meal prep win",
                "Picky eater approved",
                "Hosting / sharing food",
                "Custom",
            ],
            key="storyline_preset",
        )
    with col_story_2:
        seasonal_context = st.text_input(
            "Occasion / season",
            key="seasonal_context",
            placeholder="e.g. summer cookout, back-to-school",
        )

    custom_storyline = ""
    if storyline_preset == "Custom":
        custom_storyline = st.text_input(
            "Custom storyline",
            key="custom_storyline",
            placeholder="Describe the emotional frame or posting story you want.",
        )
    storyline = custom_storyline.strip() if storyline_preset == "Custom" else storyline_preset
    if seasonal_context.strip():
        storyline = f"{storyline} · {seasonal_context.strip()}" if storyline else seasonal_context.strip()
    if profile_context:
        storyline = f"{storyline} | {profile_context}" if storyline else profile_context

    st.caption("Pinterest and Reddit signals are pulled automatically in the background and added to memory before generation.")
    if active_profile:
        st.caption(f"Active Voice Profile: {active_profile.get('name', '')}")

    # ── Generation controls ───────────────────────────────────────────────────
    col_gen, col_regen, col_info = st.columns([1, 1, 3])

    with col_gen:
        generate_all = st.button(
            "🚀 Generate all hooks",
            type="primary",
            width='stretch',
            disabled=st.session_state.ai_generated,
        )
    with col_regen:
        regenerate = st.button(
            "🔄 Re-generate all",
            width='stretch',
        )
    with col_info:
        st.caption(
            f"Will generate {len(recipes) * 5} hooks + {len(recipes)} descriptions "
            f"across {len(recipes)} recipe(s). Fast generation via Groq API."
        )

    if regenerate:
        st.session_state.hooks = {}
        st.session_state.descriptions = {}
        st.session_state.ai_generated = False
        st.rerun()

    # ── Main generation loop ──────────────────────────────────────────────────
    if generate_all or (regenerate and not st.session_state.ai_generated):
        progress = st.progress(0, text="Starting generation...")
        status_placeholder = st.empty()
        st.session_state.hook_packages = {}
        st.session_state.market_signal_log = {}

        for idx, recipe in enumerate(recipes):
            name = recipe["name"]
            pct = int((idx / len(recipes)) * 100)
            progress.progress(pct, text=f"Generating: {name} ({idx + 1}/{len(recipes)})")
            status_placeholder.info(f"⏳ Processing **{name}**...")

            # Trend scrape + RAG memory with rich content
            trend_pins, trend_source = collect_trending_pins(recipe.get("url", recipe.get("name", "")), max_pins=10)
            print(f"AI DEBUG: Collected {len(trend_pins)} pins from {trend_source}", flush=True)
            if trend_pins:
                print(f"AI DEBUG: Sample pin: {trend_pins[0]}", flush=True)
            for pin in trend_pins:
                pin["query"] = recipe.get("name", "")
                pin["recipe_name"] = name
                pin["platform"] = "pinterest"
            store_trending_pins(trend_pins)

            reddit_query = build_recipe_reddit_query(recipe, storyline=storyline)
            try:
                reddit_posts = scrape_reddit_posts(reddit_query, sort="relevance", limit=8)
            except Exception as exc:
                print(f"AI DEBUG: Reddit signal fetch failed for {name}: {exc}", flush=True)
                reddit_posts = []
            for post in reddit_posts:
                post["recipe_name"] = name
                post["query"] = reddit_query
                post["description"] = post.get("selftext", "")
                post["source"] = "reddit"
            store_market_signals(reddit_posts, platform="reddit")

            # Build rich query from blog content for better trend matching
            blog_sample = recipe.get("blog_content_sample", "")
            ingredient_names = recipe.get("ingredient_names", "")
            meta_keywords = recipe.get("meta_keywords", "")
            
            # Combine all signals for trend query
            query_parts = [
                recipe.get("name", ""),
                recipe.get("benefit", ""),
                recipe.get("time", ""),
                ingredient_names,
                blog_sample[:200] if blog_sample else "",  # Key blog phrases
                meta_keywords,
                storyline,
            ]
            trend_query = " ".join([p for p in query_parts if p])
            
            rag_context = query_similar_market_signals(trend_query, top_k=8)
            print(f"AI DEBUG: RAG context has {len(rag_context) if rag_context else 0} similar trends", flush=True)
            if rag_context:
                print(f"AI DEBUG: Sample RAG trend: {rag_context[0] if rag_context else 'None'}", flush=True)
            st.session_state.market_signal_log[name] = {
                "pinterest_signals": len(trend_pins),
                "reddit_signals": len(reddit_posts),
                "storyline": storyline,
            }

            # Hooks + descriptions (JSON packages)
            try:
                print(
                    f"AI DEBUG: Sending to Groq with {len(trend_pins)} Pinterest pins, "
                    f"{len(reddit_posts)} Reddit posts, and {len(rag_context) if rag_context else 0} memory signals",
                    flush=True,
                )
                packages = generate_hook_packages(
                    recipe,
                    trend_context=rag_context,
                    platform="pinterest",
                    storyline=storyline,
                )
                hooks = {pkg.get("angle", f"Angle-{i}"): pkg.get("hook", "") for i, pkg in enumerate(packages)}
                print(f"AI DEBUG: Groq generated {len(packages) if packages else 0} hook packages", flush=True)
                st.session_state.hook_packages[name] = packages
                cleaned_hooks = {angle: _clean_hook_text(hook_text) for angle, hook_text in hooks.items()}
                st.session_state.hooks[name] = cleaned_hooks
            except Exception as e:
                # Generate fallback hooks dynamically
                fallback_angles = ["Time-Saver", "Effortless", "Weeknight-Hero", "Ingredient-Win", "Core-Method"]
                st.session_state.hooks[name] = {a: f"[Generation failed: {e}]" for a in fallback_angles}
                st.session_state.hook_packages[name] = []

            # Description
            try:
                desc = generate_description(
                    recipe,
                    trend_context=rag_context,
                    platform="pinterest",
                    storyline=storyline,
                )
                st.session_state.descriptions[name] = desc
            except Exception as e:
                st.session_state.descriptions[name] = f"[Description generation failed: {e}]"

        progress.progress(100, text="Generation complete!")
        status_placeholder.success(f"✅ Generated hooks and descriptions for {len(recipes)} recipe(s).")
        st.session_state.ai_generated = True
        st.rerun()

    # ── Display editable output ───────────────────────────────────────────────
    if not st.session_state.hooks:
        st.info("Click **Generate all hooks** above to start. You can edit any hook after generation.")
        return

    st.subheader("Edit hooks before exporting")
    st.caption("All changes are saved automatically. These exact texts will appear in the Canva CSV.")
    st.caption("🎯 Angles are dynamically generated from recipe context plus hidden Pinterest and Reddit market signals.")

    # Dynamic angle tips based on common categories
    ANGLE_TIPS = {
        "Lightning-Fast": "Lead with the time. Under 8 words.",
        "Effortless": "Effortless, minimal effort framing. Under 8 words.",
        "Health-Boost": "Highlight nutrition benefits. Under 8 words.",
        "Protein-Packed": "Emphasize protein content. Under 8 words.",
        "Texture-Perfect": "Focus on texture (crispy, juicy). Under 8 words.",
        "Minimal-Cleanup": "One-pan, sheet-pan angle. Under 8 words.",
        "Carb-Comfort": "Comfort food angle. Under 8 words.",
        "Family-Approved": "Kid/family friendly. Under 8 words.",
        "Slow-Cooked": "Flavor depth from slow cooking. Under 8 words.",
        "Big-Flavor": "Bold flavor emphasis. Under 8 words.",
        "Fresh-Bright": "Fresh, light, healthy. Under 8 words.",
        "Budget-Smart": "Affordable/pantry angle. Under 8 words.",
    }

    for recipe in recipes:
        name = recipe["name"]
        hooks = st.session_state.hooks.get(name, {})
        description = st.session_state.descriptions.get(name, "")
        hook_packages = st.session_state.hook_packages.get(name, [])
        signal_stats = st.session_state.get("market_signal_log", {}).get(name, {})

        with st.expander(f"**{name}** — {recipe.get('time', '')} · {recipe.get('benefit', '')}", expanded=True):
            if signal_stats:
                st.caption(
                    f"Signal memory used: {signal_stats.get('pinterest_signals', 0)} Pinterest + "
                    f"{signal_stats.get('reddit_signals', 0)} Reddit | Storyline: {signal_stats.get('storyline', 'None') or 'None'}"
                )

            # Dynamic hooks display - show all generated hooks with SEO descriptions
            col_left, col_right = st.columns(2)
            cols = [col_left, col_right, col_left, col_right, col_left]

            angles = list(hooks.keys())
            for i, angle in enumerate(angles):
                current = hooks.get(angle, "")
                new_val = cols[i].text_input(
                    label=f"**{angle}**",
                    value=current,
                    key=f"hook_{name}_{angle}",
                    help=ANGLE_TIPS.get(angle, "Under 8 words, punchy and specific"),
                    max_chars=60,
                )
                # Word count warning
                word_count = len(new_val.split())
                if word_count > 8:
                    cols[i].caption(f"⚠️ {word_count} words — aim for 8 or fewer")
                else:
                    cols[i].caption(f"{word_count} words ✓" if new_val else "")

                # Find and display SEO description from hook packages
                hook_desc = ""
                for package in hook_packages:
                    if package.get('angle') == angle:
                        hook_desc = package.get('description', '')
                        break
                
                # Display unique SEO description for this specific pin angle
                if hook_desc:
                    cols[i].markdown(f"""
                    <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-top: 5px;">
                        <strong>📌 SEO Description for {angle}:</strong><br>
                        <small style="color: #333;">{hook_desc}</small>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Store individual SEO descriptions in session state
                    if 'pin_descriptions' not in st.session_state:
                        st.session_state.pin_descriptions = {}
                    if name not in st.session_state.pin_descriptions:
                        st.session_state.pin_descriptions[name] = {}
                    st.session_state.pin_descriptions[name][angle] = hook_desc

                # Save edit back to state
                if new_val != current:
                    st.session_state.hooks[name][angle] = new_val

            st.divider()

            # Remove the general SEO description field since each pin has its own
            st.markdown("### 📋 Copy-Paste Ready Content")
            st.markdown(f"**Recipe:** {name}")
            st.markdown("**Each hook above has its own unique SEO description for that specific angle.**")
            
            # Show all hooks + descriptions in copy-paste format
            st.markdown("**📱 Pinterest Content:**")
            for angle in angles:
                hook_text = hooks.get(angle, "")
                # Safe access to pin_descriptions
                pin_descriptions = st.session_state.get('pin_descriptions', {})
                seo_text = pin_descriptions.get(name, {}).get(angle, "")
                if hook_text and seo_text:
                    st.markdown(f"""
                    <div style="border: 1px solid #ddd; padding: 10px; margin: 5px 0; border-radius: 5px;">
                        <strong>📌 {angle} Pin:</strong><br>
                        <strong>Hook:</strong> {hook_text}<br>
                        <strong>Description:</strong> {seo_text}
                    </div>
                    """, unsafe_allow_html=True)

            # URL quick-link
            if recipe.get("url"):
                st.caption(f"🔗 [{recipe['url']}]({recipe['url']})")

    st.divider()
    st.info("✅ All edits saved. Head to **Step 3 → Generate Pins** to preview and download your images.")
