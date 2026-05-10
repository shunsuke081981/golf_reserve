#!/usr/bin/env python3
"""
SWING24 Golf Range Auto-Reservation

Usage:
    python3 reserve.py           # headless (production)
    python3 reserve.py --debug   # visible browser for testing
"""
from __future__ import annotations

import sys
import re
import datetime
import logging
import urllib.parse
from playwright.sync_api import sync_playwright, Page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
BASE_URL  = "https://swing24-kayabacho.revn.jp"
URL_LOGIN = f"{BASE_URL}/auth/login"
USERNAME  = "060010"
PASSWORD  = "kybc0819"

# event_id per lane (confirmed from page source)
EVENT_IDS = {1: 15, 2: 22, 3: 23}  # slot_number → event_id

# Priority: (time_str "HH:MM", slot_number 1/2/3)
PRIORITY_SLOTS = [
    ("21:00", 1),
    ("21:00", 3),
    ("21:00", 2),
    ("20:00", 1),
    ("20:00", 3),
    ("20:00", 2),
]

MAX_DAYS_SEARCH = 30
SLOT_LABEL = {1: "打席①", 2: "打席②", 3: "打席③"}
# ─────────────────────────────────────────────────────────────────────────────


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


# ── Login ─────────────────────────────────────────────────────────────────────

def login(page: Page) -> None:
    log.info("Logging in…")
    page.goto(URL_LOGIN)
    page.wait_for_load_state("networkidle")
    page.locator("input[type='text'], input[name*='id'], input[name*='login']").first.fill(USERNAME)
    page.locator("input[type='password']").first.fill(PASSWORD)
    page.locator("button[type='submit'], input[type='submit']").first.click()
    page.wait_for_load_state("networkidle")
    log.info("Logged in")


# ── Calendar navigation ───────────────────────────────────────────────────────

def calendar_url(date: datetime.date) -> str:
    d = urllib.parse.quote(date.strftime("%Y/%m/%d"), safe="")
    return f"{BASE_URL}/reservations/calendar?date={d}&calendar_type=2"


def go_to_calendar(page: Page, date: datetime.date) -> None:
    page.goto(calendar_url(date))
    page.wait_for_load_state("networkidle")


# ── Existing reservation detection ───────────────────────────────────────────

def find_existing_reservation_date(page: Page) -> datetime.date | None:
    """
    Check history for an upcoming CONFIRMED (確定) reservation.
    Returns the latest confirmed future date, or None.

    Strategy: the page renders tab-separated innerText like:
      確定\\t打席②\\t2026/05/11(月) 21:00 ～ 60 分\\t詳細
    We look for lines containing "確定" followed by a date pattern nearby.
    """
    log.info("Checking reservation history…")
    page.goto(f"{BASE_URL}/reservations/history")
    page.wait_for_load_state("networkidle")

    text = page.evaluate("() => document.body.innerText")
    today = datetime.date.today()
    future_dates = []

    # Split text into lines and look for "確定" entries with a date
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for i, line in enumerate(lines):
        if "確定" not in line:
            continue
        # Look for a date in this line and adjacent lines
        search_window = " ".join(lines[max(0, i-1):i+3])
        m = re.search(r"(\d{4})/(\d{2})/(\d{2})", search_window)
        if m:
            try:
                dt = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if dt >= today:
                    future_dates.append(dt)
                    log.info(f"  Found confirmed: {dt}")
            except ValueError:
                pass

    if future_dates:
        latest = max(future_dates)
        log.info(f"Latest confirmed reservation: {latest}")
        return latest

    log.info("No confirmed upcoming reservation found")
    return None


# ── Slot status ───────────────────────────────────────────────────────────────

def get_slot_status(page: Page, date: datetime.date, time_str: str, slot_num: int) -> str:
    """
    Return 'available', 'cancel', or 'other' for the given slot on page.

    Available: class contains js_can_reserve
    Cancel:    class contains js_waiting_cancellation
    """
    event_id  = EVENT_IDS[slot_num]
    timestamp = f"{date.strftime('%Y/%m/%d')} {time_str}"

    status = page.evaluate(
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
    return status


# ── Reservation (AVAILABLE slot) ──────────────────────────────────────────────

def make_reservation(page: Page, date: datetime.date, time_str: str, slot_num: int) -> bool:
    """
    For AVAILABLE slots:
      Click cell → navigate to reservation form → agree terms
      → 内容確認へ進む → 予約を登録する
    Returns True on success.
    """
    label = SLOT_LABEL[slot_num]
    log.info(f"Reserving {date} {time_str} {label}…")

    go_to_calendar(page, date)

    # Get the data-url from the cell (navigating is more reliable than clicking)
    event_id  = EVENT_IDS[slot_num]
    timestamp = f"{date.strftime('%Y/%m/%d')} {time_str}"

    data_url = page.evaluate(
        """([eid, ts]) => {
            const el = document.querySelector(
                `[data-event-id="${eid}"][data-usage-timestamp="${ts}"]`
            );
            return el ? el.getAttribute('data-url') : null;
        }""",
        [str(event_id), timestamp],
    )

    if not data_url:
        log.error("Slot cell not found on calendar")
        return False

    # Navigate directly to the reservation form
    page.goto(BASE_URL + data_url)
    page.wait_for_load_state("networkidle")
    log.info(f"Reservation form: {page.url}")

    try:
        # 利用規約に同意する (checkbox is hidden; click label with force)
        page.locator("label[for='reservations-add-reservation-terms']").click(force=True)

        # 内容確認へ進む
        page.locator("button[type='submit']", has_text="内容確認").click()
        page.wait_for_load_state("networkidle")
        log.info(f"Confirmation page: {page.url}")

        # 予約を登録する
        page.get_by_text("予約を登録する").first.click()
        page.wait_for_load_state("networkidle")

        body = page.evaluate("() => document.body.innerText")
        if "予約を受け付けました" in body or "予約ID" in body:
            log.info(f"Reservation confirmed: {date} {time_str} {label} ✓")
            return True
        log.warning(f"Reservation completion unconfirmed — URL: {page.url}")
        page.screenshot(path="/tmp/swing24_incomplete.png")
        return False

    except Exception as e:
        log.error(f"Reservation failed: {e}")
        page.screenshot(path="/tmp/swing24_error.png")
        return False


# ── Cancel-wait (CANCEL slot) ─────────────────────────────────────────────────

def register_cancel_wait(page: Page, date: datetime.date, time_str: str, slot_num: int) -> bool:
    """
    For CANCEL slots:
      Stay on calendar → click the CANCEL cell → popup appears
      → click 登録する in the popup
    Returns True on success.
    """
    label = SLOT_LABEL[slot_num]
    log.info(f"Cancel-wait: {date} {time_str} {label}…")

    go_to_calendar(page, date)

    event_id  = EVENT_IDS[slot_num]
    timestamp = f"{date.strftime('%Y/%m/%d')} {time_str}"

    # Click the CANCEL cell — this opens a popup on the same page
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
        # Wait for the popup to open (it renders on the same page)
        # The popup has a "登録する" button
        page.get_by_text("登録する").first.wait_for(timeout=10000)
        page.get_by_text("登録する").first.click()
        page.wait_for_load_state("networkidle")

        log.info(f"Cancel-wait registered: {date} {time_str} {label} ✓")
        return True

    except Exception as e:
        log.error(f"Cancel-wait failed: {e}")
        page.screenshot(path="/tmp/swing24_cancel_error.png")
        return False


# ── Main logic ────────────────────────────────────────────────────────────────

def run_reservation_logic(page: Page) -> None:
    existing = find_existing_reservation_date(page)

    if existing:
        start_date = existing + datetime.timedelta(days=1)
        log.info(f"Confirmed reservation on {existing} → searching from {start_date}")
    else:
        start_date = datetime.date.today()
        log.info(f"No confirmed reservation → searching from {start_date}")

    for offset in range(MAX_DAYS_SEARCH):
        target = start_date + datetime.timedelta(days=offset)
        log.info(f"=== Checking {target} ===")

        go_to_calendar(page, target)

        statuses: dict[tuple[str, int], str] = {}
        for time_str, slot_num in PRIORITY_SLOTS:
            st = get_slot_status(page, target, time_str, slot_num)
            statuses[(time_str, slot_num)] = st
            log.info(f"  {time_str} {SLOT_LABEL[slot_num]}: {st}")

        available = [(t, s) for t, s in PRIORITY_SLOTS if statuses.get((t, s)) == "available"]
        cancel    = [(t, s) for t, s in PRIORITY_SLOTS if statuses.get((t, s)) == "cancel"]

        if available:
            t, s = available[0]
            if make_reservation(page, target, t, s):
                log.info("Done — reservation complete.")
                return
            log.warning("Reservation failed, trying next day")

        if cancel:
            log.info(f"{len(cancel)} CANCEL slot(s) on {target} — registering cancel-wait")
            for t, s in cancel:
                register_cancel_wait(page, target, t, s)

        if not available and not cancel:
            log.info(f"No available or cancel slots on {target} — next day")

    log.info("Search complete — no slot reserved")


if __name__ == "__main__":
    main()
