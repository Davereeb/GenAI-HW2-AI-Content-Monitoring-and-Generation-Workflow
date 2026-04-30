"""
HW2 Workflow Orchestrator
Runs all 5 pipeline tasks in sequence:
  Task 1: Monitor  →  Task 2: Route  →  Task 3: Classify  →  Task 4: KOL Research  →  Task 5: Generate

Includes a diversity feedback loop:
  If Task 3 produces fewer than MIN_DIVERSITY_CATEGORIES, the orchestrator
  automatically relaxes the routing threshold to 2 and re-runs Tasks 2+3 once.
"""

import importlib
import sqlite3
import time
from datetime import datetime, timezone

from config import DB_PATH, MIN_DIVERSITY_CATEGORIES


TASKS = [
    ("Task 1: Daily AI News Monitoring",    "task1_monitor"),
    ("Task 2: Relevance Routing",           "task2_router"),
    ("Task 3: Information Classification",  "task3_classifier"),
    ("Task 4: KOL Style Research",          "task4_kol_research"),
    ("Task 5: LinkedIn Content Generation", "task5_content_gen"),
]


def _count_selected_categories() -> int:
    """Return the number of distinct categories currently marked is_relevant=1."""
    try:
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute(
            "SELECT COUNT(DISTINCT category) FROM articles WHERE is_relevant=1"
        ).fetchone()[0]
        conn.close()
        return count or 0
    except Exception:
        return 0


def run_workflow():
    print("=" * 65)
    print("  HW2: AI Content Monitoring & Generation Workflow")
    print(f"  Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 65)

    results = []

    for name, module_name in TASKS:
        print(f"\n{'─' * 65}")
        print(f"  ► {name}")
        print(f"{'─' * 65}")

        start = time.time()
        try:
            module = importlib.import_module(module_name)
            result = module.run()
            elapsed = time.time() - start
            print(f"\n  ✓ Done in {elapsed:.1f}s")
            results.append((name, "OK", elapsed, result))

            # ── Diversity feedback loop (after Task 3) ────────────────────────
            if module_name == "task3_classifier":
                cats = _count_selected_categories()
                if cats < MIN_DIVERSITY_CATEGORIES:
                    print(f"\n  ⚠  Diversity check FAILED: only {cats} categor"
                          f"{'y' if cats == 1 else 'ies'} selected "
                          f"(need ≥ {MIN_DIVERSITY_CATEGORIES}).")
                    print(f"  ↻  Relaxing mandatory minimum to 2 and re-running "
                          f"Tasks 2+3 (diversity retry)…")

                    retry_start = time.time()
                    t2 = importlib.import_module("task2_router")
                    r2 = t2.run(force_rescore=False, score_min_override=2)
                    t3 = importlib.import_module("task3_classifier")
                    r3 = t3.run()
                    retry_elapsed = time.time() - retry_start

                    cats_after = _count_selected_categories()
                    print(f"\n  ✓ Diversity retry done in {retry_elapsed:.1f}s "
                          f"→ {cats_after} categories selected")
                    results.append((
                        "  ↻ Diversity Retry (T2+T3)", "OK", retry_elapsed,
                        f"{r2} | {r3}"
                    ))
                else:
                    print(f"\n  ✓ Diversity check PASSED: {cats} categories selected.")

        except Exception as e:
            elapsed = time.time() - start
            print(f"\n  ✗ FAILED: {e}")
            results.append((name, "FAILED", elapsed, str(e)))

    # Final summary
    print(f"\n{'=' * 65}")
    print("  WORKFLOW COMPLETE — Summary")
    print(f"{'=' * 65}")
    all_ok = True
    for name, status, elapsed, detail in results:
        icon = "✓" if status == "OK" else "✗"
        print(f"  {icon} [{status:6s}] {name} ({elapsed:.1f}s)")
        print(f"           → {detail}")
        if status != "OK":
            all_ok = False

    print(f"\n  Overall: {'All tasks succeeded.' if all_ok else 'Some tasks failed — see above.'}")
    print("=" * 65)


if __name__ == "__main__":
    run_workflow()
