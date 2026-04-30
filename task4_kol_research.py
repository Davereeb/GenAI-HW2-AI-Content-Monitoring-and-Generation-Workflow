"""
Task 4: LinkedIn KOL Style Research
Analyzes the public communication style of 5 AI thought leaders via OpenRouter.
Produces a detailed JSON style guide + synthesis injected into Task 5 prompts.
"""

import json
import os
import re
import sqlite3
from datetime import datetime, timezone

from openai import OpenAI

from config import (
    DB_PATH,
    KOL_MODEL,
    KOL_STYLE_GUIDE_PATH,
    KOLS,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_HEADERS,
)


client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
    default_headers=OPENROUTER_HEADERS,
)


KOL_RESEARCH_SYSTEM = """You are an expert in professional communication styles and personal branding on LinkedIn.
You have extensive knowledge of how leading AI figures communicate with professional audiences across
LinkedIn posts, blog articles, conference keynotes, and public interviews."""

KOL_RESEARCH_USER = """Analyze the LinkedIn and public communication style of {kol_name} in detail.

Provide a structured analysis with these 8 keys:
1. hook_style: How do they open posts/articles? (e.g., bold claim, statistic, personal anecdote, question, analogy)
2. structure: How are pieces organized? (paragraph length, use of lists, whitespace, post length norms)
3. tone: Describe in 3-5 adjectives (e.g., technical, accessible, inspirational, provocative, humble)
4. credibility_signals: How do they establish authority? (credentials cited, data used, examples referenced)
5. engagement_tactics: How do they drive comments/shares? (calls to action, predictions, contrarian takes, polls)
6. signature_phrases: 3-5 recurring phrases, metaphors, or language patterns they are known for
7. topic_focus: What aspects of AI do they emphasize most? (technical, business, societal, education, etc.)
8. audience_assumption: Who do they primarily write for? (engineers, executives, students, general public, investors)

Also add:
9. retail_applicability: How can a retail industry professional adapt this KOL's style for their own content?

Respond with ONLY a valid JSON object using these exact 9 keys. Be specific — include real examples where possible."""

SYNTHESIS_SYSTEM = """You are an expert LinkedIn content strategist for the retail industry."""

SYNTHESIS_USER = """Based on the following style profiles of 5 top AI thought leaders, create a synthesized
"Retail Executive LinkedIn Post Style Guide" that a retail AI transformation professional should follow.

KOL Profiles:
{profiles_json}

Produce a JSON object with these keys:
- recommended_hook_styles: list of 3 proven hook openings adapted for retail contexts
- recommended_structure: the optimal post structure for retail executive audiences
- tone_guidelines: how to balance technical credibility with business accessibility for retail readers
- credibility_approach: how to establish authority as a retail AI expert without overstating credentials
- engagement_strategy: 3 specific tactics to drive LinkedIn engagement from retail professionals
- phrases_to_use: 5 power phrases that work for retail AI content
- phrases_to_avoid: 5 overused phrases to avoid in retail AI LinkedIn posts
- post_template: a fill-in-the-blank template for a retail AI LinkedIn post (use [PLACEHOLDER] for variable parts)

Respond with ONLY a valid JSON object."""


def clean_json(text: str) -> str:
    return re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()


def _parse_kol_json(raw: str) -> dict:
    """Multi-strategy JSON extraction — never crashes on malformed LLM output."""
    cleaned = clean_json(raw)

    # Strategy 1: direct parse
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Strategy 2: find outermost {...} block
    m = re.search(r'\{[\s\S]*\}', cleaned)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass

    # Strategy 3: graceful failure — preserve raw for debugging
    return {"error": "JSON parse failed", "raw_preview": cleaned[:300]}


def analyze_kol(kol_name: str) -> dict:
    """Call the LLM to analyze one KOL's communication style. Retries once on failure."""
    print(f"  Analyzing: {kol_name}...")
    last_err = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=KOL_MODEL,
                max_tokens=1200,
                messages=[
                    {"role": "system", "content": KOL_RESEARCH_SYSTEM},
                    {"role": "user", "content": KOL_RESEARCH_USER.format(kol_name=kol_name)},
                ],
            )
            raw = response.choices[0].message.content
            result = _parse_kol_json(raw)
            if "error" not in result:
                return result
            # Parse succeeded but got error sentinel — retry once
            last_err = result.get("error", "unknown parse error")
            print(f"  [WARN] Attempt {attempt+1}: parse failed for {kol_name}: {last_err}")
        except Exception as e:
            last_err = str(e)
            print(f"  [WARN] Attempt {attempt+1}: API error for {kol_name}: {e}")
    return {"error": last_err, "kol": kol_name}


def synthesize_styles(profiles: dict) -> dict:
    """Call Claude to synthesize all KOL profiles into a retail-specific style guide."""
    print("  Synthesizing style guide for retail context...")
    profiles_json = json.dumps(profiles, indent=2)
    try:
        response = client.chat.completions.create(
            model=KOL_MODEL,
            max_tokens=1500,
            messages=[
                {"role": "system", "content": SYNTHESIS_SYSTEM},
                {"role": "user", "content": SYNTHESIS_USER.format(profiles_json=profiles_json)},
            ],
        )
        raw = response.choices[0].message.content
        return json.loads(clean_json(raw))
    except Exception as e:
        print(f"  [WARN] Synthesis failed: {e}")
        return {"error": str(e)}


def run(force: bool = False) -> str:
    """Entry point for workflow.py / app.py.
    force=False (default): load cached style guide if it already exists.
    force=True: re-run LLM analysis even if a guide already exists.
    """
    if not force and os.path.exists(KOL_STYLE_GUIDE_PATH):
        with open(KOL_STYLE_GUIDE_PATH, encoding="utf-8") as f:
            guide = json.load(f)
        kol_count = len(guide.get("kols", {}))
        print(f"  [CACHED] Style guide already exists with {kol_count} KOL profiles — skipping API calls")
        return f"Loaded cached style guide ({kol_count} KOL profiles, generated {guide.get('generated_at','?')[:10]})"

    print(f"\n[Task 4] Analyzing {len(KOLS)} KOL communication styles...")

    kol_profiles: dict = {}
    for kol in KOLS:
        profile = analyze_kol(kol)
        kol_profiles[kol] = profile

    synthesis = synthesize_styles(kol_profiles)

    style_guide = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kols": kol_profiles,
        "synthesis": synthesis,
    }

    # Save JSON file
    with open(KOL_STYLE_GUIDE_PATH, "w", encoding="utf-8") as f:
        json.dump(style_guide, f, indent=2, ensure_ascii=False)
    print(f"  Style guide saved to: {KOL_STYLE_GUIDE_PATH}")

    # Also persist to DB for audit trail
    conn = sqlite3.connect(DB_PATH)
    analyzed_at = datetime.now(timezone.utc).isoformat()
    for kol, profile in kol_profiles.items():
        conn.execute(
            "INSERT OR REPLACE INTO kol_styles (kol_name, style_json, analyzed_at) VALUES (?, ?, ?)",
            (kol, json.dumps(profile), analyzed_at),
        )
    conn.commit()
    conn.close()

    return f"{len(kol_profiles)} KOL profiles analyzed, style guide saved to {KOL_STYLE_GUIDE_PATH}"


if __name__ == "__main__":
    result = run()
    print(f"\n[Task 4 Complete] {result}")
