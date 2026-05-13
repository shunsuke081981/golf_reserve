#!/usr/bin/env python3
"""
SWING24/7 Golf Range - Google Calendar Sync

Scans the reservation site and syncs confirmed bookings (within next 4 days)
to Google Calendar under the title "SWING24/7 reservation".

Usage:
    python3 sync_calendar.py
    python3 sync_calendar.py --debug   # visible browser for testing

Required env vars:
    SWING24_USERNAME
    SWING24_PASSWORD
    GOOGLE_CALENDAR_ID              # Your Gmail address (e.g. you@gmail.com)
                                    # ⚠️ 'primary' accesses the SERVICE ACCOUNT's
                                    #    own calendar, not yours. Use your email.
    GOOGLE_CALENDAR_CREDENTIALS     # Full JSON content of service account key
                                    # (for CI/CD — store as GitHub Secret)
  or:
    GOOGLE_CALENDAR_CREDENTIALS_FILE  # Path to service account JSON key file
                                      # (for local testing)

One-time setup:
    1. Create a service account in Google Cloud Console and download the JSON key.
    2. In Google Calendar settings, share your calendar with the service account
       email (e.g. name@project.iam.gserviceaccount.com) — grant "Make changes
       to events" permission.
    3. Set GOOGLE_CALENDAR_ID to your Gmail address (not 'primary').
"""
from __future__ import annotations

import json
import os
import sys
import re
import datetime
import logging

from playwright.sync_api import sync_playwright, Page
from googleapiclient.discovery import build
from google.oauth2 import service_account

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_URL  = "https://swing24-kayabacho.revn.jp"
URL_LOGIN = f"{BASE_URL}/auth/login"
USERNAME  = os.environ["SWING24_USERNAME"]
PASSWORD  = os.environ["SWING24_PASSWORD"]

CALENDAR_TITLE = "SWING24/7 reservation"
CALENDAR_ID    = os.environ["GOOGLE_CALENDAR_ID"]
SCOPES         = ["https://www.googleapis.com/auth/calendar"]
SYNC_DAYS      = 4
JST            = datetime.timezone(datetime.timedelta(hours=9))
# ──────────────────────────────────────────────────────────────────────────────


def now_jst() -> datetime.datetime:
    return datetime.datetime.now(JST)


# ── Step A: Site scan ──────────────────────────────────────────────────────────

def _login(page: Page) -> None:
    page.goto(URL_LOGIN)
    page.wait_for_load_state("networkidle")
    page.locator("#auth-login-login-id").fill(USERNAME)
    page.locator("#auth-login-password").fill(PASSWORD)
    page.locator("#auth-login-password").press("Enter")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    if "/auth/login" in page.url:
        raise RuntimeError("Login failed — still on login page")
    log.info("Login OK")


def scan_site(page: Page) -> list[datetime.datetime]:
    """Return confirmed reservations within the next SYNC_DAYS days."""
    _login(page)

    page.goto(f"{BASE_URL}/reservations/history")
    page.wait_for_load_state("networkidle")

    now    = now_jst()
    cutoff = now + datetime.timedelta(days=SYNC_DAYS)

    text  = page.evaluate("() => document.body.innerText")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    confirmed: list[datetime.datetime] = []
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
        except ValueError:
            continue
        if now < dt <= cutoff:
            confirmed.append(dt)
            log.info(f"  Confirmed (in range): {dt.strftime('%Y-%m-%d %H:%M')}")
        else:
            log.info(f"  Confirmed (out of range, skipped): {dt.strftime('%Y-%m-%d %H:%M')}")

    log.info(f"Site scan complete: {len(confirmed)} booking(s) within next {SYNC_DAYS} days")
    return confirmed


# ── Step B: Calendar read ─────────────────────────────────────────────────────

def _build_service():
    creds_json = os.environ.get("GOOGLE_CALENDAR_CREDENTIALS")
    creds_file = os.environ.get("GOOGLE_CALENDAR_CREDENTIALS_FILE")

    if creds_json:
        info  = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    elif creds_file:
        creds = service_account.Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    else:
        raise RuntimeError(
            "Set GOOGLE_CALENDAR_CREDENTIALS (JSON string) "
            "or GOOGLE_CALENDAR_CREDENTIALS_FILE (file path)"
        )
    return build("calendar", "v3", credentials=creds)


def fetch_calendar_events(service) -> list[dict]:
    now    = now_jst()
    cutoff = now + datetime.timedelta(days=SYNC_DAYS)

    result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=now.isoformat(),
        timeMax=cutoff.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=100,
    ).execute()

    events = [e for e in result.get("items", []) if e.get("summary") == CALENDAR_TITLE]
    log.info(f"Calendar: {len(events)} '{CALENDAR_TITLE}' event(s) in next {SYNC_DAYS} days")
    return events


def _parse_start(event: dict) -> datetime.datetime:
    start = event["start"]
    if "dateTime" in start:
        return datetime.datetime.fromisoformat(start["dateTime"]).astimezone(JST)
    d = datetime.date.fromisoformat(start["date"])
    return datetime.datetime(d.year, d.month, d.day, 0, 0, tzinfo=JST)


# ── Step C: Sync ──────────────────────────────────────────────────────────────

def sync(
    site_bookings: list[datetime.datetime],
    cal_events: list[dict],
    service,
) -> None:
    # minute-precision map: start_time → event_id
    cal_map: dict[datetime.datetime, str] = {}
    for ev in cal_events:
        key = _parse_start(ev).replace(second=0, microsecond=0)
        cal_map[key] = ev["id"]

    site_set = {b.replace(second=0, microsecond=0) for b in site_bookings}

    # Create events that exist on site but not in calendar
    for booking in site_bookings:
        key = booking.replace(second=0, microsecond=0)
        if key in cal_map:
            log.info(f"Already in calendar: {key.strftime('%Y-%m-%d %H:%M')} — skip")
            continue
        end_dt = booking + datetime.timedelta(hours=1)
        body = {
            "summary": CALENDAR_TITLE,
            "start": {"dateTime": booking.isoformat(), "timeZone": "Asia/Tokyo"},
            "end":   {"dateTime": end_dt.isoformat(),  "timeZone": "Asia/Tokyo"},
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": 5}],
            },
        }
        service.events().insert(calendarId=CALENDAR_ID, body=body).execute()
        log.info(f"Created: {key.strftime('%Y-%m-%d %H:%M')}")

    # Delete calendar events that no longer exist on site (cancelled)
    for cal_time, event_id in cal_map.items():
        if cal_time not in site_set:
            service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
            log.info(f"Deleted (cancelled on site): {cal_time.strftime('%Y-%m-%d %H:%M')}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    debug = "--debug" in sys.argv

    # ── Step A: Scan site ────────────────────────────────────────────────────
    log.info("=== Step A: Scanning reservation site ===")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not debug)
            ctx  = browser.new_context(viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            try:
                site_bookings = scan_site(page)
            finally:
                browser.close()
    except Exception as e:
        log.error(f"Site scan FAILED — aborting calendar sync: {e}")
        sys.exit(1)

    # ── Step B: Fetch calendar events ────────────────────────────────────────
    log.info("=== Step B: Fetching calendar events ===")
    service    = _build_service()
    cal_events = fetch_calendar_events(service)

    # ── Step C: Sync ─────────────────────────────────────────────────────────
    log.info("=== Step C: Syncing ===")
    sync(site_bookings, cal_events, service)

    log.info("=== Done ===")


if __name__ == "__main__":
    main()
