#!/usr/bin/env python3
"""Check for confirmation dialog on cancel-wait step 2."""
from __future__ import annotations
from playwright.sync_api import sync_playwright

URL_LOGIN = "https://swing24-kayabacho.revn.jp/auth/login"
USERNAME = "060010"
PASSWORD = "kybc0819"
CANCEL_URL = "https://swing24-kayabacho.revn.jp/reservations/add?event_id=15&usage_timestamp_from=2026%2F05%2F10+23%3A00"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(URL_LOGIN)
        page.wait_for_load_state("networkidle")
        page.locator("input[type='text'], input[name*='id']").first.fill(USERNAME)
        page.locator("input[type='password']").first.fill(PASSWORD)
        page.locator("button[type='submit']").first.click()
        page.wait_for_load_state("networkidle")

        # Step 1: go to cancel slot URL
        page.goto(CANCEL_URL)
        page.wait_for_load_state("networkidle")
        page.locator("label[for='reservations-add-reservation-terms']").click()
        page.locator("button[type='submit']", has_text="内容確認").click()
        page.wait_for_load_state("networkidle")
        print(f"Step 2: {page.url}")

        # On step 2: check for form action
        form_info = page.evaluate("""() => {
            const form = document.querySelector('form');
            if (!form) return 'no form';
            return {
                action: form.action,
                method: form.method,
                buttonTypes: Array.from(form.querySelectorAll('button')).map(b => ({
                    text: b.textContent.trim(),
                    type: b.type,
                    classes: b.className,
                }))
            };
        }""")
        print(f"Form info: {form_info}")

        # Click the button and immediately take screenshot (before networkidle)
        btn = page.locator("button", has_text="内容確認へ進む")
        print(f"\nClicking button...")
        btn.first.click()

        # Wait a moment and screenshot
        import time
        time.sleep(1)
        page.screenshot(path="/tmp/cancel_after_click.png")
        print(f"URL after click: {page.url}")

        # Check for any visible overlay/dialog
        overlay_info = page.evaluate("""() => {
            const dialogs = document.querySelectorAll('[class*="dialog"], [class*="modal"], [class*="overlay"], [role="dialog"]');
            return Array.from(dialogs)
                .filter(el => el.offsetParent !== null)
                .map(el => ({
                    classes: el.className,
                    text: el.textContent.trim().substring(0, 100),
                    visible: true
                }));
        }""")
        print(f"Visible dialogs: {overlay_info}")

        # Also check for loading state
        loading = page.evaluate("() => document.querySelector('.is-active.js_loading_container') !== null")
        print(f"Loading active: {loading}")

        # Wait for all network requests
        page.wait_for_load_state("networkidle")
        print(f"URL after networkidle: {page.url}")
        page.screenshot(path="/tmp/cancel_after_networkidle.png", full_page=True)

        input("Press Enter to close...")
        browser.close()

if __name__ == "__main__":
    main()
