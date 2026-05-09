#!/usr/bin/env python3
"""Monitor network requests for cancel-wait form submission."""
from __future__ import annotations
import json
from urllib.parse import parse_qs
from playwright.sync_api import sync_playwright, Request

URL_LOGIN = "https://swing24-kayabacho.revn.jp/auth/login"
USERNAME = "060010"
PASSWORD = "kybc0819"
CANCEL_URL = "https://swing24-kayabacho.revn.jp/reservations/add?event_id=15&usage_timestamp_from=2026%2F05%2F11+21%3A00"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        def on_request(req: Request):
            if "reservations" in req.url and req.method == "POST":
                print(f"\n>>> POST {req.url}")
                try:
                    body = req.post_data
                    if body:
                        params = parse_qs(body)
                        for k, v in params.items():
                            if k not in ('_csrfToken', '_tokenValidation', '_Token[fields]', '_Token[unlocked]'):
                                print(f"  {k} = {v}")
                except Exception as e:
                    print(f"  (could not parse body: {e})")

        page.on("request", on_request)

        page.goto(URL_LOGIN)
        page.wait_for_load_state("networkidle")
        page.locator("input[type='text'], input[name*='id']").first.fill(USERNAME)
        page.locator("input[type='password']").first.fill(PASSWORD)
        page.locator("button[type='submit']").first.click()
        page.wait_for_load_state("networkidle")

        # Step 1
        print("\n=== Navigating to cancel slot ===")
        page.goto(CANCEL_URL)
        page.wait_for_load_state("networkidle")
        page.locator("label[for='reservations-add-reservation-terms']").click()
        print("Checked terms")

        print("\n=== Step 1 → Submit ===")
        page.locator("button[type='submit']", has_text="内容確認").click()
        page.wait_for_load_state("networkidle")
        print(f"Now at: {page.url}")

        print("\n=== Step 2 → Submit ===")
        page.locator("button[type='submit']", has_text="内容確認").click()
        page.wait_for_load_state("networkidle")
        print(f"Now at: {page.url}")

        # Save step 2 response HTML
        body = page.evaluate("() => document.body.innerHTML")
        with open("/tmp/step2_body.html", "w") as f:
            f.write(body)
        print("HTML saved to /tmp/step2_body.html")

        input("Press Enter...")
        browser.close()

if __name__ == "__main__":
    main()
