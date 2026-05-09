#!/usr/bin/env python3
"""Dump full page structure for debugging."""
from __future__ import annotations
import sys, json, datetime, logging
from playwright.sync_api import sync_playwright, Page

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

URL_LOGIN = "https://swing24-kayabacho.revn.jp/auth/login"
USERNAME = "060010"
PASSWORD = "kybc0819"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        page.goto(URL_LOGIN)
        page.wait_for_load_state("networkidle")
        page.locator("input[type='text'], input[name*='id'], input[name*='login'], input[name*='user']").first.fill(USERNAME)
        page.locator("input[type='password']").first.fill(PASSWORD)
        page.locator("button[type='submit'], input[type='submit']").first.click()
        page.wait_for_load_state("networkidle")
        log.info("Logged in")

        page.get_by_text("予約状況を見る").first.click()
        page.wait_for_load_state("networkidle")
        log.info("On reservation page")

        page.screenshot(path="/tmp/swing24_calendar.png", full_page=True)

        # Dump key page info
        info = page.evaluate("""() => {
            // Get all element IDs and classes
            const elements = document.querySelectorAll('[id], [class]');
            const summary = [];
            for (const el of elements) {
                const text = el.textContent.trim().substring(0, 50);
                if (text) {
                    summary.push({
                        tag: el.tagName,
                        id: el.id || null,
                        classes: el.className.substring(0, 80),
                        text: text
                    });
                }
            }
            return summary.slice(0, 200);
        }""")

        print("=== PAGE ELEMENTS ===")
        for el in info:
            if any(kw in ((el.get('text') or '') + (el.get('classes') or '') + (el.get('id') or '')).lower()
                   for kw in ['打席', 'seat', 'slot', 'lane', 'calendar', 'time', 'reserve', 'book', 'cancel', 'available']):
                print(json.dumps(el, ensure_ascii=False))

        # Also dump the entire body HTML
        body_html = page.evaluate("() => document.body.innerHTML")
        with open("/tmp/swing24_body.html", "w") as f:
            f.write(body_html)
        log.info("Body HTML saved to /tmp/swing24_body.html")

        # Look for links/clickable elements with relevant text
        links = page.evaluate("""() => {
            const els = document.querySelectorAll('a, button, [onclick], [role="button"]');
            return Array.from(els).map(el => ({
                tag: el.tagName,
                text: el.textContent.trim().substring(0, 60),
                href: el.getAttribute('href'),
                classes: el.className.substring(0, 80),
                id: el.id
            })).filter(x => x.text);
        }""")

        print("\n=== CLICKABLE ELEMENTS ===")
        for el in links[:50]:
            print(json.dumps(el, ensure_ascii=False))

        input("Press Enter to close browser...")
        browser.close()


if __name__ == "__main__":
    main()
