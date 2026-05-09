#!/usr/bin/env python3
"""Click an actual CANCEL cell on the calendar and trace the flow."""
from __future__ import annotations
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
            if "reservations" in resp.url:
                print(f"  RESPONSE {resp.status} {resp.url[:80]}")

        page.on("response", on_response)

        page.goto(URL_LOGIN)
        page.wait_for_load_state("networkidle")
        page.locator("input[type='text'], input[name*='id']").first.fill(USERNAME)
        page.locator("input[type='password']").first.fill(PASSWORD)
        page.locator("button[type='submit']").first.click()
        page.wait_for_load_state("networkidle")

        print("\n=== Calendar page ===")
        page.goto(CALENDAR_URL)
        page.wait_for_load_state("networkidle")

        # Find a CANCEL cell
        cancel_cells = page.locator(".js_waiting_cancellation").all()
        print(f"Found {len(cancel_cells)} CANCEL cells")

        if cancel_cells:
            cell = cancel_cells[0]
            ts = page.evaluate("(el) => el.getAttribute('data-usage-timestamp')", cell.element_handle())
            event_id = page.evaluate("(el) => el.getAttribute('data-event-id')", cell.element_handle())
            data_url = page.evaluate("(el) => el.getAttribute('data-url')", cell.element_handle())
            print(f"CANCEL cell: event_id={event_id}, timestamp={ts}")
            print(f"data-url: {data_url}")

            print("\nClicking CANCEL cell...")
            cell.click()
            page.wait_for_load_state("networkidle")
            print(f"After click URL: {page.url}")
            page.screenshot(path="/tmp/cancel_click_result.png", full_page=True)

            buttons = page.evaluate("""() =>
                Array.from(document.querySelectorAll('button, a'))
                .filter(e => e.textContent.trim() && e.offsetParent !== null)
                .map(e => e.textContent.trim())
            """)
            print(f"Buttons: {buttons}")

        input("Press Enter...")
        browser.close()

if __name__ == "__main__":
    main()
