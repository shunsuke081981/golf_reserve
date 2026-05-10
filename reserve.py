#!/usr/bin/env python3
"""
SWING24 Golf Range Cancel-Wait Registration

Checks tomorrow's 6 slots. If ALL are CANCEL, registers cancel-wait for all
and sends a notification email.
"""
from __future__ import annotations

import os
import sys
import datetime
import logging
import smtplib
import urllib.parse
from email.mime.text import MIMEText
from playwright.sync_api import sync_playwright, Page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL  = "https://swing24-kayabacho.revn.jp"
URL_LOGIN = f"{BASE_URL}/auth/login"
USERNAME  = "060010"
PASSWORD  = "kybc0819"

EVENT_IDS = {1: 15, 2: 22, 3: 23}  # slot_number → event_id

PRIORITY_SLOTS = [
    ("21:00", 1),
    ("21:00", 3),
    ("21:00", 2),
    ("20:00", 1),
    ("20:00", 3),
    ("20:00", 2),
]

SLOT_LABEL     = {1: "打席①", 2: "打席②", 3: "打席③"}
NOTIFY_EMAIL   = "shunsuke081981@gmail.com"
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASSWORD", "")
# ─────────────────────────────────────────────────────────────────────────────


def send_email(subject: str, body: str) -> None:
    if not GMAIL_APP_PASS:
        log.warning("GMAIL_APP_PASSWORD not set — skipping email")
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"]    = NOTIFY_EMAIL
    msg["To"]      = NOTIFY_EMAIL
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(NOTIFY_EMAIL, GMAIL_APP_PASS)
            smtp.send_message(msg)
        log.info("Email sent")
    except Exception as e:
        log.error(f"Email failed: {e}")


def main() -> None:
    debug = "--debug" in sys.argv
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not debug)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        try:
            login(page)
            run_reservation_logic(page)
        finally:
            browser.close()


def login(page: Page) -> None:
    log.info("Logging in…")
    page.goto(URL_LOGIN)
    page.wait_for_load_state("networkidle")
    page.locator("input[type='text'], input[name*='id'], input[name*='login']").first.fill(USERNAME)
    page.locator("input[type='password']").first.fill(PASSWORD)
    page.locator("button[type='submit'], input[type='submit']").first.click()
    page.wait_for_load_state("networkidle")
    log.info("Logged in")


def calendar_url(date: datetime.date) -> str:
    d = urllib.parse.quote(date.strftime("%Y/%m/%d"), safe="")
    return f"{BASE_URL}/reservations/calendar?date={d}&calendar_type=2"


def go_to_calendar(page: Page, date: datetime.date) -> None:
    page.goto(calendar_url(date))
    page.wait_for_load_state("networkidle")


def get_slot_status(page: Page, date: datetime.date, time_str: str, slot_num: int) -> str:
    event_id  = EVENT_IDS[slot_num]
    timestamp = f"{date.strftime('%Y/%m/%d')} {time_str}"
    return page.evaluate(
        """([eid, ts]) => {
            const el = document.querySelector(
                `[data-event-id="${eid}"][data-usage-timestamp="${ts}"]`
            );
            if (!el) return 'missing';
            const cls = el.className;
            if (cls.includes('js_can_reserve')) return 'available';
            if (cls.includes('js_waiting_cancellation')) return 'cancel';
            return 'other';
        }""",
        [str(event_id), timestamp],
    )


def register_cancel_wait(page: Page, date: datetime.date, time_str: str, slot_num: int) -> bool:
    label = SLOT_LABEL[slot_num]
    log.info(f"Cancel-wait: {date} {time_str} {label}…")

    go_to_calendar(page, date)

    event_id  = EVENT_IDS[slot_num]
    timestamp = f"{date.strftime('%Y/%m/%d')} {time_str}"

    clicked = page.evaluate(
        """([eid, ts]) => {
            const el = document.querySelector(
                `[data-event-id="${eid}"][data-usage-timestamp="${ts}"]`
            );
            if (!el) return false;
            el.click();
            return true;
        }""",
        [str(event_id), timestamp],
    )

    if not clicked:
        log.error("CANCEL cell not found on calendar")
        return False

    try:
        page.get_by_text("登録する").first.wait_for(timeout=10000)
        page.get_by_text("登録する").first.click()
        page.wait_for_load_state("networkidle")
        log.info(f"Cancel-wait registered: {date} {time_str} {label} ✓")
        return True
    except Exception as e:
        log.error(f"Cancel-wait failed: {e}")
        page.screenshot(path="/tmp/swing24_cancel_error.png")
        return False


def run_reservation_logic(page: Page) -> None:
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    log.info(f"Checking {tomorrow} (tomorrow)")

    go_to_calendar(page, tomorrow)

    statuses = {}
    for time_str, slot_num in PRIORITY_SLOTS:
        st = get_slot_status(page, tomorrow, time_str, slot_num)
        statuses[(time_str, slot_num)] = st
        log.info(f"  {time_str} {SLOT_LABEL[slot_num]}: {st}")

    all_cancel = all(statuses[(t, s)] == "cancel" for t, s in PRIORITY_SLOTS)
    if not all_cancel:
        log.info("Not all 6 slots are CANCEL — nothing to do.")
        return

    log.info("All 6 slots are CANCEL — registering cancel-wait for all")
    registered = []
    for time_str, slot_num in PRIORITY_SLOTS:
        if register_cancel_wait(page, tomorrow, time_str, slot_num):
            registered.append(f"  {tomorrow} {time_str} {SLOT_LABEL[slot_num]}")

    if registered:
        lines = "\n".join(registered)
        send_email(
            subject=f"【SWING24】キャンセル待ち登録完了 {tomorrow}",
            body=f"以下の枠でキャンセル待ちを登録しました。\n\n{lines}\n",
        )
    log.info("Done.")


if __name__ == "__main__":
    main()
