#!/usr/bin/env python3
"""Test cancel-wait flow through all steps."""
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

        # Step 1
        page.goto(CANCEL_URL)
        page.wait_for_load_state("networkidle")
        print(f"Step 1: {page.url}")

        label = page.locator("label[for='reservations-add-reservation-terms']")
        if label.count():
            label.click()
            print("Checked terms")

        page.locator("button[type='submit']", has_text="内容確認").click()
        page.wait_for_load_state("networkidle")
        print(f"Step 2: {page.url}")
        page.screenshot(path="/tmp/cancel_s2.png", full_page=True)

        # Check if there's another terms checkbox on step 2
        label2 = page.locator("label[for='reservations-add-reservation-terms']")
        if label2.count():
            checkbox = page.locator("input#reservations-add-reservation-terms")
            if checkbox.count() and not page.evaluate("document.getElementById('reservations-add-reservation-terms').checked"):
                label2.click()
                print("Checked terms again (step 2)")

        # Look for proceed button on step 2
        proceed2 = page.locator("button[type='submit'], button", has_text="内容確認")
        if proceed2.count():
            proceed2.first.click()
            page.wait_for_load_state("networkidle")
            print(f"Step 3: {page.url}")
            page.screenshot(path="/tmp/cancel_s3.png", full_page=True)

        buttons = page.evaluate("""() =>
            Array.from(document.querySelectorAll('button, a, input[type=submit]'))
            .filter(e => e.textContent.trim() && e.offsetParent !== null)
            .map(e => ({tag: e.tagName, text: e.textContent.trim()}))
        """)
        print("Final page buttons:")
        for b in buttons:
            print(f"  {b}")

        print("\nNOT submitting.")
        input("Press Enter to close...")
        browser.close()

if __name__ == "__main__":
    main()
