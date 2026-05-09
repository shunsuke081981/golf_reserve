#!/usr/bin/env python3
"""Debug cancel-wait step 2 HTML."""
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
        page.locator("label[for='reservations-add-reservation-terms']").click()
        page.locator("button[type='submit']", has_text="内容確認").click()
        page.wait_for_load_state("networkidle")
        print(f"Step 2 URL: {page.url}")

        # Dump all form inputs on step 2
        inputs = page.evaluate("""() =>
            Array.from(document.querySelectorAll('input, textarea, select')).map(el => ({
                type: el.type,
                name: el.name,
                id: el.id,
                value: el.value,
                checked: el.checked,
                required: el.required,
                classes: el.className,
            }))
        """)
        print("\nForm inputs on step 2:")
        for inp in inputs:
            print(f"  {inp}")

        # Check if checkbox is checked
        checked = page.evaluate("() => { const el = document.querySelector('input[type=\"checkbox\"]'); return el ? el.checked : 'no checkbox'; }")
        print(f"\nCheckbox checked: {checked}")

        # Try checking it and clicking
        checkbox_label = page.locator("label.cmn-check")
        if checkbox_label.count():
            print(f"Found {checkbox_label.count()} cmn-check labels")
            # If not checked, check it
            cb = page.locator("input[type='checkbox']")
            if cb.count():
                is_checked = page.evaluate("() => document.querySelector('input[type=\"checkbox\"]').checked")
                print(f"Checkbox currently checked: {is_checked}")
                if not is_checked:
                    checkbox_label.first.click()
                    print("Clicked label to check")

        # Now try to proceed
        btn = page.locator("button[type='submit']", has_text="内容確認")
        if btn.count():
            print(f"\nClicking button: {btn.first.text_content()}")
            btn.first.click()
            page.wait_for_load_state("networkidle")
            print(f"After click URL: {page.url}")
            page.screenshot(path="/tmp/cancel_s2_after.png", full_page=True)

            buttons = page.evaluate("""() =>
                Array.from(document.querySelectorAll('button, a'))
                .filter(e => e.textContent.trim() && e.offsetParent !== null)
                .map(e => e.textContent.trim())
            """)
            print(f"Buttons: {buttons}")

        input("Press Enter to close...")
        browser.close()

if __name__ == "__main__":
    main()
