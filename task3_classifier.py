"""
Task 3: Information Classifier
Classifies each relevant, unclassified article into one of 5 retail AI categories via OpenRouter.
"""

import json
import re
import sqlite3
import time
from collections import Counter

from openai import OpenAI

from config import (
    CATEGORIES,
    CLASSIFICATION_MODEL,
    DB_PATH,
    MIN_DIVERSITY_CATEGORIES,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_HEADERS,
    TOP_N_MAX,
)
from prompts.classification_prompt import CLASSIFICATION_SYSTEM, CLASSIFICATION_USER


client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
    default_headers=OPENROUTER_HEADERS,
)
DEFAULT_CATEGORY = "AI Infrastructure & Tools"


def clean_json(text: str) -> str:
    return re.sub(r"```(?:json)?\n?|\n?```", "", text).strip()


def classify_article(article: dict) -> tuple[str, str, str, str]:
    """Call the LLM to classify one article.
    Returns (category, confidence, reason, business_impact)."""
    user_msg = CLASSIFICATION_USER.format(
        title=article["title"],
        source=article["source"],
        summary=article["summary"] or "(no summary available)",
        combined_score=round(article.get("combined_score") or 0, 1),
    )
    try:
        response = client.chat.completions.create(
            model=CLASSIFICATION_MODEL,
            max_tokens=250,
            messages=[
                {"role": "system", "content": CLASSIFICATION_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
        )
        raw = response.choices[0].message.content
        data = json.loads(clean_json(raw))
        category       = data.get("category", DEFAULT_CATEGORY)
        confidence     = data.get("confidence", "medium")
        reason         = data.get("reason", "")
        business_impact = data.get("business_impact", "")

        # Validate — must exactly match one of the 5 allowed categories
        if category not in CATEGORIES:
            print(f"    [WARN] Unknown category '{category}' — defaulting to '{DEFAULT_CATEGORY}'")
            category = DEFAULT_CATEGORY

        valid_impacts = {"cost_reduction", "revenue_growth", "risk_mitigation", "customer_satisfaction"}
        if business_impact not in valid_impacts:
            business_impact = ""

        return category, confidence, reason, business_impact
    except Exception as e:
        print(f"    [WARN] Classification failed for '{article['title'][:50]}': {e}")
        return DEFAULT_CATEGORY, "low", "parse error — defaulted", ""


def apply_diversity_selection(conn: sqlite3.Connection) -> tuple[int, int]:
    """
    Diversity-aware final selection after all candidates are classified.

    Phase 1 (diversity quota): pick the highest-scoring article from each category
    that has at least one classified candidate — guarantees category breadth.

    Phase 2 (score fill): fill remaining slots up to TOP_N_MAX with the next
    highest global scorers not yet selected.

    Rewrites is_relevant=1 only for the final selected set.
    Returns (categories_covered, total_selected).
    """
    rows = conn.execute(
        """SELECT id, category, combined_score
           FROM articles
           WHERE is_relevant = 1 AND category IS NOT NULL
           ORDER BY combined_score DESC"""
    ).fetchall()

    selected_ids: list[int] = []
    seen_categories: set[str] = set()

    # Phase 1: best article per category
    for row in rows:
        cat = row["category"]
        if cat not in seen_categories:
            selected_ids.append(row["id"])
            seen_categories.add(cat)

    # Phase 2: fill up to TOP_N_MAX with remaining top scorers
    selected_set = set(selected_ids)
    for row in rows:
        if len(selected_ids) >= TOP_N_MAX:
            break
        if row["id"] not in selected_set:
            selected_ids.append(row["id"])
            selected_set.add(row["id"])

    # Reset all candidates, then mark only the diversity-selected set
    conn.execute("UPDATE articles SET is_relevant=0 WHERE is_relevant=1")
    if selected_ids:
        placeholders = ",".join("?" * len(selected_ids))
        conn.execute(
            f"UPDATE articles SET is_relevant=1 WHERE id IN ({placeholders})",
            selected_ids,
        )
    conn.commit()

    return len(seen_categories), len(selected_ids)


def run() -> str:
    """Entry point for workflow.py orchestrator."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """SELECT id, title, source, summary, combined_score
           FROM articles
           WHERE is_relevant = 1 AND category IS NULL"""
    ).fetchall()

    if not rows:
        conn.close()
        return "No unclassified relevant articles — nothing to do"

    print(f"\n[Task 3] Classifying {len(rows)} candidate articles...")

    counts: Counter = Counter()

    for row in rows:
        article = dict(row)
        category, confidence, reason, business_impact = classify_article(article)

        conn.execute(
            """UPDATE articles
               SET category=?, classification_confidence=?,
                   classification_reason=?, business_impact=?
               WHERE id=?""",
            (category, confidence, reason, business_impact, article["id"]),
        )
        conn.commit()
        counts[category] += 1

        impact_label = f" [{business_impact}]" if business_impact else ""
        print(f"  [{confidence.upper():6s}] {category}{impact_label}")
        print(f"           {article['title'][:65]}")
        print(f"           Reason: {reason}")

        time.sleep(0.5)

    # Print raw distribution before diversity selection
    print("\n  Raw Category Distribution (before diversity selection):")
    for cat in CATEGORIES:
        bar = "█" * counts.get(cat, 0)
        print(f"    {cat:<40} {counts.get(cat, 0):2d}  {bar}")

    # ── Diversity-aware final selection ───────────────────────────────────────
    print(f"\n  Applying diversity selection "
          f"(target: ≥{MIN_DIVERSITY_CATEGORIES} categories, max {TOP_N_MAX} articles)...")
    cats_covered, total_selected = apply_diversity_selection(conn)

    if cats_covered < MIN_DIVERSITY_CATEGORIES:
        print(f"  [WARN] Only {cats_covered} categories covered — "
              f"not enough diverse articles in this batch.")
    else:
        print(f"  [OK] {cats_covered} categories covered, {total_selected} articles selected.")

    conn.close()
    summary_parts = [f"{v} {k}" for k, v in counts.most_common()]
    return (
        f"{len(rows)} articles classified: " + ", ".join(summary_parts)
        + f" → {total_selected} selected across {cats_covered} categories"
    )


if __name__ == "__main__":
    result = run()
    print(f"\n[Task 3 Complete] {result}")
