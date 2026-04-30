# 🛍️ AI Retail Content Monitoring & Generation Workflow

An automated pipeline that monitors AI news, scores articles for retail relevance, classifies them into five retail AI categories, researches thought-leader writing styles, and generates ready-to-publish LinkedIn posts — complete with AI-generated images.

---

## ✅ Quick Start — View Pre-Generated Results (No API Key Required)

The repository includes a pre-populated database and generated posts so you can explore the full output immediately.

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/ai-retail-workflow.git
cd ai-retail-workflow

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the app
streamlit run app.py
```

Open **http://localhost:8501** in your browser.  
All tabs display pre-generated data — **no API key is needed to browse results**.

> The "Score / Classify / Generate" action buttons require API keys (see below).  
> Tabs 1–6 fully render existing articles, posts, images, and KOL profiles without any key.

---

## 🗂️ Project Structure

```
.
├── app.py                    # Streamlit UI (6 tabs)
├── config.py                 # All constants, model names, thresholds
├── workflow.py               # One-click full pipeline runner
├── scheduler.py              # APScheduler daily auto-run (Beijing 08:00)
│
├── task1_monitor.py          # RSS feed monitoring & filtering
├── task2_router.py           # Two-dimension relevance scoring
├── task3_classifier.py       # 5-way retail category classification
├── task4_kol_research.py     # KOL communication style analysis
├── task5_content_gen.py      # LinkedIn post + image generation
│
├── prompts/
│   ├── routing_prompt.py     # Task 2 scoring rubric prompts
│   ├── classification_prompt.py  # Task 3 classification prompts
│   └── generation_prompt.py  # Task 5 post generation + DALL-E prompts
│
├── data/
│   └── articles.db           # SQLite database (pre-populated)
│
├── output/
│   ├── posts/                # Generated LinkedIn post .txt files
│   ├── images/               # Generated images (.png) or prompt fallbacks (.txt)
│   └── kol_style_guide.json  # Cached KOL style analysis
│
├── requirements.txt
├── .env.example              # API key template
└── README.md
```

---

## 🔄 Workflow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Daily Auto-Run (08:00 CST)           │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
  │ Task 1   │──▶│ Task 2   │──▶│ Task 3   │──▶│ Task 4   │──▶│ Task 5   │
  │ Monitor  │   │ Route    │   │ Classify │   │ KOL      │   │ Generate │
  │          │   │          │   │          │   │ Research │   │          │
  │ 8 RSS    │   │ AI ×0.7  │   │ 5 retail │   │ 5 KOL    │   │ LinkedIn │
  │ sources  │   │ +        │   │ AI cats  │   │ styles   │   │ posts +  │
  │ Top 10   │   │ Retail   │   │ Diversity│   │ (cached) │   │ images   │
  │ articles │   │ ×0.3     │   │ ≥3 cats  │   │          │   │          │
  └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
                                                                     │
                                                          ┌──────────▼──────────┐
                                                          │  Email Notification  │
                                                          │  + History (30 days) │
                                                          └─────────────────────┘
```

### Five Tasks Explained

| Task | What it does |
|------|-------------|
| **Task 1 — Monitor** | Fetches latest articles from 8 AI news RSS feeds; applies AI keyword filter; keeps top 10 by recency |
| **Task 2 — Route** | Scores every article on two independent dimensions: AI Significance (×0.7) and Retail Value (×0.3); mandatory minimum ≥3 on both; all passing articles forwarded to Task 3 |
| **Task 3 — Classify** | LLM classifies each candidate into one of 5 retail AI categories; diversity-aware re-selection guarantees ≥3 distinct categories in the final set |
| **Task 4 — KOL Research** | Analyses the LinkedIn communication style of 5 AI thought leaders; cached after first run — no repeat API calls |
| **Task 5 — Generate** | Picks the best article per target category; generates a KOL-style LinkedIn post (rotating KOL per post); generates an image via 通义万相 (Alibaba DashScope); saves to DB |

---

## 🖥️ App Tabs

| Tab | Description |
|-----|-------------|
| 📡 Task 1: Monitor | View fetched articles; trigger a fresh fetch |
| 🎯 Task 2: Route | View two-dimension scores; re-score articles |
| 🏷️ Task 3: Classify | View category distribution (pie chart); re-classify |
| 👤 Task 4: KOL Research | KOL profile cards with avatars + LinkedIn links; Retail Style Synthesis |
| ✍️ Task 5: Generate | Generated posts with hashtag chips + copy block + image; latest 5 posts |
| 📚 History | Browse all posts with category/keyword filter |

---

## ⚙️ Full Setup (Run the Pipeline Yourself)

### 1. API Keys

You need two API keys:

| Key | Service | Get it at |
|-----|---------|-----------|
| `OPENROUTER_API_KEY` | LLM routing (DeepSeek models) | [openrouter.ai](https://openrouter.ai) — free tier available |
| `IMAGE_API_KEY` | 通义万相 image generation | [dashscope.aliyun.com](https://dashscope.aliyun.com) — free tier available |

### 2. Create `.env`

Copy the example and fill in your keys:

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

In the app sidebar, click **▶▶ Run Full Workflow** — or run each task tab in order (1 → 5).

To run headlessly:

```bash
python workflow.py
```

---

## 🤖 Models Used

| Task | Model | Provider |
|------|-------|----------|
| Scoring (T2) | `deepseek/deepseek-chat` | OpenRouter |
| Classification (T3) | `deepseek/deepseek-chat` | OpenRouter |
| KOL Analysis (T4) | `deepseek/deepseek-chat` | OpenRouter |
| Post Generation (T5) | `deepseek/deepseek-chat` | OpenRouter |
| Image Generation (T5) | `wanx2.1-t2i-turbo` | Alibaba DashScope |

All text models are routed through [OpenRouter](https://openrouter.ai), which provides a unified API for multiple LLM providers.

---

## 📋 Requirements

```
streamlit
openai
requests
feedparser
python-dotenv
APScheduler>=3.10.0
pytz>=2023.3
pandas
matplotlib
```

Install all:
```bash
pip install -r requirements.txt
```

---

## 📅 Scheduler

The pipeline runs automatically every day at **08:00 Beijing time (CST)** when the app is running. Configure in `.env`:

```
SCHEDULE_HOUR=8
SCHEDULE_MINUTE=0
```

Optionally configure email notifications:

```
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECEIVER=recipient@example.com
```

---

## 📁 Pre-Generated Output

The repository includes sample output so results are visible immediately:

- `data/articles.db` — SQLite DB with scored, classified articles and generated posts
- `output/kol_style_guide.json` — KOL style analysis for all 5 thought leaders
- `output/posts/` — Generated LinkedIn post text files
- `output/images/` — Generated images or image prompt `.txt` fallbacks
