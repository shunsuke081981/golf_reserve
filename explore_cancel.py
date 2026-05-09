#!/usr/bin/env python3
"""Dump cancel-wait page HTML."""
from __future__ import annotations
from playwright.sync_api import sync_playwright

URL_LOGIN = "https://swing24-kayabacho.revn.jp/auth/login"
USERNAME = "060010"
PASSWORD = "kybc0819"
# 打席① at 20:00 on 5/10 is CANCEL based on test output
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

        page.screenshot(path="/tmp/swing24_cancel_page.png", full_page=True)

        info = page.evaluate("""() => {
            const result = [];
            for (const el of document.querySelectorAll('input, label, button, a')) {
                const text = el.textContent.trim();
                if (text || el.type === 'submit') {
                    result.push({
                        tag: el.tagName,
                        type: el.type || null,
                        text: text.substring(0, 80),
                        classes: el.className.substring(0, 80),
                        id: el.id || null,
                        forAttr: el.htmlFor || null,
                        visible: el.offsetParent !== null,
                    });
                }
            }
            return result;
        }""")
        for el in info:
            if el.get('visible'):
                print(el)

        input("Press Enter to close...")
        browser.close()

if __name__ == "__main__":
    main()
