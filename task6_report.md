# Workflow, Prompt Optimization and Progress Report

**Course:** Generative AI Applications  
**Assignment:** HW2 — AI Retail Content Monitoring & Generation Workflow  
**Date:** April 2026

---

## 1. Workflow Architecture and Design Logic

### Overview

The system is a fully automated five-task pipeline that converts raw AI news into polished, ready-to-publish LinkedIn thought leadership content tailored for retail industry executives. It runs on a daily schedule and exposes a Streamlit web interface for both monitoring and manual control.

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│               Daily Trigger — 08:00 Beijing CST              │
│               (APScheduler BackgroundScheduler)               │
└─────────────────────────┬────────────────────────────────────┘
                          ▼
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ TASK 1   │─▶│ TASK 2   │─▶│ TASK 3   │─▶│ TASK 4   │─▶│ TASK 5   │
│ Monitor  │  │ Route    │  │ Classify │  │ KOL      │  │ Generate │
│          │  │          │  │          │  │ Research │  │          │
│ 8 RSS    │  │ AI×0.7   │  │ 5 retail │  │ 5 KOLs   │  │ LinkedIn │
│ sources  │  │ +Retail  │  │ AI cats  │  │ cached   │  │ post +   │
│ Top 10   │  │ ×0.3     │  │ Diversity│  │ rotation │  │ image    │
│ articles │  │ both ≥3  │  │ ≥3 cats  │  │          │  │          │
└──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
                                                               │
                                               ┌───────────────▼──────────────┐
                                               │ SQLite DB · Email · History  │
                                               └──────────────────────────────┘
```

### Design Principles

**Separation of concerns.** Each task is an independent Python module with a `run()` entry point. The orchestrator (`workflow.py`) chains them; the UI (`app.py`) calls each independently. This makes individual tasks testable and replaceable.

**Persistence via SQLite.** Every intermediate result — raw articles, scores, categories, generated posts — is stored in a local SQLite database. Any task can be re-run without re-executing earlier steps, and the UI displays historical data without touching the LLM.

**Configuration centralised in `config.py`.** All thresholds, model names, weights, and schedule parameters are defined once. Changing the scoring weight requires editing one line.

**Graceful degradation.** Every API call has retry logic and a fallback. If image generation fails, a prompt `.txt` file is saved. If JSON parsing fails, three recovery strategies run before falling back to raw text. No single failure crashes the pipeline.

---

## 2. Key Challenges Encountered

### Challenge 1 — Geographic API Restrictions

**Problem:** All OpenAI, Anthropic, and Google endpoints on OpenRouter returned HTTP 403 "violation of provider Terms of Service" from the deployment environment (mainland China). This blocked every LLM call at launch.

**Resolution:** Switched all text models to `deepseek/deepseek-chat` (Chinese company, fully accessible). Replaced DALL-E 3 and SiliconFlow (both blocked via OpenRouter) with 通义万相 `wanx2.1-t2i-turbo` via Alibaba DashScope — accessible and free-tier.

**Lesson:** API accessibility must be validated in the deployment region before architecture decisions are finalised. A single `config.py` model assignment made the switch trivial.

---

### Challenge 2 — Malformed JSON from LLM Responses

**Problem:** DeepSeek occasionally returned invalid JSON — unescaped newlines inside string values, trailing commas, or extra text before the opening brace. A single `json.loads()` call caused silent failures: the entire raw JSON blob was stored as the post body and displayed to readers.

**Example failure output visible to users:**
```
{ "post_text": "By 2025, AI will power 80% of retail decisions—
and GPT-5.5 is the engine...", "hashtags": ["#RetailAI"...] }
```

**Resolution:** Implemented a three-strategy extraction function (`_parse_post_response`):
1. Strip markdown fences → `json.loads()` directly
2. Find the outermost `{...}` block with regex → `json.loads()`
3. Regex-extract `post_text` and `hashtags` values individually, handling unescaped newlines explicitly

The same pattern was applied to KOL profile parsing in Task 4.

---

### Challenge 3 — Category Diversity Collapse

**Problem:** Task 2 originally selected the top 20% of articles globally by combined score. The highest-scoring articles were almost always about AI model releases (category: "AI Infrastructure & Tools"). Task 3 classified these pre-filtered articles — all into the same category. Task 5 then had no articles for other target categories and reused the same source, producing near-identical posts.

**Resolution:** Redesigned the selection pipeline:
- **Task 2** now marks ALL articles passing mandatory minimums as candidates (no top-N% cut), giving Task 3 a larger, more diverse pool.
- **Task 3** adds a diversity-aware re-selection step after classification:
  - Phase 1: take the best article per category (guarantees breadth)
  - Phase 2: fill remaining slots up to `TOP_N_MAX=8` by combined score
  - `MIN_DIVERSITY_CATEGORIES=3` is enforced as a hard constraint

---

### Challenge 4 — KOL Analysis Failure

**Problem:** The LLM produced malformed JSON for Jensen Huang — he is primarily a keynote speaker with limited LinkedIn content, so the model generated a complex response that broke JSON structure at character 1433. The broken entry was cached, showing a permanent "Analysis failed" card in the UI.

**Resolution:** Replaced Jensen Huang with Sam Altman (OpenAI CEO, highly active on social media). Added 2-attempt retry logic to `analyze_kol()` and robust JSON parsing (`_parse_kol_json`). Patched the cached style guide to remove the stale error entry.

---

### Challenge 5 — Async Image Generation API

**Problem:** Alibaba DashScope's 通义万相 API is asynchronous — it returns a `task_id` on submission and requires polling. The initial implementation had no retry on poll failure and a fixed timeout that sometimes expired before the image was ready.

**Resolution:** Restructured `generate_image()` into submit → poll loop → download with a 2-attempt outer retry. Poll interval: 5 seconds × 18 iterations = 90 seconds max per attempt.

---

### Challenge 6 — Duplicate Posts Across Runs

**Problem:** Running Task 5 multiple times (e.g., during testing) accumulated duplicate posts in the database. The `save_to_db()` function used a plain `INSERT` with no conflict check, so each run added new rows for the same categories. The DB trim kept the 5 most recent rows globally — meaning after two runs of 3 categories, the display could show 3 posts for "AI Infrastructure & Tools" and only 1 each for the other two. This broke the requirement of showing at least 3 different categories.

**Resolution:** Three-layer deduplication:
1. **`save_to_db()`** — `DELETE FROM generated_posts WHERE category = ?` before every `INSERT`, ensuring at most one post per category exists at any time
2. **DB trim** — changed from "latest 5 rows globally" to `DELETE WHERE id NOT IN (SELECT MAX(id) ... GROUP BY category)`, keeping exactly the latest post per category
3. **Display query in `app.py`** — `SELECT MAX(id) ... GROUP BY category` ensures the UI always shows one post per category, even if stale duplicates somehow exist

**Result:** The database now contains exactly 3 rows (one per target category), and the display always shows uniquely-categorised, non-duplicate content.

---

## 3. Workflow and Prompt Optimization Progress

### 3.1 Task 2 — Single Score → Two-Dimension Scoring

| | Before | After |
|--|--------|-------|
| **Scoring** | Single relevance score (1–10) | Two independent scores: AI Significance + Retail Value |
| **Selection** | Score > fixed threshold | Both scores ≥ 3 (mandatory); ALL passing sent to Task 3 |
| **Explainability** | One opaque number | Two labelled scores with written reasons |

**Key prompt addition:**
> *"Score each dimension independently. Do not let one score influence the other. An article about a major AI breakthrough (ai_score=9) may still have no retail relevance (retail_score=2) — score it that way."*

**Why it improved quality:** Separating the two dimensions prevents a high AI score from masking zero retail relevance. The mandatory minimum eliminates technically impressive articles that a retail executive cannot act on. The scoring is now explainable and auditable.

---

### 3.2 Task 3 — Classification + Diversity Re-selection

| | Before | After |
|--|--------|-------|
| **Input pool** | Top 20% from Task 2 (3–8 articles) | ALL articles passing mandatory minimums |
| **Selection** | None — classify and stop | Phase 1: best per category → Phase 2: fill by score |
| **Diversity guarantee** | None | ≥ 3 categories guaranteed |

**Why it improved quality:** Generated posts now consistently span at least three different retail AI topics (e.g., Customer Experience, Supply Chain, AI Infrastructure), giving the audience varied content instead of three posts about the same model release.

---

### 3.3 Task 4 — Generic Persona → Structured KOL Profiles

| | Before | After |
|--|--------|-------|
| **Persona** | "A seasoned AI thought leader" | Specific KOL with 9-field profile |
| **Profile fields** | None | hook_style, structure, tone, credibility_signals, engagement_tactics, signature_phrases, topic_focus, audience_assumption, retail_applicability |
| **Synthesis** | None | Cross-KOL "Retail Executive Style Guide" with post template |

**Key prompt addition:**
> *"Be specific — include real examples where possible. Respond with ONLY a valid JSON object using these exact 9 keys."*

**Why it improved quality:** Posts now exhibit authentic style variation. An Andrew Ng-style post uses structured educational breakdowns; a Kai-Fu Lee-style post opens with bold geopolitical framing. This differentiation makes the content feel human.

---

### 3.4 Task 5 — Free Text → Structured Output + KOL Rotation

| | Before | After |
|--|--------|-------|
| **Output format** | Free text, hashtags mixed in | Structured JSON: `{"post_text": "...", "hashtags": [...]}` |
| **Persona** | Same for every post | Rotating KOL per post (post 0→Andrew Ng, post 1→Andrej Karpathy, etc.) |
| **Writing rules** | None | Explicit prohibitions + length target + hook style requirement |

**Key writing rules added to system prompt:**
- Never start with "Excited to share…" or "I'm thrilled…"
- Never use "game-changer", "revolutionary", "leverage", "in today's fast-paced world"
- Length: 150–250 words (optimal for LinkedIn mobile)
- End with a thought-provoking question that invites genuine engagement
- Connect AI news to a **specific** retail pain point within the first 3 lines

**Why it improved quality:** Posts are shorter, more distinctive, and more suitable for LinkedIn's mobile-first format. Separated hashtags enable the UI to render them as chips and the copy block to assemble them correctly. The prohibited phrase list specifically targets the most common AI-generated clichés.

---

## 4. Lessons Learned

| # | Lesson |
|---|--------|
| 1 | **Test API access before designing architecture.** Geographic restrictions are a real constraint. Always verify provider accessibility from the deployment environment before committing to an API. |
| 2 | **Never trust LLM JSON output blindly.** Even well-prompted models produce malformed JSON. Multi-strategy parsing with graceful fallbacks is essential. |
| 3 | **Score diversity matters as much as score magnitude.** Optimising purely for highest combined score produces a homogeneous output. A diversity constraint dramatically improved content variety with minimal added complexity. |
| 4 | **Cache expensive operations explicitly.** KOL style analysis (5 LLM calls, ~5,000 tokens each) runs once and is reused indefinitely. Making the cache visible to the user (the "Force Re-analyze" button) builds trust and avoids confusion. |
| 5 | **Separation of concerns reduces debugging time.** When Task 2 scoring was broken (all scores = 0), the issue was isolated to one file without touching the rest of the pipeline. |
| 6 | **Async APIs require polling discipline.** DashScope's image API is genuinely asynchronous. Careful retry logic with clear timeout messaging prevents silent hangs. |
| 7 | **Idempotency must be designed in from the start.** Any pipeline step that writes to a database needs an upsert or delete-before-insert strategy. Plain `INSERT` accumulates duplicates silently across test runs — only visible when the UI displays unexpected repeated content. |

---

## 5. Future Opportunities for Improvement

### 5.1 Content Quality

- **Engagement feedback loop:** Track which posts receive high LinkedIn engagement (likes, comments) and use this signal to refine generation prompts — a lightweight RLHF approach.
- **Multi-article synthesis:** Synthesise 2–3 related articles into a single post for more original, nuanced perspectives rather than summarising one source.
- **LLM-as-judge evaluation:** After generation, pass each post through a second LLM call that scores it on retail relevance, KOL authenticity, and engagement potential (1–10). Only posts above threshold advance.

### 5.2 Data Sourcing

- **Chinese-language AI sources:** Add 机器之心 and 量子位 RSS feeds to improve coverage of Chinese AI lab developments.
- **Social signal enrichment:** Integrate Twitter/X data to surface articles already generating discussion, boosting their recency-weighted scores.
- **Full article scraping:** Currently the pipeline uses only summaries and snippets. Fetching full article text would significantly improve classification accuracy and generation quality.

### 5.3 Automation & Operations

- **Cloud deployment:** Host on Alibaba Cloud ECS or Hugging Face Spaces so the scheduler runs 24/7 without requiring a local machine.
- **Direct LinkedIn publishing:** Integrate the LinkedIn API to publish approved posts directly, removing the manual copy-paste step.
- **WeChat / Slack notifications:** Push generated posts to a team channel for one-click approval before publication.
- **Content calendar:** Generate a full week of posts in one run, spread across categories and days.

### 5.4 Evaluation Framework

- **Category coverage dashboard:** Track which of the 5 retail AI categories has been covered in the past 7 days and bias article selection toward under-represented ones.
- **Prompt versioning:** Tag each generated post with the prompt version used, enabling controlled A/B comparison of prompt changes on output quality.
