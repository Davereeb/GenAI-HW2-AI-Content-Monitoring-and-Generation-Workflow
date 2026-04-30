"""
app.py — Streamlit UI for AI Retail Content Workflow
Launch: streamlit run app.py
"""

import io
import json
import os
import re
import sqlite3
from contextlib import redirect_stdout

import pandas as pd
import streamlit as st

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Retail News Workflow",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from config import (
    AI_SCORE_MIN,
    CATEGORIES,
    CLASSIFICATION_MODEL,
    DB_PATH,
    GENERATION_MODEL,
    GLOBAL_ARTICLE_LIMIT,
    IMAGE_MODEL,
    KOL_MODEL,
    KOL_STYLE_GUIDE_PATH,
    MIN_DIVERSITY_CATEGORIES,
    OPENROUTER_API_KEY,
    OUTPUT_IMAGES_DIR,
    OUTPUT_POSTS_DIR,
    RETAIL_SCORE_MIN,
    ROUTING_MODEL,
    RSS_SOURCES,
    TARGET_CATEGORIES,
    TOP_N_MAX,
    TOP_N_MIN,
    TOP_N_PERCENT,
)
from scheduler import get_next_run_time, start_scheduler

# Start background scheduler (idempotent — safe on every page reload)
start_scheduler()

# ── Utilities ──────────────────────────────────────────────────────────────────

def run_task(module_name: str) -> tuple[str, str]:
    """Run a task module's run(), capturing stdout. Returns (result, logs)."""
    import importlib
    buf = io.StringIO()
    try:
        mod = importlib.import_module(module_name)
        with redirect_stdout(buf):
            result = mod.run()
        return result, buf.getvalue()
    except Exception as e:
        return f"FAILED: {e}", buf.getvalue()


def db_stats() -> dict:
    if not os.path.exists(DB_PATH):
        return {"total": 0, "relevant": 0, "classified": 0, "posts": 0}
    conn = sqlite3.connect(DB_PATH)
    stats = {
        "total":      conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
        "relevant":   conn.execute("SELECT COUNT(*) FROM articles WHERE is_relevant=1").fetchone()[0],
        "classified": conn.execute("SELECT COUNT(*) FROM articles WHERE category IS NOT NULL").fetchone()[0],
        "posts":      0,
    }
    try:
        stats["posts"] = conn.execute("SELECT COUNT(*) FROM generated_posts").fetchone()[0]
    except Exception:
        pass
    conn.close()
    return stats


def query_articles(where: str = "1=1") -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        f"SELECT title, source, published, ai_score, retail_score, combined_score, "
        f"is_relevant, category "
        f"FROM articles WHERE {where} ORDER BY fetched_at DESC",
        conn,
    )
    conn.close()
    return df


def query_generated_posts(where: str = "1=1") -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(
            f"SELECT id, category, article_title, article_source, "
            f"post_text, hashtags, selection_reason, image_path, generated_at "
            f"FROM generated_posts WHERE {where} ORDER BY generated_at DESC",
            conn,
        )
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🛍️ Retail AI Workflow")

    if OPENROUTER_API_KEY:
        st.success("✅ OpenRouter API key loaded")
    else:
        st.error("❌ No API key — add OPENROUTER_API_KEY to .env")

    st.divider()

    st.subheader("Model Assignment")
    st.markdown(f"""
| Task | Model |
|------|-------|
| Routing (T2) | `{ROUTING_MODEL}` |
| Classify (T3) | `{CLASSIFICATION_MODEL}` |
| KOL (T4) | `{KOL_MODEL}` |
| Generate (T5) | `{GENERATION_MODEL}` |
| Image (T5) | `{IMAGE_MODEL}` (通义万相) |
""")

    st.divider()

    st.subheader("Pipeline Settings")
    st.caption(f"🔢 Article limit: Top {GLOBAL_ARTICLE_LIMIT}")
    st.caption(
        f"🎯 Selection: Top {int(TOP_N_PERCENT*100)}% "
        f"({TOP_N_MIN}–{TOP_N_MAX} articles, both scores ≥{AI_SCORE_MIN})"
    )
    st.caption(f"📡 RSS sources: {len(RSS_SOURCES)}")
    st.caption(f"🏷️ Categories: {len(CATEGORIES)}")
    st.caption(f"🕗 Next scheduled run: {get_next_run_time()}")

    st.divider()

    run_all = st.button("▶▶ Run Full Workflow", type="primary", use_container_width=True)
    st.caption("Runs all 5 tasks in sequence")

    st.divider()

    st.subheader("🔄 Reset")
    reset_clicked = st.button("Reset Scores & Re-run T2", use_container_width=True)
    st.caption("Clears stale/errored scores and re-scores all articles")


# ── Header & metrics ───────────────────────────────────────────────────────────
st.title("🛍️ AI Retail Content Monitoring & Generation")

stats = db_stats()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Articles in DB",   stats["total"])
c2.metric("Retail-Relevant",  stats["relevant"])
c3.metric("Classified",       stats["classified"])
c4.metric("Posts Generated",  stats["posts"])

st.divider()

# ── Reset handler ──────────────────────────────────────────────────────────────
if reset_clicked:
    import importlib, task2_router as _t2
    importlib.reload(_t2)
    buf = io.StringIO()
    with st.spinner("Resetting all scores and re-scoring…"):
        try:
            with redirect_stdout(buf):
                result = _t2.run(force_rescore=True)
            st.session_state.update(t2_res=result, t2_logs=buf.getvalue())
        except Exception as e:
            st.session_state.update(t2_res=f"FAILED: {e}", t2_logs=buf.getvalue())
    st.rerun()

# ── Full Workflow runner ───────────────────────────────────────────────────────
if run_all:
    TASKS = [
        ("📡 Task 1: Monitor",     "task1_monitor"),
        ("🎯 Task 2: Route",       "task2_router"),
        ("🏷️ Task 3: Classify",    "task3_classifier"),
        ("👤 Task 4: KOL Research", "task4_kol_research"),
        ("✍️ Task 5: Generate",    "task5_content_gen"),
    ]
    prog = st.progress(0, text="Starting workflow…")
    with st.status("Running full workflow…", expanded=True) as wf_status:
        for i, (label, module) in enumerate(TASKS):
            st.write(f"Running **{label}**…")
            result, _ = run_task(module)
            st.write(f"✅ {result}")
            prog.progress((i + 1) / len(TASKS), text=f"Completed {label}")
    wf_status.update(label="✅ Workflow complete!", state="complete")
    st.rerun()

# ── Tabs ───────────────────────────────────────────────────────────────────────
t1, t2, t3, t4, t5, t6 = st.tabs([
    "📡 Task 1: Monitor",
    "🎯 Task 2: Route",
    "🏷️ Task 3: Classify",
    "👤 Task 4: KOL Research",
    "✍️ Task 5: Generate",
    "📚 History",
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — Monitor
# ─────────────────────────────────────────────────────────────────────────────
with t1:
    st.subheader("Daily AI News Monitoring")
    st.caption(
        f"Fetches all entries from {len(RSS_SOURCES)} RSS sources → AI keyword filter → "
        f"global Top-{GLOBAL_ARTICLE_LIMIT} by recency → stores in SQLite."
    )

    if st.button("▶ Fetch News", type="primary", key="bt1"):
        with st.spinner("Fetching from RSS sources…"):
            res, logs = run_task("task1_monitor")
        st.session_state.update(t1_res=res, t1_logs=logs)

    if "t1_res" in st.session_state:
        st.success(st.session_state["t1_res"])
        with st.expander("Logs"):
            st.code(st.session_state["t1_logs"])

    df = query_articles()
    if not df.empty:
        st.subheader(f"Articles in DB — {len(df)} total")
        display_t1 = df[["title", "source", "published"]].copy()
        display_t1["published"] = (
            pd.to_datetime(display_t1["published"], utc=True, errors="coerce")
            .dt.strftime("%Y-%m-%d")
            .fillna("")
        )
        st.dataframe(display_t1, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — Route
# ─────────────────────────────────────────────────────────────────────────────
with t2:
    st.subheader("Two-Dimension Relevance Routing")
    st.caption(
        f"Scores each article on **AI significance** (×0.7) and **retail value** (×0.3) "
        f"using **{ROUTING_MODEL}**. Both scores must be ≥{AI_SCORE_MIN}. "
        f"All passing articles are forwarded to Task 3 for **diversity-aware selection** "
        f"(≥{MIN_DIVERSITY_CATEGORIES} categories guaranteed)."
    )

    with st.expander("📊 Scoring Rubric", expanded=True):
        st.markdown("""
| Dimension | Weight | 9–10 | 7–8 | 5–6 | 3–4 | 1–2 |
|-----------|--------|------|-----|-----|-----|-----|
| **AI Significance** | ×0.7 | Breakthrough model / API release (GPT, Gemini, Llama…) | Major capability update, agentic system, enterprise AI launch | Incremental update, AI governance, dev tooling | Niche academic paper, distant-timeline research | Non-AI content |
| **Retail Value** | ×0.3 | Direct retail use case (e-commerce, supply chain, pricing…) | Clear business application within 12 months | Plausible retail angle, general enterprise AI | Indirect relevance | No retail relevance |

**Combined = AI × 0.7 + Retail × 0.3** &nbsp;|&nbsp; Mandatory: **both scores ≥ 3** &nbsp;|&nbsp; All passing articles → Task 3 diversity selection (≥3 categories, max 8)
""")

    col_score, col_reset = st.columns([2, 1])
    run_t2   = col_score.button("▶ Score Articles", type="primary", key="bt2")
    reset_t2 = col_reset.button("🔄 Reset & Re-score", key="bt2_reset",
                                 help="Clears previous scores and re-scores everything")

    if run_t2:
        with st.spinner(f"Scoring with {ROUTING_MODEL}…"):
            res, logs = run_task("task2_router")
        st.session_state.update(t2_res=res, t2_logs=logs)

    if reset_t2:
        import importlib, task2_router as _t2r
        importlib.reload(_t2r)
        buf = io.StringIO()
        with st.spinner("Resetting all scores and re-scoring…"):
            try:
                with redirect_stdout(buf):
                    result = _t2r.run(force_rescore=True)
                st.session_state.update(t2_res=result, t2_logs=buf.getvalue())
            except Exception as e:
                st.session_state.update(t2_res=f"FAILED: {e}", t2_logs=buf.getvalue())
        st.rerun()

    if "t2_res" in st.session_state:
        st.success(st.session_state["t2_res"])
        with st.expander("Logs"):
            st.code(st.session_state["t2_logs"])

    df = query_articles("ai_score IS NOT NULL")
    if not df.empty:
        st.subheader("Scored Articles")
        col_chart, col_table = st.columns([1, 2])

        with col_chart:
            dist = df["combined_score"].dropna().round(1).value_counts().sort_index().rename("count")
            st.bar_chart(dist, color="#6366f1")
            st.caption("Distribution of combined scores")

        with col_table:
            display = df[["title", "source", "ai_score", "retail_score", "combined_score"]].copy()
            # Round to 2 decimal places and sort high → low
            for col in ["ai_score", "retail_score", "combined_score"]:
                display[col] = display[col].round(2)
            display = display.sort_values("combined_score", ascending=False)
            display["status"] = df.loc[display.index].apply(
                lambda r: "✅ Selected" if r["is_relevant"] == 1
                else ("❌ Eliminated" if (
                    pd.notna(r["ai_score"]) and pd.notna(r["retail_score"]) and
                    (r["ai_score"] < AI_SCORE_MIN or r["retail_score"] < RETAIL_SCORE_MIN)
                ) else "⬇️ Not top N"),
                axis=1,
            )

            def _row_style(row):
                if row.get("status", "").startswith("❌"):
                    return ["background-color:#fee2e2"] * len(row)
                if row.get("status", "").startswith("✅"):
                    return ["background-color:#dcfce7"] * len(row)
                return [""] * len(row)

            st.dataframe(
                display.style.apply(_row_style, axis=1),
                use_container_width=True,
                hide_index=True,
            )

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Classify
# ─────────────────────────────────────────────────────────────────────────────
with t3:
    st.subheader("Information Classification")
    st.caption(
        f"Classifies relevant articles into {len(CATEGORIES)} retail AI categories "
        f"using **{CLASSIFICATION_MODEL}**."
    )

    if st.button("▶ Classify Articles", type="primary", key="bt3"):
        with st.spinner(f"Classifying with {CLASSIFICATION_MODEL}…"):
            res, logs = run_task("task3_classifier")
        st.session_state.update(t3_res=res, t3_logs=logs)

    if "t3_res" in st.session_state:
        st.success(st.session_state["t3_res"])
        with st.expander("Logs"):
            st.code(st.session_state["t3_logs"])

    df = query_articles("category IS NOT NULL")
    if not df.empty:
        st.subheader("Classified Articles")
        col_chart, col_table = st.columns([1, 2])

        with col_chart:
            import matplotlib.pyplot as plt
            counts = df["category"].value_counts().rename("count")
            fig, ax = plt.subplots(figsize=(4, 4))
            ax.pie(
                counts.values,
                labels=counts.index,
                autopct="%1.0f%%",
                startangle=90,
                colors=["#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6"],
            )
            ax.axis("equal")
            st.pyplot(fig)
            plt.close(fig)

        with col_table:
            st.dataframe(
                df[["title", "source", "category", "combined_score"]],
                use_container_width=True,
                hide_index=True,
            )

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — KOL Research
# ─────────────────────────────────────────────────────────────────────────────
with t4:
    st.subheader("KOL Style Research")
    guide_exists = os.path.exists(KOL_STYLE_GUIDE_PATH)
    st.caption(
        f"Analyzes communication styles of 5 AI thought leaders using **{KOL_MODEL}**. "
        "Style guide is **cached after the first run** — no API calls on subsequent loads. "
        "Use *Force Re-analyze* to refresh."
    )
    if guide_exists:
        st.success("✅ Cached style guide found — click **Load Style Guide** to display it.")

    col_kol1, col_kol2 = st.columns([2, 1])
    run_kol   = col_kol1.button(
        "▶ Load Style Guide" if guide_exists else "▶ Analyze KOLs",
        type="primary", key="bt4",
    )
    force_kol = col_kol2.button(
        "🔄 Force Re-analyze", key="bt4_force",
        help="Re-runs LLM analysis for all KOLs, overwriting the cache",
    )

    if run_kol:
        with st.spinner("Loading cached style guide…" if guide_exists else f"Analyzing with {KOL_MODEL}…"):
            res, logs = run_task("task4_kol_research")   # calls run(force=False)
        st.session_state.update(t4_res=res, t4_logs=logs)

    if force_kol:
        import importlib, task4_kol_research as _t4
        importlib.reload(_t4)
        buf = io.StringIO()
        with st.spinner(f"Re-analyzing all KOLs with {KOL_MODEL}…"):
            try:
                with redirect_stdout(buf):
                    result = _t4.run(force=True)
                st.session_state.update(t4_res=result, t4_logs=buf.getvalue())
            except Exception as e:
                st.session_state.update(t4_res=f"FAILED: {e}", t4_logs=buf.getvalue())
        st.rerun()

    if "t4_res" in st.session_state:
        st.success(st.session_state["t4_res"])
        with st.expander("Logs"):
            st.code(st.session_state["t4_logs"])

    if os.path.exists(KOL_STYLE_GUIDE_PATH):
        with open(KOL_STYLE_GUIDE_PATH, encoding="utf-8") as f:
            guide = json.load(f)

        # LinkedIn URLs + avatar accent colours for each KOL
        KOL_META = {
            "Andrew Ng":        {"linkedin": "https://www.linkedin.com/in/andrewyng/",       "color": "0D8ABC"},
            "Andrej Karpathy":  {"linkedin": "https://www.linkedin.com/in/andrejkarpathy/",  "color": "7C3AED"},
            "Sam Altman":       {"linkedin": "https://www.linkedin.com/in/samaltman/",       "color": "0EA5E9"},
            "Kai-Fu Lee":       {"linkedin": "https://www.linkedin.com/in/kaifulee/",        "color": "DC2626"},
            "Mustafa Suleyman": {"linkedin": "https://www.linkedin.com/in/mustafasuleyman/", "color": "D97706"},
        }

        # ── Retail Style Synthesis card ───────────────────────────────────────
        synthesis = guide.get("synthesis", {})
        if synthesis and "error" not in synthesis:
            st.markdown("### 📋 Retail Style Synthesis")
            with st.container(border=True):
                sc1, sc2 = st.columns(2)
                with sc1:
                    if synthesis.get("recommended_hook_styles"):
                        st.markdown("**🎯 Recommended Hook Styles**")
                        for h in synthesis["recommended_hook_styles"]:
                            st.markdown(f"- {h}")
                    if synthesis.get("recommended_structure"):
                        st.markdown("**📐 Post Structure**")
                        st.markdown(synthesis["recommended_structure"])
                    if synthesis.get("tone_guidelines"):
                        st.markdown("**🎨 Tone Guidelines**")
                        st.markdown(synthesis["tone_guidelines"])
                    if synthesis.get("post_template"):
                        st.markdown("**📝 Post Template**")
                        st.code(synthesis["post_template"], language=None)
                with sc2:
                    if synthesis.get("credibility_approach"):
                        st.markdown("**🏆 Credibility Approach**")
                        st.markdown(synthesis["credibility_approach"])
                    if synthesis.get("engagement_strategy"):
                        st.markdown("**💬 Engagement Strategy**")
                        for t in synthesis["engagement_strategy"]:
                            st.markdown(f"- {t}")
                    if synthesis.get("phrases_to_use"):
                        st.markdown("**✅ Power Phrases**")
                        st.markdown("  ".join(f"`{p}`" for p in synthesis["phrases_to_use"]))
                    if synthesis.get("phrases_to_avoid"):
                        st.markdown("**❌ Avoid**")
                        st.markdown("  ".join(f"~~{p}~~" for p in synthesis["phrases_to_avoid"]))

        st.markdown("---")

        # ── Individual KOL cards ──────────────────────────────────────────────
        st.markdown("### 👥 Individual KOL Profiles")
        kols = guide.get("kols", {})
        kol_cols = st.columns(len(kols) or 1)

        for col, (name, profile) in zip(kol_cols, kols.items()):
            meta     = KOL_META.get(name, {"linkedin": "#", "color": "6B7280"})
            initials = "".join(w[0] for w in name.split()[:2])
            avatar   = (f"https://ui-avatars.com/api/?name={initials}"
                        f"&size=120&background={meta['color']}&color=fff&bold=true&rounded=true")

            with col:
                # Avatar + clickable name
                st.markdown(
                    f"""<div style="text-align:center;margin-bottom:10px;">
                        <img src="{avatar}" width="80"
                             style="border-radius:50%;box-shadow:0 2px 8px rgba(0,0,0,.15);"/>
                        <br/><br/>
                        <a href="{meta['linkedin']}" target="_blank"
                           style="font-weight:700;font-size:14px;text-decoration:none;
                                  color:#{meta['color']};">
                           🔗 {name}
                        </a>
                    </div>""",
                    unsafe_allow_html=True,
                )

                # Style-summary card
                if "error" in profile:
                    st.error("Analysis failed")
                else:
                    with st.container(border=True):
                        tone = profile.get("tone", [])
                        tone_str = " · ".join(tone) if isinstance(tone, list) else str(tone)
                        hook     = str(profile.get("hook_style", ""))
                        phrases  = profile.get("signature_phrases", [])
                        retail   = str(profile.get("retail_applicability", ""))
                        engage   = str(profile.get("engagement_tactics", ""))

                        st.markdown(f"**Tone**  \n{tone_str}")
                        st.markdown(f"**Hook style**  \n{hook[:140]}{'…' if len(hook)>140 else ''}")

                        if phrases:
                            st.markdown("**Signature phrases**")
                            items = phrases if isinstance(phrases, list) else [phrases]
                            for p in items[:3]:
                                st.markdown(f"- *{p}*")

                        if engage:
                            st.markdown(f"**Engagement**  \n{engage[:160]}{'…' if len(engage)>160 else ''}")

                        if retail:
                            st.markdown(f"**Retail angle**  \n{retail[:200]}{'…' if len(retail)>200 else ''}")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — Generate
# ─────────────────────────────────────────────────────────────────────────────
with t5:
    st.subheader("LinkedIn Content Generation")
    st.caption(
        f"Generates **{len(TARGET_CATEGORIES)} posts** using **{GENERATION_MODEL}**, "
        f"each in a different KOL's style (rotating). "
        f"Images via **通义万相** (`{IMAGE_MODEL}`). "
        f"Set `IMAGE_API_KEY` in `.env` — get a key at dashscope.aliyun.com."
    )

    if st.button("▶ Generate Content", type="primary", key="bt5"):
        with st.spinner(f"Generating with {GENERATION_MODEL}…"):
            res, logs = run_task("task5_content_gen")
        st.session_state.update(t5_res=res, t5_logs=logs)

    if "t5_res" in st.session_state:
        st.success(st.session_state["t5_res"])
        with st.expander("Logs"):
            st.code(st.session_state["t5_logs"])

    from prompts.generation_prompt import get_dalle_prompt

    # Show only the 5 most recent posts (DB is also trimmed to 5 after each run)
    posts_df = query_generated_posts(
        "id IN (SELECT id FROM generated_posts ORDER BY generated_at DESC LIMIT 5)"
    )
    if not posts_df.empty:
        st.subheader(f"Latest Posts — {len(posts_df)} total")
        for _, row in posts_df.iterrows():
            with st.container(border=True):
                # Header: category + KOL badge
                sel = row.get("selection_reason", "")
                kol_label = ""
                if "KOL:" in sel:
                    kol_label = sel.split("|")[0].replace("KOL:", "").strip()
                header_cols = st.columns([4, 1])
                header_cols[0].markdown(f"#### {row['category']}")
                if kol_label:
                    header_cols[1].info(f"✍️ {kol_label}")

                # Source attribution
                st.caption(
                    f"📰 **{row['article_title'][:80]}** — {row['article_source']}  |  {sel}"
                )

                col_text, col_img = st.columns([3, 2])

                # ── Left: rendered post + hashtags + one combined copy block ──
                with col_text:
                    st.markdown(row["post_text"])

                    try:
                        tags = json.loads(row["hashtags"]) if row["hashtags"] else []
                    except Exception:
                        tags = []
                    if tags:
                        st.markdown(" ".join(f"`{t}`" for t in tags))

                    # Single combined copy block (post body + hashtags)
                    combined_copy = row["post_text"]
                    if tags:
                        combined_copy += "\n\n" + " ".join(tags)
                    st.code(combined_copy, language=None)

                # ── Right: image (if available) + always-visible image prompt ──
                with col_img:
                    img_path = row.get("image_path", "")
                    if img_path and os.path.exists(img_path):
                        st.image(img_path, use_container_width=True)
                    else:
                        st.markdown(
                            "<div style='background:#f0f2f6;border-radius:8px;"
                            "padding:20px;text-align:center;color:#888;'>"
                            "🖼️ Image not yet generated</div>",
                            unsafe_allow_html=True,
                        )

                    # Always show the image prompt (copyable) below the image
                    cat_slug_val = re.sub(r"[^a-z0-9]+", "_", row["category"].lower()).strip("_")
                    date_str_val = row["generated_at"][:10].replace("-", "")
                    prompt_f = os.path.join(
                        OUTPUT_IMAGES_DIR,
                        f"{cat_slug_val}_{date_str_val}_prompt.txt",
                    )
                    if os.path.exists(prompt_f):
                        with open(prompt_f) as pf:
                            saved_prompt = pf.read().split("\n\n", 1)[-1]  # strip header line
                    else:
                        saved_prompt = get_dalle_prompt(row["category"], row["article_title"])

                    with st.expander("🎨 Image Prompt — copy to 通义万相 / Midjourney"):
                        st.code(saved_prompt, language=None)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 6 — History
# ─────────────────────────────────────────────────────────────────────────────
with t6:
    st.subheader("Generation History")
    st.caption(f"All LinkedIn posts generated by the workflow (last 30 days).")

    posts_df = query_generated_posts()
    if posts_df.empty:
        st.info("No posts generated yet. Run Task 5 to generate your first post.")
    else:
        # Filters
        col_f1, col_f2 = st.columns(2)
        all_cats = ["All categories"] + sorted(posts_df["category"].unique().tolist())
        selected_cat = col_f1.selectbox("Filter by category", all_cats)
        search_term  = col_f2.text_input("Search post text", placeholder="keyword…")

        filtered = posts_df.copy()
        if selected_cat != "All categories":
            filtered = filtered[filtered["category"] == selected_cat]
        if search_term:
            mask = (
                filtered["post_text"].str.contains(search_term, case=False, na=False) |
                filtered["article_title"].str.contains(search_term, case=False, na=False)
            )
            filtered = filtered[mask]

        st.caption(f"Showing {len(filtered)} of {len(posts_df)} posts")

        # Summary table
        summary = filtered[["generated_at", "category", "article_source", "selection_reason"]].copy()
        summary["generated_at"] = summary["generated_at"].str[:16]
        st.dataframe(summary, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Post Detail")

        for _, row in filtered.iterrows():
            date_label = row["generated_at"][:16]
            with st.expander(f"[{date_label}]  {row['category']}  —  {row['article_title'][:60]}"):
                st.caption(f"Source: {row['article_source']}  |  {row['selection_reason']}")

                try:
                    tags = json.loads(row["hashtags"]) if row["hashtags"] else []
                except Exception:
                    tags = []

                st.markdown(row["post_text"])
                if tags:
                    st.markdown(" ".join(f"`{t}`" for t in tags))

                col_copy, col_img = st.columns([2, 1])
                with col_copy:
                    full_text = row["post_text"] + ("\n\n" + " ".join(tags) if tags else "")
                    st.code(full_text, language=None)

                with col_img:
                    img_path = row.get("image_path", "")
                    if img_path and os.path.exists(img_path):
                        st.image(img_path, use_container_width=True)
