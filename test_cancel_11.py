#!/usr/bin/env python3
"""Test cancel-wait with 5/11 21:00 打席① - fresh slot."""
from __future__ import annotations
import time
from playwright.sync_api import sync_playwright, Request, Response

URL_LOGIN = "https://swing24-kayabacho.revn.jp/auth/login"
USERNAME = "060010"
PASSWORD = "kybc0819"
# 5/11 21:00 打席① (event_id=15) was CANCEL in test
CANCEL_URL = "https://swing24-kayabacho.revn.jp/reservations/add?event_id=15&usage_timestamp_from=2026%2F05%2F11+21%3A00"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # Intercept responses to see redirects
        def on_response(response: Response):
            if "reservations" in response.url:
                print(f"  RESPONSE {response.status} {response.url}")

        page.on("response", on_response)

        page.goto(URL_LOGIN)
        page.wait_for_load_state("networkidle")
        page.locator("input[type='text'], input[name*='id']").first.fill(USERNAME)
        page.locator("input[type='password']").first.fill(PASSWORD)
        page.locator("button[type='submit']").first.click()
        page.wait_for_load_state("networkidle")

        # Step 1
        print(f"\n=== Step 1 ===")
        page.goto(CANCEL_URL)
        page.wait_for_load_state("networkidle")
        print(f"URL: {page.url}")

        page.locator("label[for='reservations-add-reservation-terms']").click()
        print("Checked terms")

        print("\nClicking 内容確認へ進む (Step 1→2)...")
        page.locator("button[type='submit']", has_text="内容確認").click()
        page.wait_for_load_state("networkidle")

        print(f"\n=== Step 2 ===")
        print(f"URL: {page.url}")
        page.screenshot(path="/tmp/cancel11_s2.png", full_page=True)

        # Check page content
        h1 = page.locator("h2, h3, .pageTitle").first.text_content() if page.locator("h2, h3, .pageTitle").count() else "none"
        print(f"Page title: {h1}")

        alert = page.locator(".alert, .error, [class*='alert']").first
        if alert.count() and alert.is_visible():
            print(f"Alert: {alert.text_content()}")

        # See step indicator
        steps = page.evaluate("""() => {
            const circles = document.querySelectorAll('.step-circle, .progress-step, li.active, [class*=step]');
            return Array.from(circles).slice(0, 10).map(el => ({
                cls: el.className, text: el.textContent.trim().substring(0,30)
            }));
        }""")
        print(f"Steps: {steps}")

        # Try to proceed
        btn = page.locator("button", has_text="内容確認へ進む")
        if btn.count() and btn.first.is_visible():
            print("\nClicking 内容確認へ進む (Step 2→3)...")
            # Monitor network
            with page.expect_navigation(wait_until="networkidle", timeout=10000) as nav:
                btn.first.click()
            print(f"Step 3 URL: {page.url}")
            page.screenshot(path="/tmp/cancel11_s3.png", full_page=True)

            final_btns = page.evaluate("""() =>
                Array.from(document.querySelectorAll('button, a'))
                .filter(e => e.textContent.trim() && e.offsetParent !== null)
                .map(e => e.textContent.trim())
            """)
            print(f"Final buttons: {final_btns}")

        input("Press Enter to close...")
        browser.close()

if __name__ == "__main__":
    main()
