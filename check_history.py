#!/usr/bin/env python3
"""Check reservation and cancel-wait history."""
from __future__ import annotations
from playwright.sync_api import sync_playwright

URL_LOGIN = "https://swing24-kayabacho.revn.jp/auth/login"
USERNAME = "060010"
PASSWORD = "kybc0819"

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

        page.goto("https://swing24-kayabacho.revn.jp/reservations/history")
        page.wait_for_load_state("networkidle")
        page.screenshot(path="/tmp/history.png", full_page=True)

        text = page.evaluate("() => document.body.innerText")
        print("=== RESERVATION HISTORY ===")
        print(text[:3000])

        # Also check cancel-wait history if it exists
        for url in [
            "https://swing24-kayabacho.revn.jp/reservations/cancel-wait",
            "https://swing24-kayabacho.revn.jp/cancellation-waits",
            "https://swing24-kayabacho.revn.jp/waiting",
        ]:
            try:
                page.goto(url)
                page.wait_for_load_state("networkidle")
                if "404" not in page.title() and "not found" not in page.title().lower():
                    print(f"\n=== {url} ===")
                    print(page.evaluate("() => document.body.innerText")[:1000])
            except Exception:
                pass

        input("Press Enter...")
        browser.close()

if __name__ == "__main__":
    main()
