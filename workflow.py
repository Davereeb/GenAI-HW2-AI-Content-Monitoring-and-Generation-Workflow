"""
HW2 Workflow Orchestrator
Runs all 5 pipeline tasks in sequence:
  Task 1: Monitor  →  Task 2: Route  →  Task 3: Classify  →  Task 4: KOL Research  →  Task 5: Generate
"""

import importlib
import time
from datetime import datetime, timezone


TASKS = [
    ("Task 1: Daily AI News Monitoring",    "task1_monitor"),
    ("Task 2: Relevance Routing",           "task2_router"),
    ("Task 3: Information Classification",  "task3_classifier"),
    ("Task 4: KOL Style Research",          "task4_kol_research"),
    ("Task 5: LinkedIn Content Generation", "task5_content_gen"),
]


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
