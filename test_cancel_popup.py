#!/usr/bin/env python3
"""Test clicking CANCEL cell popup and 登録する button (DRY RUN - does not confirm)."""
from __future__ import annotations
import time
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

        # 5/10 23:00 打席① (event_id=15) is CANCEL
        event_id = 15
        timestamp = "2026/05/10 23:00"

        print(f"\nClicking CANCEL cell: event_id={event_id}, ts={timestamp}")
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
        print(f"Cell found and clicked: {clicked}")

        # Wait for popup
        time.sleep(1)
        page.screenshot(path="/tmp/popup_open.png")

        # Check what's visible
        popup_info = page.evaluate("""() => {
            const all = document.querySelectorAll('*');
            const visible = [];
            for (const el of all) {
                if (el.textContent.trim() === '登録する' && el.offsetParent !== null) {
                    visible.push({
                        tag: el.tagName,
                        text: el.textContent.trim(),
                        classes: el.className,
                        parent: el.parentElement ? el.parentElement.className : 'none',
                    });
                }
            }
            return visible;
        }""")
        print(f"'登録する' elements: {popup_info}")

        # Try to find and show the popup HTML
        popup_html = page.evaluate("""() => {
            const el = document.querySelector('[class*="ui-dialog"], [class*="popup"], [class*="modal"], [class*="overlay"]');
            if (!el) {
                // Try to find by looking for 登録する button's parent
                const btn = Array.from(document.querySelectorAll('button, a')).find(b =>
                    b.textContent.trim() === '登録する' && b.offsetParent !== null
                );
                if (btn) {
                    let parent = btn.parentElement;
                    for (let i = 0; i < 5; i++) {
                        if (!parent) break;
                        parent = parent.parentElement;
                    }
                    return parent ? parent.outerHTML.substring(0, 500) : 'no parent';
                }
                return 'no popup found';
            }
            return el.outerHTML.substring(0, 500);
        }""")
        print(f"\nPopup HTML: {popup_html}")

        print("\nNOT clicking 登録する - this is a dry run")
        print("Screenshot saved to /tmp/popup_open.png")

        input("Press Enter to close...")
        browser.close()

if __name__ == "__main__":
    main()
