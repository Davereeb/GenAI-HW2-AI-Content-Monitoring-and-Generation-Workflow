# 🛍️ AI Retail Content Monitoring & Generation Workflow

> An end-to-end, agentic pipeline that transforms raw AI news into polished, ready-to-publish LinkedIn thought leadership content for retail industry executives — fully automated, daily, with self-correcting quality control.

---

## ✅ Quick Start — View Pre-Generated Results (No API Key Required)

The repository includes a pre-populated database, generated posts, and AI images so you can explore the full output immediately.

```bash
# 1. Clone the repository
git clone https://github.com/Davereeb/GenAI-HW2-AI-Content-Monitoring-and-Generation-Workflow.git
cd GenAI-HW2-AI-Content-Monitoring-and-Generation-Workflow

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the app
streamlit run app.py
```

Open **http://localhost:8501** in your browser.  
All 6 tabs display pre-generated data — **no API key is needed to browse results**.

> The action buttons (Score / Classify / Generate) require API keys — see [Full Setup](#️-full-setup-run-the-pipeline-yourself).  
> All tabs fully render existing articles, posts, images, and KOL profiles without any key.

---

## 🏗️ Criterion 1 — Soundness of Workflow and Agent Design

### Adaptive Five-Task Agent Pipeline

The system is not a simple linear pipeline — it is an **adaptive agent** that monitors its own intermediate output and self-corrects before proceeding.

```
┌─────────────────────────────────────────────────────────────────┐
│              Daily Auto-Run — 08:00 Beijing CST                 │
│              (APScheduler BackgroundScheduler)                   │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ Task 1   │─▶│ Task 2   │─▶│ Task 3   │─▶│ Task 4   │─▶│ Task 5   │
  │ Monitor  │  │ Route    │  │ Classify │  │   KOL    │  │ Generate │
  │          │  │          │  │          │  │ Research │  │          │
  │ 8 RSS    │  │ AI ×0.7  │  │ 5 retail │  │ 5 KOLs   │  │ Post +   │
  │ sources  │  │ Retail   │  │ AI cats  │  │ (cached) │  │ Image +  │
  │ Top 10   │  │ ×0.3 +   │  │ Diversity│  │          │  │ LLM Judge│
  │ articles │  │ Recency  │  │ ≥3 cats  │  │          │  │          │
  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
                                    │
                    ┌───────────────▼─────────────────────┐
                    │  Diversity Check (≥3 categories?)    │
                    │  NO → Relax threshold → Retry T2+T3 │  ← Feedback Loop
                    │  YES → Continue to Task 4            │
                    └──────────────────────────────────────┘
                                                                │
                                            ┌───────────────────▼──────────────┐
                                            │  SQLite DB · Email · 30-day Hist │
                                            └──────────────────────────────────┘
```

### Diversity Feedback Loop (Adaptive Agent Behaviour)

After Task 3 completes, the orchestrator (`workflow.py`) queries the database:

- **If ≥ 3 categories selected** → pipeline continues to Task 4 normally
- **If < 3 categories selected** → automatically relaxes the mandatory score minimum from 3 → 2 and re-runs Tasks 2+3 once

This self-correction loop means the pipeline **never silently produces under-diverse output**. It detects the problem and fixes it without human intervention — a core property of agent design.

### Design Principles

| Principle | Implementation |
|-----------|---------------|
| **Separation of concerns** | Each task is an independent Python module with a `run()` entry point — testable, replaceable, and runnable in isolation |
| **Persistence** | Every intermediate result (scores, categories, posts, quality evaluations) is stored in SQLite — any step can be re-run without re-executing earlier ones |
| **Graceful degradation** | Every API call has retry logic and a fallback — if image generation times out, a prompt `.txt` is saved; if JSON parsing fails, three recovery strategies run before falling back to raw text |
| **Single config source** | All thresholds, weights, model names, and schedule parameters live in `config.py` — changing the AI weight requires editing one line |
| **Idempotency** | Every DB write uses DELETE-then-INSERT, ensuring re-runs don't accumulate duplicates |

### Project Structure

```
.
├── app.py                       # Streamlit UI (6 tabs)
├── config.py                    # All constants, model names, thresholds
├── workflow.py                  # Orchestrator with diversity feedback loop
├── scheduler.py                 # APScheduler daily auto-run (Beijing 08:00)
│
├── task1_monitor.py             # RSS feed monitoring & AI keyword filtering
├── task2_router.py              # Two-dimension scoring + recency bonus
├── task3_classifier.py          # 5-way classification + diversity re-selection
├── task4_kol_research.py        # KOL communication style analysis (cached)
├── task5_content_gen.py         # Post generation + LLM judge + image generation
│
├── prompts/
│   ├── routing_prompt.py        # Task 2: two-dimension scoring rubric
│   ├── classification_prompt.py # Task 3: category + business impact prompts
│   └── generation_prompt.py     # Task 5: KOL-style post + image prompts
│
├── data/articles.db             # SQLite database (pre-populated)
├── output/posts/                # Generated LinkedIn post .txt files
├── output/images/               # Generated images (.png) or prompt fallbacks (.txt)
└── output/kol_style_guide.json  # Cached KOL style analysis
```

---

## 🎯 Criterion 2 — Effectiveness of Relevance Routing

### Two-Dimension Scoring with Recency Bonus

Task 2 scores every article on **two independent dimensions** to prevent a high AI score from masking zero retail relevance:

```
Combined Score = (AI Significance × 0.7) + (Retail Value × 0.3) + Recency Bonus
```

| Dimension | Weight | Rationale |
|-----------|--------|-----------|
| **AI Significance** | ×0.7 | Retail executives need to understand major AI shifts — this ensures only genuinely impactful AI news is selected |
| **Retail Value** | ×0.3 | Direct applicability to retail operations — prevents technically impressive but operationally irrelevant articles from passing |
| **Recency Bonus** | max +0.5 | Articles < 24 h: +0.5 · < 48 h: +0.3 · < 7 days: +0.1 — keeps content topical without distorting primary scoring |

### Scoring Rubric

| Score | AI Significance | Retail Value |
|-------|----------------|-------------|
| **9–10** | Breakthrough model / API release (GPT, Gemini, Llama…) | Direct retail use case (e-commerce, supply chain, pricing…) |
| **7–8** | Major capability update, agentic system, enterprise AI launch | Clear business application within 12 months |
| **5–6** | Incremental update, AI governance, dev tooling | Plausible retail angle, general enterprise AI |
| **3–4** | Niche academic paper, distant-timeline research | Indirect relevance |
| **1–2** | Non-AI content | No retail relevance |

### Selection Logic

- **Mandatory gate:** both scores must be **≥ 3** — an article scoring AI=9, Retail=1 is eliminated
- **All passing articles** are forwarded to Task 3 (no arbitrary top-N% cut)
- Task 3 does diversity-aware final selection, ensuring breadth is preserved
- Score distribution is visualised as a histogram in the UI for full transparency

---

## 🏷️ Criterion 3 — Quality and Business Value of Insight Classification

### Five Retail AI Categories

Task 3 classifies every candidate article into exactly one of five categories optimised for retail executive relevance:

| Category | Business Focus |
|----------|---------------|
| **Customer Experience & Personalization** | AI-driven recommendations, chatbots, loyalty, CX automation |
| **Supply Chain & Operations** | Demand forecasting, inventory optimisation, logistics AI |
| **Pricing & Revenue Management** | Dynamic pricing, promotions, revenue optimisation |
| **AI Infrastructure & Tools** | Foundation models, platforms, APIs — general AI capability news |
| **Governance, Ethics & Regulation** | AI policy, bias, compliance, data privacy |

### Business Impact Tagging

Every classified article also receives a **business impact tag** that makes the value proposition immediately actionable for a retail executive:

| Tag | Meaning |
|-----|---------|
| 💰 `cost_reduction` | Reduces operating costs, headcount, or waste |
| 📈 `revenue_growth` | Drives sales, conversion rate, or customer loyalty |
| 🛡️ `risk_mitigation` | Addresses compliance, fraud, supply chain risk, or data privacy |
| ⭐ `customer_satisfaction` | Improves CX, personalization, or service quality |

### Explainability

Each classification includes:
- **Confidence level** — High 🟢 / Medium 🟡 / Low 🔴
- **Reason** — one sentence explaining why the article belongs in this category
- **Business impact** — the primary value driver for retail executives

These four fields are all stored in the database and displayed in the Task 3 UI, making every classification fully auditable.

### Diversity Guarantee

The classification pipeline runs a **two-phase diversity-aware re-selection** after classifying all articles:

- **Phase 1** — take the highest-scoring article from each represented category (guarantees breadth)
- **Phase 2** — fill remaining slots up to 8 by combined score (preserves quality)
- **Hard constraint** — minimum 3 distinct categories enforced; feedback loop triggers retry if not met

---

## ✍️ Criterion 4 — Clarity, Relevance, and Professionalism of LinkedIn Content

### KOL-Style Rotating Posts

Each post is written in the authentic communication style of a real AI thought leader, rotated across posts:

| Post # | KOL Style | Characteristic |
|--------|-----------|----------------|
| 1 | **Andrew Ng** | Structured educational breakdown; framework-first thinking |
| 2 | **Andrej Karpathy** | Technical precision; first-principles reasoning |
| 3 | **Sam Altman** | Bold strategic framing; future-of-work perspective |
| 4 | **Kai-Fu Lee** | Geopolitical lens; China–West AI dynamics |
| 5 | **Mustafa Suleyman** | Ethics-conscious; responsible AI deployment |

Task 4 analyses each KOL's real LinkedIn and public writing across 9 structured dimensions (hook style, structure, tone, credibility signals, engagement tactics, signature phrases, topic focus, audience assumption, retail applicability) and synthesises them into a **Retail Executive Style Guide** injected into every generation prompt.

### Writing Quality Rules (Prompt Engineering)

Every generated post follows explicit constraints:

**Required:**
- Open with a concrete retail problem or surprising statistic — never a generic greeting
- Connect AI news to a **specific** retail pain point within the first 3 lines
- End with a thought-provoking question that invites genuine engagement
- 150–250 words (optimised for LinkedIn mobile reading)

**Prohibited:**
- ~~"Excited to share…"~~ / ~~"I'm thrilled to announce…"~~
- ~~"game-changer"~~ / ~~"revolutionary"~~ / ~~"leverage"~~ / ~~"in today's fast-paced world"~~

### LLM-as-Judge Quality Control (Two-Pass Generation)

After generating each post, a **second LLM call** evaluates it as a senior content editor:

| Dimension | What is scored |
|-----------|---------------|
| 🎣 **Hook Strength** | Does the opening immediately grab attention without clichés? |
| 🛍️ **Retail Specificity** | Is the retail pain point concrete and named — not generic AI hype? |
| 🧑 **KOL Authenticity** | Does the writing feel like a genuine thought leader? |
| 💬 **Engagement Potential** | Would a retail executive pause, reflect, and want to share? |

- Each dimension scored **1–10**
- If average **< 7.5** → the judge rewrites the weakest sections automatically
- If average **≥ 7.5** → original post is kept
- Quality scores are stored in the database and displayed as badges in the UI

### AI-Generated Images

Every post is paired with a contextually relevant image generated by **通义万相 (Tongyi Wanxiang)** via Alibaba DashScope — a photorealistic, LinkedIn-ready 16:9 image matching the post's retail category and topic. If image generation is unavailable, the exact prompt is saved as a `.txt` fallback for manual use.

---

## 📈 Criterion 5 — Depth of Reflection and Continuous Improvement

### Challenges Solved During Development

| # | Challenge | Root Cause | Resolution |
|---|-----------|-----------|------------|
| 1 | **Geographic API restrictions** | OpenAI/Anthropic endpoints blocked in mainland China (HTTP 403) | Switched to `deepseek/deepseek-chat` (OpenRouter) + 通义万相 (DashScope) |
| 2 | **Malformed JSON from LLM** | Unescaped newlines, trailing commas in structured outputs | Three-strategy extraction: direct parse → regex block → field-by-field regex |
| 3 | **Category diversity collapse** | Top-20% score cut always selected the same "AI Infrastructure" articles | Redesigned: Task 2 passes all candidates; Task 3 does diversity-aware two-phase re-selection |
| 4 | **KOL analysis failure (Jensen Huang)** | Keynote speaker with limited LinkedIn presence → LLM produced malformed JSON | Replaced with Sam Altman; added 2-attempt retry + robust `_parse_kol_json()` |
| 5 | **Async image API** | DashScope 通义万相 returns task_id, requires polling; initial fixed timeout expired | Restructured to submit → poll (5 s × 18 = 90 s max) → download, with 2-attempt outer retry |
| 6 | **Duplicate posts across test runs** | Plain `INSERT` with no conflict check accumulated stale rows | DELETE-before-INSERT per category + GROUP BY category display query |

### Design Evolution — Prompt Optimization

| Task | Before | After |
|------|--------|-------|
| **Task 2** | Single relevance score (1–10) | Two independent scores (AI + Retail) + recency bonus |
| **Task 3** | Category only | Category + confidence + reason + business impact |
| **Task 4** | Generic "AI thought leader" persona | 9-field structured KOL profile + synthesised style guide |
| **Task 5** | Free text, one-pass generation | Structured JSON + KOL rotation + LLM-as-judge self-correction |
| **Workflow** | Linear pipeline | Adaptive feedback loop — retries with relaxed thresholds on diversity failure |

### Key Lessons Learned

1. **Validate API access in the deployment region** before architecture decisions are finalised
2. **Never trust LLM JSON output blindly** — multi-strategy parsing with graceful fallbacks is essential
3. **Score diversity matters as much as score magnitude** — a diversity constraint dramatically improved content variety
4. **Cache expensive LLM operations explicitly** — KOL analysis (5 calls, ~5,000 tokens each) runs once, reused indefinitely
5. **Separation of concerns reduces debugging time** — a broken Task 2 was isolated and fixed without touching the rest of the pipeline
6. **Async APIs require polling discipline** — clear timeout messaging prevents silent hangs
7. **Idempotency must be designed in from the start** — plain `INSERT` accumulates duplicates silently across test runs
8. **LLM self-evaluation is practical** — a second LLM call as judge costs ~500 extra tokens but provides a measurable quality signal and automatic revision
9. **Agent design means adaptive behaviour** — a pipeline that monitors its own output and re-runs steps with adjusted parameters is more robust than one that always proceeds regardless

---

## 🖥️ App Interface

| Tab | What you see |
|-----|-------------|
| 📡 **Task 1: Monitor** | Fetched articles with sources and publish dates; trigger fresh fetch |
| 🎯 **Task 2: Route** | Two-dimension scores with colour-coded status; score distribution histogram; scoring rubric |
| 🏷️ **Task 3: Classify** | Category pie chart; per-article confidence badge, business impact tag, and classification reason |
| 👤 **Task 4: KOL Research** | Avatar cards with LinkedIn links; 9-field style profiles; Retail Style Synthesis guide |
| ✍️ **Task 5: Generate** | Posts with hashtag chips, copy block, AI image, quality badge (🟢/🟡/🔴 X.X/10), and 4-dimension score breakdown |
| 📚 **History** | All posts with category/keyword filter; 30-day retention |

---

## ⚙️ Full Setup (Run the Pipeline Yourself)

### 1. API Keys

| Key | Service | Where to get it |
|-----|---------|-----------------|
| `OPENROUTER_API_KEY` | LLM text models (DeepSeek via OpenRouter) | [openrouter.ai](https://openrouter.ai) — free tier available |
| `IMAGE_API_KEY` | 通义万相 image generation (Alibaba DashScope) | [dashscope.aliyun.com](https://dashscope.aliyun.com) — free tier available |

### 2. Configure `.env`

```bash
cp .env.example .env
```

Edit `.env`:

```
OPENROUTER_API_KEY=sk-or-v1-your-key-here
IMAGE_API_KEY=sk-your-dashscope-key-here
```

### 3. Install & Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

### 4. Run the Full Pipeline

Click **▶▶ Run Full Workflow** in the app sidebar, or run each tab in order (1 → 5).

To run headlessly (e.g. for scheduled execution):

```bash
python workflow.py
```

---

## 🤖 Models

| Task | Model | Provider |
|------|-------|----------|
| Relevance Scoring (T2) | `deepseek/deepseek-chat` | OpenRouter |
| Classification (T3) | `deepseek/deepseek-chat` | OpenRouter |
| KOL Analysis (T4) | `deepseek/deepseek-chat` | OpenRouter |
| Post Generation (T5) | `deepseek/deepseek-chat` | OpenRouter |
| LLM Judge (T5) | `deepseek/deepseek-chat` | OpenRouter |
| Image Generation (T5) | `wanx2.1-t2i-turbo` | Alibaba DashScope |

> All text models are routed through [OpenRouter](https://openrouter.ai) — a unified API gateway supporting 200+ LLM providers. DeepSeek was chosen because OpenAI, Anthropic, and Google endpoints return HTTP 403 from mainland China deployment environments.

---

## 📅 Scheduler

The full pipeline runs automatically every day at **08:00 Beijing time (CST)** via APScheduler. Configurable in `.env`:

```
SCHEDULE_HOUR=8
SCHEDULE_MINUTE=0
```

Optional email notification after each run:

```
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECEIVER=recipient@example.com
```
