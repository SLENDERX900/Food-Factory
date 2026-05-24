"""
Cross-platform scheduling workspace.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from utils.notion_planner import (
    create_schedule_entry,
    forecast_recipe_candidates,
    notion_enabled,
    query_upcoming_schedule,
    recipe_names_from_entries,
    summarize_upcoming_by_platform,
    update_schedule_entry,
)
from utils.post_scheduler import add_job, delete_job, due_jobs, list_queue, update_job
from utils.scheduler import build_schedule_slots, schedule_pin


def _queue_rows() -> list[dict]:
    rows = []
    for item in list_queue():
        rows.append(
            {
                "ID": item.get("id", ""),
                "Platform": item.get("platform", ""),
                "Recipe": item.get("recipe_name", ""),
                "Destination": item.get("destination", ""),
                "Title": item.get("title", ""),
                "Scheduled UTC": item.get("scheduled_for", ""),
                "Status": item.get("status", ""),
                "Mode": "Auto" if item.get("platform") == "pinterest" else "Manual Reminder",
                "Error": item.get("last_error", ""),
            }
        )
    return rows


def _sync_job_to_notion(job: dict) -> None:
    if not notion_enabled():
        return
    page_id = job.get("notion_page_id", "")
    if page_id:
        ok, message = update_schedule_entry(page_id, job)
        if not ok:
            update_job(job["id"], last_error=f"Notion sync failed: {message}")
        return

    ok, message, page_id = create_schedule_entry(job)
    if ok and page_id:
        update_job(job["id"], notion_page_id=page_id)
    else:
        update_job(job["id"], last_error=f"Notion sync failed: {message}")


def _enqueue_pinterest_jobs(start_date, posts_per_day: int, first_hour: int) -> int:
    recipes = st.session_state.get("recipes", [])
    packages = st.session_state.get("hook_packages", {})
    pin_descriptions = st.session_state.get("pin_descriptions", {})

    posts = []
    for recipe in recipes:
        name = recipe.get("name", "")
        for package in packages.get(name, []):
            angle = package.get("angle", "")
            hook = st.session_state.get("hooks", {}).get(name, {}).get(angle, package.get("hook", ""))
            description = pin_descriptions.get(name, {}).get(angle) or package.get("description", "")
            if hook:
                posts.append(
                    {
                        "recipe_name": name,
                        "title": hook,
                        "body": description,
                        "destination": "Pinterest board",
                        "source_url": recipe.get("url", ""),
                        "image_url": recipe.get("image_url", "") or recipe.get("url", ""),
                        "metadata": {"angle": angle},
                    }
                )

    slots = build_schedule_slots(
        len(posts),
        posts_per_day=posts_per_day,
        start_date=start_date,
        first_hour_utc=first_hour,
    )
    for index, post in enumerate(posts):
        job = add_job(platform="pinterest", scheduled_for=slots[index], **post)
        _sync_job_to_notion(job)
    return len(posts)


def _enqueue_reddit_jobs(start_date, posts_per_day: int, first_hour: int) -> int:
    drafts = st.session_state.get("reddit_drafts", [])
    slots = build_schedule_slots(
        len(drafts),
        posts_per_day=posts_per_day,
        start_date=start_date,
        first_hour_utc=first_hour,
    )
    for index, draft in enumerate(drafts):
        job = add_job(
            platform="reddit",
            recipe_name=draft.get("recipe_name", ""),
            title=draft.get("title", ""),
            body=draft.get("body", ""),
            destination=draft.get("subreddit", ""),
            source_url=draft.get("source_url", ""),
            image_url="",
            metadata={"query": draft.get("query", ""), "kind": draft.get("kind", "self")},
            scheduled_for=slots[index],
        )
        _sync_job_to_notion(job)
    return len(drafts)


def _push_pinterest_jobs() -> tuple[int, int]:
    success = 0
    failed = 0
    for job in list_queue():
        if job.get("platform") != "pinterest" or job.get("status") != "queued":
            continue
        scheduled_for = datetime.fromisoformat(job["scheduled_for"])
        ok, message = schedule_pin(
            job.get("title", ""),
            job.get("body", ""),
            job.get("source_url", ""),
            job.get("image_url", ""),
            scheduled_for,
        )
        if ok:
            updated = update_job(job["id"], status="scheduled_remote", platform_post_id=message, last_error="")
            if updated:
                _sync_job_to_notion(updated)
            success += 1
        else:
            updated = update_job(job["id"], status="failed", last_error=message)
            if updated:
                _sync_job_to_notion(updated)
            failed += 1
    return success, failed


def _mark_reddit_due_as_posted() -> tuple[int, int]:
    success = 0
    pending = 0
    for job in due_jobs():
        if job.get("platform") != "reddit":
            continue
        updated = update_job(job["id"], status="published", last_error="")
        if updated:
            _sync_job_to_notion(updated)
            success += 1
        else:
            pending += 1
    return success, pending


def _render_calendar() -> None:
    queue = list_queue()
    if not queue:
        st.info("No scheduled jobs yet.")
        return
    rows = []
    for job in queue:
        scheduled_raw = job.get("scheduled_for", "")
        try:
            scheduled_dt = datetime.fromisoformat(scheduled_raw)
            day_label = scheduled_dt.strftime("%Y-%m-%d")
            time_label = scheduled_dt.strftime("%H:%M UTC")
        except Exception:
            day_label = scheduled_raw[:10]
            time_label = scheduled_raw
        rows.append(
            {
                "Day": day_label,
                "Time": time_label,
                "Platform": job.get("platform", "").title(),
                "Recipe": job.get("recipe_name", ""),
                "Action": "Auto-post" if job.get("platform") == "pinterest" else "Manual Reddit post reminder",
                "Destination": job.get("destination", ""),
                "Status": job.get("status", ""),
            }
        )
    df = pd.DataFrame(rows).sort_values(by=["Day", "Time", "Platform"])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("**Daily View**")
    for day in df["Day"].drop_duplicates().tolist():
        day_df = df[df["Day"] == day][["Time", "Platform", "Recipe", "Action", "Destination", "Status"]]
        with st.expander(day, expanded=False):
            st.dataframe(day_df, use_container_width=True, hide_index=True)


def render_scheduler_hub() -> None:
    st.subheader("Scheduler Hub")
    st.caption("Pinterest uses real API scheduling. Reddit uses scheduled reminders so you know exactly when to post manually.")

    queue = list_queue()
    queued = len([item for item in queue if item.get("status") == "queued"])
    remote = len([item for item in queue if item.get("status") == "scheduled_remote"])
    due_reddit = len([item for item in due_jobs() if item.get("platform") == "reddit"])
    col1, col2, col3 = st.columns(3)
    col1.metric("Queued jobs", queued)
    col2.metric("Pinterest auto-scheduled", remote)
    col3.metric("Reddit reminders due", due_reddit)

    overview_tab, enqueue_tab, execute_tab, queue_tab = st.tabs(["Calendar", "Add Jobs", "Run Scheduling", "Queue"])

    with overview_tab:
        _render_calendar()
        st.divider()
        if notion_enabled():
            upcoming_entries = query_upcoming_schedule(days=14)
            counts = summarize_upcoming_by_platform(upcoming_entries)
            scheduled_recipe_names = recipe_names_from_entries(upcoming_entries)
            forecast = forecast_recipe_candidates(st.session_state.get("recipes", []), scheduled_recipe_names, limit=5)

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Notion Upcoming Counts**")
                if counts:
                    for platform, count in counts.items():
                        st.write(f"{platform}: {count}")
                else:
                    st.caption("No upcoming scheduled entries found in Notion.")
            with c2:
                st.markdown("**Next-Week Forecasted Recipes**")
                if forecast:
                    for recipe_name in forecast:
                        st.write(f"- {recipe_name}")
                else:
                    st.caption("No unscheduled recipes available from the current batch to forecast.")
        else:
            st.info("Connect Notion to see cross-platform counts and forecast suggestions here.")

    with enqueue_tab:
        default_date = (datetime.now(timezone.utc) + timedelta(days=1)).date()
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            start_date = st.date_input("Start date (UTC)", value=default_date, key="hub_start_date")
        with col_b:
            posts_per_day = st.slider("Posts per day", min_value=1, max_value=6, value=2, key="hub_posts_per_day")
        with col_c:
            first_hour = st.slider("First hour UTC", min_value=0, max_value=23, value=14, key="hub_first_hour")

        left, right = st.columns(2)
        with left:
            ready_pinterest = bool(st.session_state.get("hook_packages"))
            if st.button("Queue Pinterest Content", use_container_width=True, disabled=not ready_pinterest):
                count = _enqueue_pinterest_jobs(start_date, posts_per_day, first_hour)
                st.success(f"Queued {count} Pinterest job(s) and synced them to Notion when available.")
                st.rerun()
            if not ready_pinterest:
                st.caption("Generate Pinterest hooks first to queue Pinterest posts.")

        with right:
            ready_reddit = bool(st.session_state.get("reddit_drafts"))
            if st.button("Queue Reddit Reminders", use_container_width=True, disabled=not ready_reddit):
                count = _enqueue_reddit_jobs(start_date, posts_per_day, first_hour)
                st.success(f"Queued {count} Reddit reminder job(s) and synced them to Notion when available.")
                st.rerun()
            if not ready_reddit:
                st.caption("Generate Reddit drafts first to queue Reddit reminders.")

    with execute_tab:
        st.markdown("**Pinterest**")
        st.caption("Queued Pinterest jobs are pushed to Pinterest immediately with their future publish times, then reflected back in Notion.")
        if st.button("Push Queued Pinterest Jobs", type="primary", use_container_width=True):
            success, failed = _push_pinterest_jobs()
            if failed:
                st.warning(f"Pinterest scheduling complete: {success} succeeded, {failed} failed.")
            else:
                st.success(f"Scheduled {success} Pinterest job(s) on Pinterest.")
            st.rerun()

        st.divider()
        st.markdown("**Reddit**")
        st.caption("Reddit entries act as reminders on the calendar. When you’ve posted manually, mark them as posted so Notion stays accurate.")
        due_rows = [job for job in due_jobs() if job.get("platform") == "reddit"]
        if due_rows:
            for job in due_rows:
                st.write(f"{job.get('scheduled_for', '')} · r/{job.get('destination', '')} · {job.get('recipe_name', '')}")
        else:
            st.caption("No Reddit reminders are due right now.")
        if st.button("Mark Due Reddit Reminders as Posted", use_container_width=True):
            success, pending = _mark_reddit_due_as_posted()
            if pending:
                st.warning(f"Marked {success} reminder(s) as posted. {pending} could not be updated.")
            else:
                st.success(f"Marked {success} Reddit reminder(s) as posted.")
            st.rerun()

    with queue_tab:
        rows = _queue_rows()
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            removable = {f"{row['Platform']} · {row['Recipe']} · {row['Title'][:40]}": row["ID"] for row in rows}
            selected = st.selectbox("Remove job", options=[""] + list(removable.keys()), key="remove_job_key")
            if selected and st.button("Delete Selected Job", use_container_width=True):
                delete_job(removable[selected])
                st.success("Job removed.")
                st.rerun()
        else:
            st.info("No scheduled jobs yet.")
