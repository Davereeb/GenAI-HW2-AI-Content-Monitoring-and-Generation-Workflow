"""
Task 2: Two-Dimension Relevance Router
Scores articles on AI significance and retail value independently via OpenRouter.
Selection logic:
  - Both scores must be >= mandatory minimum (AI_SCORE_MIN, RETAIL_SCORE_MIN)
  - combined_score = ai_score * AI_WEIGHT + retail_score * RETAIL_WEIGHT
  - Top N% of passing articles are marked relevant (floor: TOP_N_MIN, ceiling: TOP_N_MAX)
"""

import json
import math
import re
import sqlite3
import time

from openai import OpenAI

from config import (
    AI_SCORE_MIN,
    AI_WEIGHT,
    DB_PATH,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_HEADERS,
    RETAIL_SCORE_MIN,
    RETAIL_WEIGHT,
    ROUTING_MODEL,
    TOP_N_MAX,
    TOP_N_MIN,
    TOP_N_PERCENT,
)
from prompts.routing_prompt import ROUTING_SYSTEM, ROUTING_USER


client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
    default_headers=OPENROUTER_HEADERS,
)


def clean_json(text: str) -> str:
    return re.sub(r"```(?:json)?\n?|\n?```", "", text).strip()


def reset_scores(conn: sqlite3.Connection) -> int:
    """Clear all scores so articles can be re-scored from scratch."""
    cur = conn.execute(
        """UPDATE articles SET
           ai_score=NULL, retail_score=NULL, combined_score=NULL,
           ai_reason=NULL, retail_reason=NULL,
           is_relevant=NULL, category=NULL"""
    )
    conn.commit()
    return cur.rowcount


def score_article(article: dict) -> dict | None:
    """Call the LLM to score one article. Returns dict with scores or None on error."""
    user_msg = ROUTING_USER.format(
        title=article["title"],
        source=article["source"],
        summary=article["summary"] or "(no summary available)",
    )
    try:
        response = client.chat.completions.create(
            model=ROUTING_MODEL,
            max_tokens=200,
            messages=[
                {"role": "system", "content": ROUTING_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
        )
        raw  = response.choices[0].message.content
        data = json.loads(clean_json(raw))
        ai_score     = max(1, min(10, int(data.get("ai_score", 5))))
        retail_score = max(1, min(10, int(data.get("retail_score", 5))))
        return {
            "ai_score":     ai_score,
            "retail_score": retail_score,
            "ai_reason":    data.get("ai_reason", ""),
            "retail_reason":data.get("retail_reason", ""),
            "combined":     round(ai_score * AI_WEIGHT + retail_score * RETAIL_WEIGHT, 2),
        }
    except Exception as e:
        print(f"    [WARN] Scoring failed for '{article['title'][:50]}': {e}")
        return None


def run(force_rescore: bool = False) -> str:
    """Entry point for workflow.py / app.py.
    force_rescore=True resets all scores before running (used by the UI reset button).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if force_rescore:
        n = reset_scores(conn)
        print(f"  [RESET] Cleared scores for {n} articles")

    rows = conn.execute(
        "SELECT id, title, source, summary FROM articles WHERE ai_score IS NULL OR ai_score < 0"
    ).fetchall()

    if not rows:
        conn.close()
        return "No unscored articles — run Task 1 first, or use Reset & Re-score"

    print(f"\n[Task 2] Scoring {len(rows)} articles with {ROUTING_MODEL}...")

    scored_articles: list[dict] = []
    failed = 0

    for row in rows:
        article = dict(row)
        result  = score_article(article)

        if result is None:
            # Use -1 as sentinel so these articles can be retried on next run
            conn.execute(
                """UPDATE articles SET ai_score=-1, retail_score=-1,
                   combined_score=-1, is_relevant=0 WHERE id=?""",
                (article["id"],),
            )
            failed += 1
        else:
            conn.execute(
                """UPDATE articles SET
                   ai_score=?, retail_score=?, combined_score=?,
                   ai_reason=?, retail_reason=?, is_relevant=0
                   WHERE id=?""",
                (
                    result["ai_score"], result["retail_score"], result["combined"],
                    result["ai_reason"], result["retail_reason"],
                    article["id"],
                ),
            )
            scored_articles.append({
                "id":            article["id"],
                "title":         article["title"],
                "ai_score":      result["ai_score"],
                "retail_score":  result["retail_score"],
                "combined":      result["combined"],
                "ai_reason":     result["ai_reason"],
                "retail_reason": result["retail_reason"],
            })
            print(f"  [AI:{result['ai_score']:2d} RT:{result['retail_score']:2d} "
                  f"=> {result['combined']:.1f}] {article['title'][:55]}")
            print(f"           AI: {result['ai_reason']}")
            print(f"           Retail: {result['retail_reason']}")

        conn.commit()
        time.sleep(0.3)

    # ── Apply mandatory minimums — pass ALL qualifying articles to Task 3 ───────
    # (Top-N% filtering is removed here; Task 3 does diversity-aware final selection)
    passing = [
        a for a in scored_articles
        if a["ai_score"] >= AI_SCORE_MIN and a["retail_score"] >= RETAIL_SCORE_MIN
    ]
    eliminated = len(scored_articles) - len(passing)
    if eliminated:
        print(f"\n  [FILTER] {eliminated} articles eliminated "
              f"(ai_score < {AI_SCORE_MIN} OR retail_score < {RETAIL_SCORE_MIN})")

    # Mark ALL passing articles as relevant candidates for Task 3 classification
    selected_ids = [a["id"] for a in passing]
    if selected_ids:
        placeholders = ",".join("?" * len(selected_ids))
        conn.execute(
            f"UPDATE articles SET is_relevant=1 WHERE id IN ({placeholders})",
            selected_ids,
        )
        conn.commit()

    print(f"\n  Summary: {len(scored_articles)} scored, "
          f"{len(passing)} passed mandatory minimums → all marked as candidates for Task 3")
    print(f"  (Diversity-aware final selection will run at end of Task 3)")

    for a in sorted(passing, key=lambda a: a["combined"], reverse=True):
        print(f"  [CANDIDATE] {a['combined']:.1f} — {a['title'][:60]}")

    conn.close()

    return (
        f"{len(scored_articles)} articles scored → "
        f"{len(passing)} passed mandatory minimums → all marked as Task 3 candidates"
        + (f" ({failed} API errors)" if failed else "")
    )


if __name__ == "__main__":
    result = run()
    print(f"\n[Task 2 Complete] {result}")
