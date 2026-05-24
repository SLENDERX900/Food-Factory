"""
components/export.py — Tab 3: Canva Bulk Export
Formats hooks into the exact CSV Canva's Bulk Create expects.
Columns: Recipe_Name, Angle_Type, Hook_Text, Search_Description
"""

import io
import pandas as pd
import streamlit as st


def _build_dataframe() -> pd.DataFrame:
    """
    Flatten session_state hooks + descriptions into a Canva-ready DataFrame.
    One row per hook (dynamic angles per recipe).
    """
    recipes = st.session_state.get("recipes", [])
    hooks = st.session_state.get("hooks", {})
    descriptions = st.session_state.get("descriptions", {})

    rows = []
    for recipe in recipes:
        name = recipe["name"]
        recipe_hooks = hooks.get(name, {})
        description = descriptions.get(name, "")

        # Iterate over actual angles present (dynamic)
        for angle, hook_text in recipe_hooks.items():
            hook_text = hook_text.strip()
            if not hook_text:
                continue
            rows.append({
                "Recipe_Name": name,
                "Angle_Type": angle,
                "Hook_Text": hook_text,
                "Search_Description": description,
                "Recipe_URL": recipe.get("url", ""),
                "Cook_Time": recipe.get("time", ""),
                "Benefit_Tag": recipe.get("benefit", ""),
            })

    return pd.DataFrame(rows)


def render_export():
    st.subheader("Canva Bulk Export")
    st.caption("Download the formatted CSV, then import it into Canva's Bulk Create feature.")

    # ── Guard checks ──────────────────────────────────────────────────────────
    if not st.session_state.get("batch_locked") or not st.session_state.get("recipes"):
        st.warning("⚠️ No batch locked. Go to **Step 1** first.")
        return

    if not st.session_state.get("hooks"):
        st.warning("⚠️ No hooks generated yet. Go to **Step 2 → AI Copy Engine** first.")
        return

    # ── Build CSV ─────────────────────────────────────────────────────────────
    df = _build_dataframe()

    if df.empty:
        st.error("No hook data found. Please re-generate in Step 2.")
        return

    # Canva-specific export (only the 4 columns Canva needs)
    canva_df = df[["Recipe_Name", "Angle_Type", "Hook_Text", "Search_Description"]].copy()

    # Full export (all columns, for your own records)
    full_df = df.copy()

    # Convert to CSV bytes
    canva_csv = canva_df.to_csv(index=False).encode("utf-8")
    full_csv = full_df.to_csv(index=False).encode("utf-8")

    # ── Stats ─────────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("Recipes", len(df["Recipe_Name"].unique()))
    col2.metric("Total hooks / rows", len(df))
    avg_angles = round(len(df) / max(len(df["Recipe_Name"].unique()), 1), 1)
    col3.metric("Avg angles / recipe", avg_angles)

    st.divider()

    # ── Preview ───────────────────────────────────────────────────────────────
    with st.expander("📋 Preview CSV (first 15 rows)", expanded=True):
        st.dataframe(canva_df.head(15), use_container_width=True, hide_index=True)

    st.divider()

    # ── Download buttons ──────────────────────────────────────────────────────
    col_dl1, col_dl2 = st.columns(2)

    with col_dl1:
        st.download_button(
            label="⬇️  Download canva_bulk_import.csv",
            data=canva_csv,
            file_name="canva_bulk_import.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
            help="Import this into Canva → Bulk Create. Maps Hook_Text to your text layer.",
        )
        st.caption("4 columns · Canva-ready · use this for bulk design production")

    with col_dl2:
        st.download_button(
            label="⬇️  Download full_export.csv",
            data=full_csv,
            file_name="pinterest_factory_full_export.csv",
            mime="text/csv",
            use_container_width=True,
            help="Full export including URLs, cook times, and benefit tags for your records.",
        )
        st.caption("7 columns · includes URLs, times, tags · for your records / Notion")

    st.divider()

    # ── Canva Bulk Create instructions ────────────────────────────────────────
    st.subheader("How to use in Canva — 4 steps")

    st.markdown("""
---

#### Step 1 — Set up your template

Open Canva and create (or open) your Pinterest pin template.
Make sure the **text layer you want to swap** has a clear name — e.g. `Hook Text`.
You need at least one text element connected to a data column.

> Target size: **1000 × 1500 px** (Pinterest optimal) or **1080 × 1920 px** (vertical).

---

#### Step 2 — Open Bulk Create

In the left sidebar, click **Apps** → search **Bulk Create** → open it.
Click **Upload CSV** and select `canva_bulk_import.csv` you just downloaded.

Canva will detect the columns: `Recipe_Name`, `Angle_Type`, `Hook_Text`, `Search_Description`.

---

#### Step 3 — Connect data to your design

Click **Connect data** in the Bulk Create panel.
Click on your **Hook Text layer** in the canvas.
In the dropdown, select **Hook_Text** as the data source.

Optional: Connect a second text layer to `Recipe_Name` if your template has a recipe title slot.

---

#### Step 4 — Generate and export

Click **Generate X designs** (X = number of rows in your CSV).
Canva creates one pin per hook row automatically.
Select all → **Download** → choose **JPG** or **PNG** at 1x.

> Naming tip: Canva names files by row number. Rename them using the `Recipe_Name` + `Angle_Type` from your CSV for easier organisation.

---

**After Canva:**
- Upload to Pinterest directly or use the native Pinterest scheduler
- Copy the `Search_Description` from the CSV into each pin's description field
- Schedule **3–5 pins per day** — do not post everything at once

---
    """)

    # ── Per-recipe summary ────────────────────────────────────────────────────
    st.subheader("Per-recipe hook summary")
    for recipe_name in df["Recipe_Name"].unique():
        recipe_df = df[df["Recipe_Name"] == recipe_name][["Angle_Type", "Hook_Text"]]
        with st.expander(f"**{recipe_name}**"):
            st.dataframe(recipe_df, use_container_width=True, hide_index=True)
            desc = df[df["Recipe_Name"] == recipe_name]["Search_Description"].iloc[0]
            st.caption(f"**Description:** {desc}")
            url = df[df["Recipe_Name"] == recipe_name]["Recipe_URL"].iloc[0]
            if url:
                st.caption(f"**URL:** {url}")
