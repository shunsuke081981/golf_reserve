#!/usr/bin/env python3
"""Dump reservation page HTML for debugging."""
from __future__ import annotations
import sys
from playwright.sync_api import sync_playwright

URL_LOGIN = "https://swing24-kayabacho.revn.jp/auth/login"
USERNAME = "060010"
PASSWORD = "kybc0819"
RESERVATION_URL = "https://swing24-kayabacho.revn.jp/reservations/add?event_id=15&usage_timestamp_from=2026%2F05%2F10+21%3A00"

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

        page.goto(RESERVATION_URL)
        page.wait_for_load_state("networkidle")

        page.screenshot(path="/tmp/swing24_reservation_add.png", full_page=True)

        body = page.evaluate("() => document.body.innerHTML")
        with open("/tmp/swing24_reservation_add.html", "w") as f:
            f.write(body)

        print("HTML saved to /tmp/swing24_reservation_add.html")
        print("Screenshot saved to /tmp/swing24_reservation_add.png")

        # Find forms, checkboxes, buttons
        info = page.evaluate("""() => {
            const result = [];
            for (const el of document.querySelectorAll('input, label, button, a')) {
                result.push({
                    tag: el.tagName,
                    type: el.type || null,
                    name: el.name || null,
                    id: el.id || null,
                    forAttr: el.htmlFor || null,
                    text: el.textContent.trim().substring(0, 80),
                    classes: el.className.substring(0, 80),
                    visible: el.offsetParent !== null,
                });
            }
            return result;
        }""")
        for el in info:
            print(el)

        input("Press Enter to close...")
        browser.close()

if __name__ == "__main__":
    main()
