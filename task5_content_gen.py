"""
Task 5: LinkedIn Content Generation
For each of the target categories:
  1. Select best article using recency-weighted score
     (combined_score * 0.8 + recency_score * 0.2)
  2. Generate LinkedIn post text + hashtags via GPT-4o (structured JSON output)
  3. Generate image via DALL-E 3
  4. Save post to file and persist in generated_posts table
"""

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone, timedelta

import requests
from openai import OpenAI

from config import (
    DB_PATH,
    GENERATION_MODEL,
    IMAGE_API_KEY,
    IMAGE_BASE_URL,
    IMAGE_MODEL,
    IMAGE_SIZE,
    KOL_STYLE_GUIDE_PATH,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_HEADERS,
    OUTPUT_IMAGES_DIR,
    OUTPUT_POSTS_DIR,
    RECENCY_WEIGHT,
    RELEVANCE_WEIGHT,
    TARGET_CATEGORIES,
)
from prompts.generation_prompt import (
    DEFAULT_HASHTAGS,
    GENERATION_SYSTEM_TEMPLATE,
    GENERATION_USER_TEMPLATE,
    get_dalle_prompt,
)

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
    default_headers=OPENROUTER_HEADERS,
)


def load_style_guide() -> dict:
    if not os.path.exists(KOL_STYLE_GUIDE_PATH):
        raise FileNotFoundError(
            f"Style guide not found at {KOL_STYLE_GUIDE_PATH}. Run task4_kol_research.py first."
        )
    with open(KOL_STYLE_GUIDE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def recency_score(published_str: str) -> int:
    """Convert a published date string to a recency score (10/8/5/2)."""
    if not published_str:
        return 2
    now = datetime.now(timezone.utc)
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S+00:00",
    ):
        try:
            pub = datetime.strptime(published_str, fmt)
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            age = now - pub
            if age < timedelta(hours=24):
                return 10
            if age < timedelta(hours=48):
                return 8
            if age < timedelta(days=7):
                return 5
            return 2
        except ValueError:
            continue
    return 2


def get_best_article(conn: sqlite3.Connection, category: str) -> tuple[dict | None, str]:
    """
    Fetch candidates for the given category and pick the best by recency-weighted score.
    Falls back to the best available relevant article if none exists in the target category.
    Returns (article_dict, selection_reason).
    """
    rows = conn.execute(
        """SELECT id, title, source, url, summary, snippet, combined_score, published
           FROM articles
           WHERE is_relevant = 1 AND category = ?
           ORDER BY combined_score DESC
           LIMIT 10""",
        (category,),
    ).fetchall()

    if not rows:
        # Fallback: use best relevant article regardless of category
        rows = conn.execute(
            """SELECT id, title, source, url, summary, snippet, combined_score, published
               FROM articles
               WHERE is_relevant = 1
               ORDER BY combined_score DESC
               LIMIT 10""",
        ).fetchall()
        if not rows:
            return None, ""
        print(f"  [FALLBACK] No articles in '{category}' — using best available relevant article")

    best = None
    best_score = -1.0
    best_reason = ""

    for row in rows:
        article = dict(row)
        r_score  = recency_score(article.get("published", ""))
        combined = article.get("combined_score") or 0
        final    = combined * RELEVANCE_WEIGHT + r_score * RECENCY_WEIGHT
        if final > best_score:
            best_score = final
            best = article
            best_reason = (
                f"combined: {combined:.1f}, recency: {r_score}/10, final: {final:.2f}"
            )

    return best, best_reason


def _parse_post_response(raw: str) -> tuple[str, list[str]]:
    """
    Multi-strategy extraction of post_text and hashtags from an LLM response.
    Handles: markdown fences, unescaped newlines inside JSON strings, extra text.
    """
    # Strip markdown code fences first
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"\s*```", "", cleaned).strip()

    # Strategy 1: direct json.loads
    try:
        data = json.loads(cleaned)
        pt = data.get("post_text", "").strip()
        ht = data.get("hashtags", DEFAULT_HASHTAGS)
        if pt:
            return pt, ht
    except Exception:
        pass

    # Strategy 2: find the outermost {...} block and parse it
    m = re.search(r'\{[\s\S]*\}', cleaned)
    if m:
        try:
            data = json.loads(m.group())
            pt = data.get("post_text", "").strip()
            ht = data.get("hashtags", DEFAULT_HASHTAGS)
            if pt:
                return pt, ht
        except Exception:
            pass

    # Strategy 3: regex-extract values directly (handles unescaped newlines in JSON)
    pt_m = re.search(r'"post_text"\s*:\s*"([\s\S]+?)"\s*,\s*"hashtags"', cleaned)
    if pt_m:
        pt = pt_m.group(1).replace('\\n', '\n').replace('\\"', '"').strip()
        ht = DEFAULT_HASHTAGS
        ht_m = re.search(r'"hashtags"\s*:\s*(\[[^\]]*\])', cleaned)
        if ht_m:
            try:
                ht = json.loads(ht_m.group(1))
            except Exception:
                pass
        if pt:
            return pt, ht

    # Fallback: return the cleaned text as-is (no JSON wrapper)
    return cleaned, DEFAULT_HASHTAGS


def generate_post(article: dict, category: str, style_guide: dict,
                  kol_name: str = "", kol_profile: dict | None = None) -> tuple[str, list[str]]:
    """Call the LLM to generate a LinkedIn post in the style of a specific KOL.
    Returns (post_text, hashtags). Retries up to 3x."""
    synthesis_str  = json.dumps(style_guide.get("synthesis", {}), indent=2)
    kol_profile_str = json.dumps(kol_profile or {}, indent=2)

    system_prompt = GENERATION_SYSTEM_TEMPLATE.format(
        kol_name=kol_name or "a seasoned AI thought leader",
        kol_profile=kol_profile_str,
        kol_style_synthesis=synthesis_str,
    )
    user_prompt = GENERATION_USER_TEMPLATE.format(
        category=category,
        title=article["title"],
        source=article["source"],
        summary=article.get("summary") or article.get("snippet") or "(no summary)",
    )

    last_error = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=GENERATION_MODEL,
                max_tokens=800,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            )
            raw = response.choices[0].message.content.strip()
            post_text, hashtags = _parse_post_response(raw)
            return post_text, hashtags

        except Exception as e:
            last_error = e
            print(f"  [WARN] Generation attempt {attempt + 1} failed: {e}")
            time.sleep(3)

    raise RuntimeError(f"Generation failed after 3 attempts: {last_error}")


def generate_image(category: str, article_title: str, cat_slug: str, date_str: str) -> str | None:
    """
    Generate an image via 通义万相 (Tongyi Wanxiang) on Alibaba DashScope.
    DashScope image generation is async: submit a task, then poll until done.
    Retries up to 2 times on failure.
    Returns saved image path on success.
    On failure or missing key, saves the prompt as a fallback .txt and returns None.
    """
    img_prompt  = get_dalle_prompt(category, article_title)
    img_path    = os.path.join(OUTPUT_IMAGES_DIR, f"{cat_slug}_{date_str}.png")
    prompt_path = os.path.join(OUTPUT_IMAGES_DIR, f"{cat_slug}_{date_str}_prompt.txt")

    if not IMAGE_API_KEY:
        print("  [WARN] IMAGE_API_KEY not set — skipping image generation.")
        print(f"  Saving image prompt to {prompt_path} for manual use.")
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(f"Image prompt for: {category}\n\n{img_prompt}")
        return None

    headers = {
        "Authorization":     f"Bearer {IMAGE_API_KEY}",
        "Content-Type":      "application/json",
        "X-DashScope-Async": "enable",   # required for async task submission
    }

    last_error = None
    for img_attempt in range(2):   # retry once on failure
        try:
            # ── Step 1: Submit the image-generation task ───────────────────────
            submit_resp = requests.post(
                f"{IMAGE_BASE_URL}/services/aigc/text2image/image-synthesis",
                headers=headers,
                json={
                    "model": IMAGE_MODEL,
                    "input": {"prompt": img_prompt[:800]},
                    "parameters": {
                        "size": IMAGE_SIZE,
                        "n":    1,
                    },
                },
                timeout=30,
            )
            submit_resp.raise_for_status()
            task_id = submit_resp.json().get("output", {}).get("task_id")
            if not task_id:
                raise ValueError(f"No task_id in submit response: {submit_resp.json()}")
            print(f"  [INFO] 通义万相 task submitted: {task_id} (attempt {img_attempt + 1}/2)")

            # ── Step 2: Poll until SUCCEEDED or FAILED (max ~90 s) ────────────
            poll_url     = f"{IMAGE_BASE_URL}/tasks/{task_id}"
            poll_headers = {"Authorization": f"Bearer {IMAGE_API_KEY}"}
            image_url    = None
            for poll in range(18):   # 18 × 5 s = 90 s max
                time.sleep(5)
                poll_resp = requests.get(poll_url, headers=poll_headers, timeout=15)
                poll_resp.raise_for_status()
                output = poll_resp.json().get("output", {})
                status = output.get("task_status", "")
                if status == "SUCCEEDED":
                    results   = output.get("results", [])
                    image_url = results[0].get("url") if results else None
                    if not image_url:
                        raise ValueError(f"No image URL in results: {output}")
                    break
                if status == "FAILED":
                    raise RuntimeError(f"Task FAILED: {output.get('message', output)}")
                print(f"  [INFO] Task status: {status} (poll {poll + 1}/18)…")
            else:
                raise TimeoutError("通义万相 task did not complete within 90 seconds")

            # ── Step 3: Download and save the image ───────────────────────────
            img_bytes = requests.get(image_url, timeout=30).content
            with open(img_path, "wb") as f:
                f.write(img_bytes)
            return img_path   # success — exit retry loop

        except Exception as e:
            last_error = e
            print(f"  [WARN] Image attempt {img_attempt + 1} failed: {e}")
            if img_attempt < 1:
                print("  Retrying image generation in 5 s…")
                time.sleep(5)

    # All retries exhausted — save prompt for manual use
    print(f"  [WARN] Image generation failed after 2 attempts: {last_error}")
    print(f"  Saving image prompt to {prompt_path} for manual use.")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(f"Image prompt for: {category}\n\n{img_prompt}")
    return None


def save_to_db(conn: sqlite3.Connection, category: str, article: dict,
               post_text: str, hashtags: list[str],
               selection_reason: str, image_path: str | None) -> None:
    """Persist the generated post to the generated_posts table.
    Replaces any existing post for the same category (one post per category).
    """
    # Deduplication: remove stale post for this category before inserting the new one
    conn.execute("DELETE FROM generated_posts WHERE category = ?", (category,))
    conn.execute(
        """INSERT INTO generated_posts
           (category, article_title, article_source, article_url,
            post_text, hashtags, selection_reason, image_path, generated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            category,
            article.get("title", ""),
            article.get("source", ""),
            article.get("url", ""),
            post_text,
            json.dumps(hashtags),
            selection_reason,
            image_path or "",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def run() -> str:
    """Entry point for workflow.py orchestrator."""
    style_guide = load_style_guide()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    os.makedirs(OUTPUT_POSTS_DIR,  exist_ok=True)
    os.makedirs(OUTPUT_IMAGES_DIR, exist_ok=True)

    date_str  = datetime.now(timezone.utc).strftime("%Y%m%d")
    generated = []

    # Build KOL rotation list (cycle through available profiles)
    kol_profiles = style_guide.get("kols", {})
    kol_names    = [k for k, v in kol_profiles.items() if "error" not in v]
    n_kols       = len(kol_names)

    print(f"\n[Task 5] Generating LinkedIn posts for {len(TARGET_CATEGORIES)} categories "
          f"(KOL rotation: {', '.join(kol_names)})...")

    for i, category in enumerate(TARGET_CATEGORIES):
        # Rotate through KOLs: post 0 → KOL 0, post 1 → KOL 1, …
        kol_name    = kol_names[i % n_kols] if n_kols else "AI Thought Leader"
        kol_profile = kol_profiles.get(kol_name, {})

        print(f"\n  Category : {category}")
        print(f"  KOL Style: {kol_name}")
        article, sel_reason = get_best_article(conn, category)

        if not article:
            print(f"  [WARN] No relevant articles found for '{category}' — skipping")
            continue

        print(f"  Article  : {article['title'][:70]}")
        print(f"  Source   : {article['source']}  ({sel_reason})")

        # Enrich selection reason with KOL info
        sel_reason_full = f"KOL: {kol_name} | {sel_reason}"

        # Generate post text + hashtags in chosen KOL's style
        print(f"  Generating post in style of {kol_name}...")
        post_text, hashtags = generate_post(article, category, style_guide, kol_name, kol_profile)

        # Save post to file (body + separator + hashtags)
        cat_slug  = slug(category)
        post_path = os.path.join(OUTPUT_POSTS_DIR, f"{cat_slug}_{date_str}.txt")
        with open(post_path, "w", encoding="utf-8") as f:
            f.write(f"Category: {category}\n")
            f.write(f"KOL Style: {kol_name}\n")
            f.write(f"Source article: {article['title']}\n")
            f.write(f"Source: {article['source']}\n")
            f.write(f"Selection: {sel_reason_full}\n")
            f.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
            f.write("=" * 60 + "\n\n")
            f.write(post_text)
            f.write("\n\n===HASHTAGS===\n")
            f.write("  ".join(hashtags))
        print(f"  Post saved: {post_path}")
        print(f"  Hashtags : {' '.join(hashtags)}")
        print(f"  Preview  : {post_text[:200].replace(chr(10), ' ')}...")

        sel_reason = sel_reason_full  # use enriched reason for DB save

        # Generate image
        print("  Generating image via 通义万相 (DashScope)...")
        img_path = generate_image(category, article["title"], cat_slug, date_str)
        if img_path:
            print(f"  Image saved: {img_path}")

        # Persist to DB history
        save_to_db(conn, category, article, post_text, hashtags, sel_reason, img_path)

        generated.append((category, post_path, img_path))

    # ── Trim DB: keep only the latest post per category (deduplication) ─────────
    conn.execute(
        """DELETE FROM generated_posts
           WHERE id NOT IN (
               SELECT MAX(id) FROM generated_posts GROUP BY category
           )"""
    )
    conn.commit()
    remaining = conn.execute("SELECT COUNT(*) FROM generated_posts").fetchone()[0]
    print(f"  [DB] Deduplicated: {remaining} unique-category posts retained.")

    conn.close()

    images = sum(1 for _, _, img in generated if img)
    return f"{len(generated)} posts generated, {images} images created"


if __name__ == "__main__":
    result = run()
    print(f"\n[Task 5 Complete] {result}")
