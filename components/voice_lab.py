"""
Voice Lab workspace for reusable content profiles.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.voice_profiles import delete_profile, list_profiles, profile_to_prompt_context, upsert_profile


def render_voice_lab() -> None:
    st.subheader("Voice Lab")
    st.caption("Build reusable story, tone, and lingo profiles so the platform learns how you want content to feel across channels.")

    profiles = list_profiles()
    profile_names = [profile.get("name", "") for profile in profiles]

    st.markdown("**Profile Library**")
    if profiles:
        rows = [
            {
                "Name": profile.get("name", ""),
                "Storyline": profile.get("storyline", ""),
                "Occasion": profile.get("occasion", ""),
                "Tone": profile.get("tone", ""),
                "Lingo": ", ".join(profile.get("lingo", [])),
                "CTA style": profile.get("cta_style", ""),
            }
            for profile in profiles
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No voice profiles yet.")

    st.divider()
    st.markdown("**Create or Update Profile**")

    selected = st.selectbox("Load existing profile", options=[""] + profile_names, key="voice_lab_load")
    existing = next((profile for profile in profiles if profile.get("name") == selected), None)

    name = st.text_input("Profile name", value=existing.get("name", "") if existing else "", key="voice_name")
    storyline = st.text_area(
        "Storyline",
        value=existing.get("storyline", "") if existing else "",
        key="voice_storyline",
        placeholder="What emotional or strategic frame should the content carry?",
    )
    occasion = st.text_input(
        "Occasion / context",
        value=existing.get("occasion", "") if existing else "",
        key="voice_occasion",
        placeholder="e.g. back-to-school, Sunday prep, summer cookout",
    )
    tone = st.text_input(
        "Tone",
        value=existing.get("tone", "") if existing else "",
        key="voice_tone",
        placeholder="e.g. warm, sharp, playful, grounded",
    )
    lingo = st.text_area(
        "Native lingo",
        value=", ".join(existing.get("lingo", [])) if existing else "",
        key="voice_lingo",
        placeholder="Comma-separated phrases you want the model to sound fluent in",
    )
    cta_style = st.text_input(
        "CTA style",
        value=existing.get("cta_style", "") if existing else "",
        key="voice_cta_style",
        placeholder="e.g. gentle encouragement, curiosity pull, challenge framing",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Save Profile", type="primary", use_container_width=True):
            profile = {
                "name": name.strip(),
                "storyline": storyline.strip(),
                "occasion": occasion.strip(),
                "tone": tone.strip(),
                "lingo": [item.strip() for item in lingo.split(",") if item.strip()],
                "cta_style": cta_style.strip(),
            }
            if not profile["name"]:
                st.error("Profile name is required.")
            else:
                upsert_profile(profile)
                st.session_state.active_voice_profile = profile["name"]
                st.success(f"Saved profile: {profile['name']}")
                st.rerun()
    with col2:
        if selected and st.button("Delete Profile", use_container_width=True):
            delete_profile(selected)
            if st.session_state.get("active_voice_profile") == selected:
                st.session_state.active_voice_profile = ""
            st.success(f"Deleted profile: {selected}")
            st.rerun()

    st.divider()
    st.markdown("**Active Profile**")
    active_name = st.selectbox(
        "Choose profile for generation",
        options=[""] + profile_names,
        index=([""] + profile_names).index(st.session_state.get("active_voice_profile", "")) if st.session_state.get("active_voice_profile", "") in profile_names else 0,
        key="active_voice_profile_selector",
    )
    st.session_state.active_voice_profile = active_name
    active_profile = next((profile for profile in profiles if profile.get("name") == active_name), None)
    if active_profile:
        st.caption(profile_to_prompt_context(active_profile))
    else:
        st.caption("No active profile selected. The app will still use recipe, platform, and storyline context.")
