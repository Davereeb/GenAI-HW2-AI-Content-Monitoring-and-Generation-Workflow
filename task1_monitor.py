"""
Task 1: Daily AI News Monitoring Agent (Strategy C)
Pipeline per run:
  1. Fetch all entries from every RSS source
  2. Keyword pre-filter — keep only entries that mention AI (free, no LLM)
  3. Sort globally by publication date (most recent first)
  4. Take the top GLOBAL_ARTICLE_LIMIT entries across all sources combined
  5. Store new entries in SQLite (INSERT OR IGNORE deduplicates)
"""

import calendar
import sqlite3
import time
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

from config import (
    AI_KEYWORDS,
    DB_PATH,
    GLOBAL_ARTICLE_LIMIT,
    REQUEST_HEADERS,
    RSS_SOURCES,
)


# ── Database setup ────────────────────────────────────────────────────────────

def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            url              TEXT UNIQUE NOT NULL,
            title            TEXT NOT NULL,
            source           TEXT NOT NULL,
            published        TEXT,
            summary          TEXT,
            snippet          TEXT,
            fetched_at       TEXT NOT NULL,
            ai_score         REAL DEFAULT NULL,
            retail_score     REAL DEFAULT NULL,
            combined_score   REAL DEFAULT NULL,
            ai_reason        TEXT DEFAULT NULL,
            retail_reason    TEXT DEFAULT NULL,
            is_relevant      INTEGER DEFAULT NULL,
            category         TEXT DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS kol_styles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kol_name    TEXT UNIQUE NOT NULL,
            style_json  TEXT NOT NULL,
            analyzed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS generated_posts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            category         TEXT NOT NULL,
            article_title    TEXT,
            article_source   TEXT,
            article_url      TEXT,
            post_text        TEXT NOT NULL,
            hashtags         TEXT,
            selection_reason TEXT,
            image_path       TEXT,
            generated_at     TEXT NOT NULL
        );
    """)
    # Add new columns to existing articles tables (safe if already present)
    for col, typedef in [
        ("ai_score",       "REAL DEFAULT NULL"),
        ("retail_score",   "REAL DEFAULT NULL"),
        ("combined_score", "REAL DEFAULT NULL"),
        ("ai_reason",      "TEXT DEFAULT NULL"),
        ("retail_reason",  "TEXT DEFAULT NULL"),
    ]:
        try:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {typedef}")
        except Exception:
            pass  # column already exists
    conn.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_snippet(url: str, max_chars: int = 500) -> str:
    """Fetch the first max_chars of body text from a URL. Returns '' on failure."""
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=5)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return " ".join(soup.get_text(separator=" ").split())[:max_chars]
    except Exception:
        return ""


def entry_datetime(entry) -> datetime:
    """Parse publication date to UTC datetime. Falls back to epoch so undated entries sink."""
    pt = entry.get("published_parsed") or entry.get("updated_parsed")
    if pt:
        return datetime.utcfromtimestamp(calendar.timegm(pt)).replace(tzinfo=timezone.utc)
    for field in ("published", "updated", "created"):
        raw = entry.get(field, "")
        if not raw:
            continue
        for fmt in (
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
        ):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return datetime.fromtimestamp(0, tz=timezone.utc)


def passes_ai_filter(entry) -> bool:
    """Return True if the entry title or summary contains at least one AI keyword."""
    text = (
        (entry.get("title") or "") + " " + (entry.get("summary") or "")
    ).lower()
    return any(kw in text for kw in AI_KEYWORDS)


# ── Core pipeline ─────────────────────────────────────────────────────────────

def collect_entries_from_source(source: dict) -> list[dict]:
    """Fetch all entries from one RSS source. Returns list of enriched entry dicts."""
    name = source["name"]
    url  = source["url"]
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        print(f"  [WARN] {name}: feedparser error — {e}")
        return []

    if not feed.entries:
        print(f"  [WARN] {name}: no entries returned")
        return []

    results = []
    for entry in feed.entries:
        link = entry.get("link", "")
        if not link:
            continue
        results.append({
            "_source_name": name,
            "_entry":       entry,
            "_dt":          entry_datetime(entry),
            "_link":        link,
        })

    print(f"  {name}: {len(results)} entries fetched")
    return results


def run() -> str:
    """Entry point for workflow.py orchestrator."""
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # ── Step 1: collect all entries from all sources ──────────────────────────
    print(f"\n[Task 1] Fetching from {len(RSS_SOURCES)} RSS sources...")
    all_entries = []
    for source in RSS_SOURCES:
        all_entries.extend(collect_entries_from_source(source))

    print(f"\n  Total entries collected : {len(all_entries)}")

    # ── Step 2: keyword pre-filter (AI relevance, free) ──────────────────────
    filtered = [e for e in all_entries if passes_ai_filter(e["_entry"])]

    print(f"  After AI keyword filter : {len(filtered)}  "
          f"({len(all_entries) - len(filtered)} non-AI entries dropped)")

    # ── Step 3: sort globally by recency (most recent first) ──────────────────
    filtered.sort(key=lambda e: e["_dt"], reverse=True)

    # ── Step 4: take global top N ─────────────────────────────────────────────
    selected = filtered[:GLOBAL_ARTICLE_LIMIT]
    print(f"  After global Top-{GLOBAL_ARTICLE_LIMIT} cut  : {len(selected)} articles → entering DB\n")

    # ── Step 5: store in SQLite ───────────────────────────────────────────────
    fetched_at = datetime.now(timezone.utc).isoformat()
    new_count  = 0

    for e in selected:
        entry     = e["_entry"]
        name      = e["_source_name"]
        link      = e["_link"]
        title     = entry.get("title", "No title")
        summary   = (entry.get("summary") or entry.get("description") or "")[:500]
        published = (
            entry.get("published") or entry.get("updated") or fetched_at
        )
        snippet = fetch_snippet(link)

        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO articles
                   (url, title, source, published, summary, snippet, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (link, title, name, published, summary, snippet, fetched_at),
            )
            if cursor.rowcount:
                new_count += 1
                print(f"  [NEW] {name}: {title[:65]}")
        except sqlite3.Error as ex:
            print(f"  [ERROR] DB insert failed for {link}: {ex}")

        time.sleep(0.2)

    conn.commit()
    conn.close()

    skipped = len(selected) - new_count
    return (
        f"{len(all_entries)} entries fetched → "
        f"{len(filtered)} passed AI filter → "
        f"{len(selected)} selected (Top-{GLOBAL_ARTICLE_LIMIT}) → "
        f"{new_count} new, {skipped} duplicates"
    )


if __name__ == "__main__":
    result = run()
    print(f"\n[Task 1 Complete] {result}")
