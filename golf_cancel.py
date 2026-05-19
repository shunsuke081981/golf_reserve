#!/usr/bin/env python3
"""
SWING24/7 Golf Range - Cancel & Rebook

Cancels the nearest confirmed reservation, then books the first available
slot in the 7-day window starting the day after the cancelled date.

Usage:
    python3 golf_cancel.py           # headless (production)
    python3 golf_cancel.py --debug   # visible browser for testing
"""
from __future__ import annotations

import base64
import json
import os
import sys
import re
import datetime
import logging
import urllib.parse

from playwright.sync_api import sync_playwright, Page
from googleapiclient.discovery import build
from google.oauth2 import service_account

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL  = "https://swing24-kayabacho.revn.jp"
URL_LOGIN = f"{BASE_URL}/auth/login"
USERNAME  = os.environ["SWING24_USERNAME"]
PASSWORD  = os.environ["SWING24_PASSWORD"]

CALENDAR_ID    = os.environ["GOOGLE_CALENDAR_ID"]
CALENDAR_TITLE = "SWING24/7 reservation"
SCOPES         = ["https://www.googleapis.com/auth/calendar"]

EVENT_IDS = {1: 15, 2: 22, 3: 23}

PRIORITY_SLOTS = [
    ("21:00", 1),
    ("21:00", 3),
    ("21:00", 2),
    ("20:00", 1),
    ("20:00", 3),
    ("20:00", 2),
]

SEARCH_DAYS = 7
SLOT_LABEL  = {1: "打席①", 2: "打席②", 3: "打席③"}
JST         = datetime.timezone(datetime.timedelta(hours=9))
# ─────────────────────────────────────────────────────────────────────────────


def now_jst() -> datetime.datetime:
    return datetime.datetime.now(JST)


# ── Login ─────────────────────────────────────────────────────────────────────

def login(page: Page) -> None:
    log.info(f"Logging in… (id_len={len(USERNAME)} pw_len={len(PASSWORD)})")
    page.goto(URL_LOGIN)
    page.wait_for_load_state("networkidle")
    log.info(f"Login page URL: {page.url}")
    page.locator("#auth-login-login-id").fill(USERNAME)
    page.locator("#auth-login-password").fill(PASSWORD)
    page.locator("#auth-login-password").press("Enter")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    log.info(f"After login URL: {page.url}")
    if "/auth/login" in page.url:
        raise RuntimeError("Login failed — still on login page")
    log.info("Logged in")


# ── Calendar navigation ───────────────────────────────────────────────────────

def go_to_calendar(page: Page, date: datetime.date) -> None:
    d   = urllib.parse.quote(date.strftime("%Y/%m/%d"), safe="")
    url = f"{BASE_URL}/reservations/calendar?date={d}&calendar_type=2"
    page.goto(url)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    count = page.evaluate("() => document.querySelectorAll('[data-event-id]').length")
    log.info(f"Calendar {date}: elements={count}")


# ── Find nearest confirmed reservation ───────────────────────────────────────

def find_nearest_reservation(page: Page) -> datetime.date | None:
    """Return the nearest future confirmed reservation date."""
    log.info("Checking reservation history…")
    page.goto(f"{BASE_URL}/reservations/history")
    page.wait_for_load_state("networkidle")

    now          = now_jst()
    future_dates = []

    text  = page.evaluate("() => document.body.innerText")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for i, line in enumerate(lines):
        if "確定" not in line:
            continue
        window = " ".join(lines[max(0, i - 1):i + 4])
        m = re.search(r"(\d{4})/(\d{2})/(\d{2})[^\d]*(\d{2}):(\d{2})", window)
        if not m:
            continue
        try:
            dt = datetime.datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)),
                tzinfo=JST,
            )
            if dt > now:
                future_dates.append(dt.date())
                log.info(f"  Found confirmed (future): {dt}")
            else:
                log.info(f"  Found confirmed (past, skipped): {dt}")
        except ValueError:
            pass

    if not future_dates:
        log.info("No confirmed upcoming reservation found")
        return None

    nearest = min(future_dates)
    log.info(f"Nearest confirmed reservation: {nearest}")
    return nearest


# ── Cancel existing reservation ───────────────────────────────────────────────

def cancel_reservation(page: Page, date: datetime.date) -> bool:
    log.info(f"Cancelling reservation on {date}…")
    page.goto(f"{BASE_URL}/reservations/history")
    page.wait_for_load_state("networkidle")

    date_str = date.strftime("%Y/%m/%d")

    # Walk up from each '詳細' link until an ancestor containing both the
    # date string and '確定' is found — handles tables where date and status
    # are in separate <tr> rows.
    detail_href = page.evaluate(
        """(dateStr) => {
            const links = Array.from(document.querySelectorAll('a'));
            const candidates = links.filter(a => a.textContent.trim() === '詳細');
            for (const link of candidates) {
                let node = link;
                for (let i = 0; i < 20; i++) {
                    node = node.parentElement;
                    if (!node) break;
                    const text = node.textContent;
                    if (text.includes(dateStr) && text.includes('確定')) {
                        return link.getAttribute('href');
                    }
                }
            }
            return null;
        }""",
        date_str,
    )

    if not detail_href:
        log.error(f"Detail link not found for {date_str} with '確定'")
        page.screenshot(path="/tmp/golf_cancel_error.png")
        with open("/tmp/golf_history_debug.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        log.info("History page HTML saved to /tmp/golf_history_debug.html")
        return False

    target_url = BASE_URL + detail_href if detail_href.startswith("/") else detail_href
    page.goto(target_url)
    page.wait_for_load_state("networkidle")
    log.info(f"Detail page: {page.url}")

    try:
        page.once("dialog", lambda d: d.accept())
        page.get_by_text("キャンセル").first.click()
        page.wait_for_load_state("networkidle")
        try:
            hai = page.get_by_text("はい")
            if hai.count() > 0:
                hai.first.click()
                page.wait_for_load_state("networkidle")
        except Exception:
            pass
        log.info(f"Reservation on {date} cancelled ✓")
        return True
    except Exception as e:
        log.error(f"Cancel failed: {e}")
        page.screenshot(path="/tmp/golf_cancel_error.png")
        return False


# ── Slot status ───────────────────────────────────────────────────────────────

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
            if (cls.includes('js_can_reserve'))          return 'available';
            if (cls.includes('js_waiting_cancellation')) return 'cancel';
            return 'other';
        }""",
        [str(event_id), timestamp],
    )


# ── Make reservation ──────────────────────────────────────────────────────────

def make_reservation(page: Page, date: datetime.date, time_str: str, slot_num: int) -> bool:
    label = SLOT_LABEL[slot_num]
    log.info(f"Reserving {date} {time_str} {label}…")
    go_to_calendar(page, date)

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

    page.goto(BASE_URL + data_url)
    page.wait_for_load_state("networkidle")
    log.info(f"Reservation form: {page.url}")

    try:
        page.evaluate("document.querySelector('input[type=checkbox]').click()")
        page.locator("button[type='submit']", has_text="内容確認").click()
        page.wait_for_load_state("networkidle")
        log.info(f"Confirmation page: {page.url}")
        page.get_by_text("予約を登録する").first.click()
        page.wait_for_load_state("networkidle")

        body = page.evaluate("() => document.body.innerText")
        if "予約を受け付けました" in body or "予約ID" in body:
            log.info(f"Reservation confirmed: {date} {time_str} {label} ✓")
            return True
        log.warning(f"Reservation completion unconfirmed — URL: {page.url}")
        page.screenshot(path="/tmp/golf_cancel_incomplete.png")
        return False

    except Exception as e:
        log.error(f"Reservation failed: {e}")
        page.screenshot(path="/tmp/golf_cancel_reservation_error.png")
        return False


# ── Search and rebook ─────────────────────────────────────────────────────────

def search_and_rebook(page: Page, start_date: datetime.date) -> tuple[datetime.date, str, int] | None:
    """Search start_date to start_date+SEARCH_DAYS for the first available slot."""
    for offset in range(SEARCH_DAYS):
        target = start_date + datetime.timedelta(days=offset)
        log.info(f"=== Checking {target} ===")
        go_to_calendar(page, target)

        statuses: dict[tuple[str, int], str] = {}
        for time_str, slot_num in PRIORITY_SLOTS:
            st = get_slot_status(page, target, time_str, slot_num)
            statuses[(time_str, slot_num)] = st
            log.info(f"  {time_str} {SLOT_LABEL[slot_num]}: {st}")

        if all(s == "missing" for s in statuses.values()):
            log.info(f"All slots missing on {target} — outside booking window, stopping.")
            break

        available = [(t, s) for t, s in PRIORITY_SLOTS if statuses.get((t, s)) == "available"]
        if not available:
            log.info(f"No available slots on {target} — next day")
            continue

        for t, s in available:
            if make_reservation(page, target, t, s):
                return target, t, s
            log.warning(f"Reservation failed: {target} {t} {SLOT_LABEL[s]}, trying next slot")

        log.warning(f"All available slots failed on {target}, moving to next day")

    return None


# ── Google Calendar ───────────────────────────────────────────────────────────

def _build_service():
    creds_json = os.environ.get("GOOGLE_CALENDAR_CREDENTIALS")
    creds_file = os.environ.get("GOOGLE_CALENDAR_CREDENTIALS_FILE")

    if creds_json:
        raw = creds_json.strip()
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            info = json.loads(base64.b64decode(raw))
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    elif creds_file:
        creds = service_account.Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    else:
        raise RuntimeError(
            "Set GOOGLE_CALENDAR_CREDENTIALS (JSON string) "
            "or GOOGLE_CALENDAR_CREDENTIALS_FILE (file path)"
        )
    return build("calendar", "v3", credentials=creds)


def delete_calendar_event_for_date(service, date: datetime.date) -> None:
    """Delete all SWING24/7 reservation events on the given date."""
    day_start = datetime.datetime(date.year, date.month, date.day, 0, 0, tzinfo=JST)
    day_end   = day_start + datetime.timedelta(days=1)

    result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        maxResults=50,
    ).execute()

    deleted = 0
    for ev in result.get("items", []):
        if ev.get("summary") == CALENDAR_TITLE:
            service.events().delete(calendarId=CALENDAR_ID, eventId=ev["id"]).execute()
            log.info(f"Deleted calendar event for {date} (id={ev['id']})")
            deleted += 1

    if deleted == 0:
        log.info(f"No calendar event found for {date} — nothing to delete")


def create_calendar_event(service, date: datetime.date, time_str: str) -> None:
    """Create a 1-hour reservation event with 5-min popup reminder."""
    h, m     = map(int, time_str.split(":"))
    start_dt = datetime.datetime(date.year, date.month, date.day, h, m, tzinfo=JST)
    end_dt   = start_dt + datetime.timedelta(hours=1)
    body = {
        "summary": CALENDAR_TITLE,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Tokyo"},
        "end":   {"dateTime": end_dt.isoformat(),   "timeZone": "Asia/Tokyo"},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 5}],
        },
    }
    ev = service.events().insert(calendarId=CALENDAR_ID, body=body).execute()
    log.info(f"Created calendar event: {date} {time_str} (id={ev['id']})")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    debug = "--debug" in sys.argv

    cancel_date: datetime.date
    result: tuple[datetime.date, str, int] | None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not debug)
        ctx     = browser.new_context(viewport={"width": 1280, "height": 900})
        page    = ctx.new_page()
        try:
            login(page)

            # ① Find nearest confirmed reservation
            cancel_date = find_nearest_reservation(page)
            if cancel_date is None:
                log.error("No confirmed reservation found — nothing to cancel. Aborting.")
                sys.exit(1)

            # ② Cancel it
            if not cancel_reservation(page, cancel_date):
                log.error(f"Failed to cancel reservation on {cancel_date} — aborting to avoid inconsistency.")
                sys.exit(1)

            # ③ Search for next available slot from D+1
            search_start = cancel_date + datetime.timedelta(days=1)
            log.info(f"Searching for available slot from {search_start} (D+1) over {SEARCH_DAYS} days…")
            result = search_and_rebook(page, search_start)

        finally:
            browser.close()

    # ④ Update Google Calendar
    log.info("=== Updating Google Calendar ===")
    service = _build_service()

    if result is None:
        log.error(f"No available slot found in {SEARCH_DAYS}-day window after {cancel_date}.")
        log.info("Deleting cancelled calendar event and exiting.")
        try:
            delete_calendar_event_for_date(service, cancel_date)
        except Exception as e:
            log.error(f"Calendar delete failed: {e}")
        sys.exit(1)

    new_date, new_time, new_slot = result
    try:
        delete_calendar_event_for_date(service, cancel_date)
        create_calendar_event(service, new_date, new_time)
        log.info(
            f"Done: {cancel_date} cancelled → "
            f"{new_date} {new_time} {SLOT_LABEL[new_slot]} reserved ✓"
        )
    except Exception as e:
        log.error(f"Calendar update failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
