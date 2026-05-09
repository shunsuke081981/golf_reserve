#!/usr/bin/env python3
"""Click an AVAILABLE cell to see if it opens a popup or navigates."""
from __future__ import annotations
from playwright.sync_api import sync_playwright

URL_LOGIN = "https://swing24-kayabacho.revn.jp/auth/login"
USERNAME = "060010"
PASSWORD = "kybc0819"
CALENDAR_URL = "https://swing24-kayabacho.revn.jp/reservations/calendar?date=2026%2F05%2F10&calendar_type=2"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        page.goto(URL_LOGIN)
        page.wait_for_load_state("networkidle")
        page.locator("input[type='text'], input[name*='id']").first.fill(USERNAME)
        page.locator("input[type='password']").first.fill(PASSWORD)
        page.locator("button[type='submit']").first.click()
        page.wait_for_load_state("networkidle")

        page.goto(CALENDAR_URL)
        page.wait_for_load_state("networkidle")

        # Find an AVAILABLE cell
        available_cells = page.locator(".js_can_reserve").all()
        print(f"Found {len(available_cells)} AVAILABLE cells")

        if available_cells:
            cell = available_cells[0]
            ts = page.evaluate("(el) => el.getAttribute('data-usage-timestamp')", cell.element_handle())
            event_id = page.evaluate("(el) => el.getAttribute('data-event-id')", cell.element_handle())
            data_url = page.evaluate("(el) => el.getAttribute('data-url')", cell.element_handle())
            print(f"AVAILABLE cell: event_id={event_id}, timestamp={ts}")
            print(f"data-url: {data_url}")

            print("\nClicking AVAILABLE cell...")
            # Don't wait for networkidle since it might open popup not navigate
            cell.click()
            import time
            time.sleep(2)

            print(f"After click URL: {page.url}")
            page.screenshot(path="/tmp/available_click.png", full_page=False)

            # Check for popup/dialog
            popup_info = page.evaluate("""() => {
                const dialogs = document.querySelectorAll('[class*="ui-dialog"], [class*="modal"], [role="dialog"], .dialog');
                return Array.from(dialogs)
                    .filter(el => el.offsetParent !== null)
                    .map(el => ({
                        classes: el.className,
                        text: el.textContent.trim().substring(0, 200),
                    }));
            }""")
            print(f"Visible dialogs: {popup_info}")

            buttons = page.evaluate("""() =>
                Array.from(document.querySelectorAll('button, a'))
                .filter(e => e.textContent.trim() && e.offsetParent !== null)
                .map(e => e.textContent.trim())
            """)
            print(f"Visible buttons: {buttons[-10:]}")  # Last 10 buttons

        input("Press Enter...")
        browser.close()

if __name__ == "__main__":
    main()
