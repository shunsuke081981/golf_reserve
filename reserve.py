#!/usr/bin/env python3
"""
SWING24 Golf Range Auto-Reservation

Usage:
    python3 reserve.py           # headless (production)
    python3 reserve.py --debug   # visible browser for testing
"""
from __future__ import annotations

import os
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
USERNAME  = os.environ["SWING24_USERNAME"]
PASSWORD  = os.environ["SWING24_PASSWORD"]

EVENT_IDS = {1: 15, 2: 22, 3: 23}  # slot_number → event_id

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
JST = datetime.timezone(datetime.timedelta(hours=9))
# ─────────────────────────────────────────────────────────────────────────────


def today_jst() -> datetime.date:
    return datetime.datetime.now(JST).date()


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
    # カレンダーのスロット要素がJSで描画されるのを待つ
    try:
        page.wait_for_selector("[data-event-id]", timeout=10000)
    except Exception:
        pass  # 要素がなければmissingとして扱う


# ── Existing reservation detection ───────────────────────────────────────────

def find_existing_reservation_date(page: Page) -> datetime.date | None:
    log.info("Checking reservation history…")
    page.goto(f"{BASE_URL}/reservations/history")
    page.wait_for_load_state("networkidle")

    today = today_jst()
    future_dates = []

    text = page.evaluate("() => document.body.innerText")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for i, line in enumerate(lines):
        if "確定" not in line:
            continue
        search_window = " ".join(lines[max(0, i-1):i+4])
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


# ── Reservation (AVAILABLE slot) ──────────────────────────────────────────────

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
        page.screenshot(path="/tmp/swing24_incomplete.png")
        return False

    except Exception as e:
        log.error(f"Reservation failed: {e}")
        page.screenshot(path="/tmp/swing24_error.png")
        return False


# ── Cancel-wait (CANCEL slot) ─────────────────────────────────────────────────

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


# ── Main logic ────────────────────────────────────────────────────────────────

def run_reservation_logic(page: Page) -> None:
    today    = today_jst()
    tomorrow = today + datetime.timedelta(days=1)

    # ① 明日のキャンセル待ち（確定予約の有無に関わらず実行）
    log.info(f"=== Cancel-wait check for {tomorrow} ===")
    go_to_calendar(page, tomorrow)
    cancel_tomorrow = []
    for t, s in PRIORITY_SLOTS:
        st = get_slot_status(page, tomorrow, t, s)
        log.info(f"  {t} {SLOT_LABEL[s]}: {st}")
        if st == "cancel":
            cancel_tomorrow.append((t, s))
    if cancel_tomorrow:
        log.info(f"{len(cancel_tomorrow)} CANCEL slot(s) on {tomorrow} — registering cancel-wait")
        for t, s in cancel_tomorrow:
            register_cancel_wait(page, tomorrow, t, s)
    else:
        log.info(f"No CANCEL slots on {tomorrow}")

    # ② 確定予約チェック → あれば新規予約探索をスキップ
    existing = find_existing_reservation_date(page)
    if existing:
        log.info(f"Confirmed reservation exists on {existing}. No further search needed.")
        return

    # ③ 新規予約探索
    log.info(f"No confirmed reservation → searching from {today}")
    for offset in range(MAX_DAYS_SEARCH):
        target = today + datetime.timedelta(days=offset)
        log.info(f"=== Checking {target} ===")

        go_to_calendar(page, target)

        statuses: dict[tuple[str, int], str] = {}
        for time_str, slot_num in PRIORITY_SLOTS:
            st = get_slot_status(page, target, time_str, slot_num)
            statuses[(time_str, slot_num)] = st
            log.info(f"  {time_str} {SLOT_LABEL[slot_num]}: {st}")

        all_statuses = list(statuses.values())

        # 全枠missingは予約受付期間外 → それ以降も同様なので終了
        if all(s == "missing" for s in all_statuses):
            log.info(f"All slots missing on {target} — outside booking window, stopping.")
            break

        available = [(t, s) for t, s in PRIORITY_SLOTS if statuses.get((t, s)) == "available"]

        if available:
            t, s = available[0]
            if make_reservation(page, target, t, s):
                log.info("Done — reservation complete.")
                return
            log.warning("Reservation failed, trying next day")
        else:
            log.info(f"No available slots on {target} — next day")

    log.info("Search complete — no slot reserved")


if __name__ == "__main__":
    main()

