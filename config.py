import os
from dotenv import load_dotenv

load_dotenv()

# ── OpenRouter API ─────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/ai-news-workflow",
    "X-Title": "AI Retail News Workflow",
}

# ── Paths ──────────────────────────────────────────────────────────────────────
DB_PATH              = "data/articles.db"
OUTPUT_POSTS_DIR     = "output/posts"
OUTPUT_IMAGES_DIR    = "output/images"
KOL_STYLE_GUIDE_PATH = "output/kol_style_guide.json"

# ── Per-task model assignment (all via OpenRouter) ─────────────────────────────
ROUTING_MODEL        = "deepseek/deepseek-chat"   # Task 2: structured JSON scoring
CLASSIFICATION_MODEL = "deepseek/deepseek-chat"   # Task 3: 5-way classification
KOL_MODEL            = "deepseek/deepseek-chat"   # Task 4: deep KOL style analysis
GENERATION_MODEL     = "deepseek/deepseek-chat"   # Task 5: LinkedIn post generation
DALLE_MODEL          = "openai/dall-e-3"           # Task 5: legacy (kept for reference)
DALLE_SIZE           = "1792x1024"

# ── Task 5: Image generation (通义万相 / Tongyi Wanxiang via Alibaba DashScope) ─
IMAGE_API_KEY  = os.getenv("IMAGE_API_KEY", "")
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")
IMAGE_MODEL    = os.getenv("IMAGE_MODEL",    "wanx2.1-t2i-turbo")
IMAGE_SIZE     = "1280*720"   # 16:9 ratio, DashScope uses '*' separator

# ── Task 1: News monitoring ────────────────────────────────────────────────────
GLOBAL_ARTICLE_LIMIT = 10   # max articles kept per run (global, across all sources)

# AI keyword filter — drops non-AI content from broad sources (HBR, a16z, etc.)
AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "llm", "large language model", "gpt", "generative", "neural network",
    "automation", "algorithm", "chatbot", "agent", "foundation model",
    "computer vision", "natural language", "reinforcement learning",
]

# ── Task 2: Two-dimension scoring ──────────────────────────────────────────────
AI_WEIGHT          = 0.7    # weight for AI significance dimension
RETAIL_WEIGHT      = 0.3    # weight for retail relevance dimension
AI_SCORE_MIN       = 3      # mandatory minimum — article rejected if AI score < this
RETAIL_SCORE_MIN   = 3      # mandatory minimum — article rejected if retail score < this
TOP_N_PERCENT      = 0.20   # select top 20% of articles that pass mandatory minimums
TOP_N_MIN          = 3      # floor: always select at least this many
TOP_N_MAX          = 8      # ceiling: never select more than this many

# ── Task 3: Diversity selection ────────────────────────────────────────────────
MIN_DIVERSITY_CATEGORIES = 3   # guaranteed minimum distinct categories after Task 3

# ── Task 5: Article selection ──────────────────────────────────────────────────
RELEVANCE_WEIGHT   = 0.8    # weight of combined_score in final selection score
RECENCY_WEIGHT     = 0.2    # weight of recency bonus in final selection score

# ── Scheduler ─────────────────────────────────────────────────────────────────
SCHEDULE_HOUR      = int(os.getenv("SCHEDULE_HOUR", "8"))    # default 08:00 Beijing
SCHEDULE_MINUTE    = int(os.getenv("SCHEDULE_MINUTE", "0"))
SCHEDULE_TIMEZONE  = "Asia/Shanghai"

# ── Email notification ─────────────────────────────────────────────────────────
EMAIL_SMTP_HOST    = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
EMAIL_SMTP_PORT    = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_SENDER       = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD     = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECEIVER     = os.getenv("EMAIL_RECEIVER", "")

# ── History ────────────────────────────────────────────────────────────────────
HISTORY_RETENTION_DAYS = 30   # generated posts older than this are auto-deleted

# RSS Sources — Task 1
RSS_SOURCES = [
    {"name": "Google AI Blog",     "url": "https://blog.google/technology/ai/rss/"},
    {"name": "OpenAI Blog",        "url": "https://openai.com/blog/rss.xml"},
    {"name": "a16z",               "url": "https://a16z.com/feed/"},
    {"name": "MIT Tech Review AI", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed"},
    {"name": "HBR",                "url": "https://feeds.hbr.org/harvardbusiness"},
    {"name": "McKinsey AI",        "url": "https://www.mckinsey.com/capabilities/quantumblack/rss"},
    {"name": "DeepMind",           "url": "https://deepmind.google/blog/rss.xml"},
    {"name": "Microsoft AI",       "url": "https://blogs.microsoft.com/ai/feed/"},
]

# Task 3 classification categories
CATEGORIES = [
    "Customer Experience & Personalization",
    "Supply Chain & Operations",
    "Pricing & Revenue Management",
    "AI Infrastructure & Tools",
    "Governance, Ethics & Regulation",
]

# Task 4 KOLs to analyze
KOLS = [
    "Andrew Ng",
    "Andrej Karpathy",
    "Sam Altman",       # replaces Jensen Huang
    "Kai-Fu Lee",
    "Mustafa Suleyman",
]

# Task 5: which categories to generate LinkedIn posts for
TARGET_CATEGORIES = [
    "Customer Experience & Personalization",
    "Supply Chain & Operations",
    "AI Infrastructure & Tools",
]

# HTTP request headers to avoid 403s
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AINewsBot/1.0; +https://github.com/ai-news-workflow)"
}
