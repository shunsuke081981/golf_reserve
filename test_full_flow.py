#!/usr/bin/env python3
"""
Full flow test:
1. Cancel-wait popup registration (5/10 23:00 打席① which is CANCEL)
2. Check what happens after clicking 登録する
"""
from __future__ import annotations
import time
from playwright.sync_api import sync_playwright, Response

URL_LOGIN = "https://swing24-kayabacho.revn.jp/auth/login"
USERNAME = "060010"
PASSWORD = "kybc0819"
CALENDAR_URL = "https://swing24-kayabacho.revn.jp/reservations/calendar?date=2026%2F05%2F10&calendar_type=2"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        def on_response(resp: Response):
            if "reservations" in resp.url or "waiting" in resp.url or "cancel" in resp.url.lower():
                print(f"  RESPONSE {resp.status} {resp.url[:100]}")

        page.on("response", on_response)

        page.goto(URL_LOGIN)
        page.wait_for_load_state("networkidle")
        page.locator("input[type='text'], input[name*='id']").first.fill(USERNAME)
        page.locator("input[type='password']").first.fill(PASSWORD)
        page.locator("button[type='submit']").first.click()
        page.wait_for_load_state("networkidle")

        page.goto(CALENDAR_URL)
        page.wait_for_load_state("networkidle")

        # Click CANCEL cell (5/10 23:00 打席①)
        event_id = 15
        timestamp = "2026/05/10 23:00"
        print(f"\nClicking CANCEL cell: {timestamp} event_id={event_id}")

        page.evaluate(
            """([eid, ts]) => {
                const el = document.querySelector(
                    `[data-event-id="${eid}"][data-usage-timestamp="${ts}"]`
                );
                if (el) el.click();
            }""",
            [str(event_id), timestamp],
        )

        # Wait for popup
        print("Waiting for 登録する button...")
        page.get_by_text("登録する").first.wait_for(timeout=10000)
        print("Popup appeared! Clicking 登録する...")

        page.screenshot(path="/tmp/before_register.png")
        page.get_by_text("登録する").first.click()

        # Wait and check
        time.sleep(2)
        page.screenshot(path="/tmp/after_register.png")
        print(f"URL after click: {page.url}")

        # Check for success/error messages
        msg = page.evaluate("""() => {
            const els = document.querySelectorAll('.flash, .message, .alert, [class*="success"], [class*="error"]');
            return Array.from(els).filter(e => e.offsetParent !== null).map(e => e.textContent.trim());
        }""")
        print(f"Messages: {msg}")

        page.wait_for_load_state("networkidle")
        page.screenshot(path="/tmp/after_register_idle.png")
        print(f"URL after networkidle: {page.url}")

        input("Press Enter to close...")
        browser.close()

if __name__ == "__main__":
    main()
