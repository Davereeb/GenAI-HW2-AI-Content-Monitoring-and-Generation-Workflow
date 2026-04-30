"""
Daily workflow scheduler.
Fires at Beijing 08:00 every day via APScheduler BackgroundScheduler.
Module-level singleton prevents duplicate jobs across Streamlit reruns.
"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    EMAIL_PASSWORD,
    EMAIL_RECEIVER,
    EMAIL_SENDER,
    EMAIL_SMTP_HOST,
    EMAIL_SMTP_PORT,
    SCHEDULE_HOUR,
    SCHEDULE_MINUTE,
    SCHEDULE_TIMEZONE,
)

_scheduler: BackgroundScheduler | None = None


def run_full_workflow() -> None:
    """Run all 5 tasks in sequence, then send email notification."""
    print("[Scheduler] Starting daily workflow...")
    results = {}

    task_modules = [
        ("task1_monitor",     "Task 1: Monitor"),
        ("task2_router",      "Task 2: Route"),
        ("task3_classifier",  "Task 3: Classify"),
        ("task4_kol_research","Task 4: KOL Research"),
        ("task5_content_gen", "Task 5: Generate"),
    ]

    for module_name, label in task_modules:
        try:
            import importlib
            mod = importlib.import_module(module_name)
            result = mod.run()
            results[label] = result
            print(f"[Scheduler] {label} — {result}")
        except Exception as e:
            results[label] = f"FAILED: {e}"
            print(f"[Scheduler] {label} — FAILED: {e}")

    send_email_notification(results)
    print("[Scheduler] Daily workflow complete.")


def send_email_notification(results: dict) -> None:
    """Send a summary email via SMTP. Silently skips if EMAIL_SENDER is not configured."""
    if not EMAIL_SENDER or not EMAIL_RECEIVER:
        print("[Scheduler] Email not configured — skipping notification.")
        return

    subject = "[AI Retail Workflow] Daily run complete"
    lines = ["Daily AI Retail Content Workflow has completed.\n"]
    for label, result in results.items():
        lines.append(f"  {label}:\n    {result}\n")
    body = "\n".join(lines)

    msg = MIMEMultipart()
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECEIVER
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        print(f"[Scheduler] Email sent to {EMAIL_RECEIVER}")
    except Exception as e:
        print(f"[Scheduler] Email send failed: {e}")


def start_scheduler() -> None:
    """Start the background scheduler. Idempotent — safe to call multiple times."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return

    tz = pytz.timezone(SCHEDULE_TIMEZONE)
    _scheduler = BackgroundScheduler(timezone=tz)
    _scheduler.add_job(
        run_full_workflow,
        trigger=CronTrigger(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE, timezone=tz),
        id="daily_workflow",
        replace_existing=True,
    )
    _scheduler.start()
    print(
        f"[Scheduler] Started — daily run at "
        f"{SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d} {SCHEDULE_TIMEZONE}"
    )


def get_next_run_time() -> str:
    """Return a human-readable string for the next scheduled run."""
    if _scheduler is None or not _scheduler.running:
        return "Scheduler not running"
    job = _scheduler.get_job("daily_workflow")
    if job and job.next_run_time:
        return job.next_run_time.strftime("%Y-%m-%d %H:%M %Z")
    return "Unknown"
