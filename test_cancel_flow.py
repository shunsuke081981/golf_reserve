#!/usr/bin/env python3
"""Test cancel-wait flow up to confirmation (does NOT submit)."""
from __future__ import annotations
from playwright.sync_api import sync_playwright

URL_LOGIN = "https://swing24-kayabacho.revn.jp/auth/login"
USERNAME = "060010"
PASSWORD = "kybc0819"
# 打席① at 23:00 on 5/10 is CANCEL
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

        page.goto(CANCEL_URL)
        page.wait_for_load_state("networkidle")
        print(f"Step 1: {page.url}")
        page.screenshot(path="/tmp/cancel_step1.png", full_page=True)

        # Click terms label
        page.locator("label[for='reservations-add-reservation-terms']").click()

        # Click 内容確認へ進む
        page.locator("button[type='submit']", has_text="内容確認").click()
        page.wait_for_load_state("networkidle")
        print(f"Step 2: {page.url}")
        page.screenshot(path="/tmp/cancel_step2.png", full_page=True)

        buttons = page.evaluate("""() =>
            Array.from(document.querySelectorAll('button, a, input[type=submit]'))
            .filter(e => e.textContent.trim())
            .map(e => ({tag: e.tagName, text: e.textContent.trim(), visible: e.offsetParent !== null}))
        """)
        print("Buttons on cancel confirmation page:")
        for b in buttons:
            if b['visible']:
                print(f"  {b}")

        print("\nNOT submitting — stopping here.")
        input("Press Enter to close...")
        browser.close()

if __name__ == "__main__":
    main()
