#!/usr/bin/env python3
"""Debug history page parsing."""
from __future__ import annotations
from playwright.sync_api import sync_playwright

URL_LOGIN = "https://swing24-kayabacho.revn.jp/auth/login"
USERNAME = "060010"
PASSWORD = "kybc0819"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(URL_LOGIN)
        page.wait_for_load_state("networkidle")
        page.locator("input[type='text'], input[name*='id']").first.fill(USERNAME)
        page.locator("input[type='password']").first.fill(PASSWORD)
        page.locator("button[type='submit']").first.click()
        page.wait_for_load_state("networkidle")

        page.goto("https://swing24-kayabacho.revn.jp/reservations/history")
        page.wait_for_load_state("networkidle")

        # Dump all table rows with cells
        rows = page.evaluate("""() => {
            const result = [];
            for (const tr of document.querySelectorAll('tr')) {
                const cells = Array.from(tr.querySelectorAll('td'));
                if (cells.length > 0) {
                    result.push({
                        numCells: cells.length,
                        cells: cells.map(c => c.textContent.trim()),
                    });
                }
            }
            return result;
        }""")

        print("Table rows:")
        for r in rows:
            print(f"  [{r['numCells']} cells]: {r['cells']}")

        # Also try to find rows differently
        rows2 = page.evaluate("""() => {
            const result = [];
            for (const tr of document.querySelectorAll('tbody tr, tr.list')) {
                const tds = Array.from(tr.querySelectorAll('td'));
                if (tds.length > 0) {
                    result.push(tds.map(td => td.innerText.trim()));
                }
            }
            return result;
        }""")
        print("\ntbody rows:")
        for r in rows2:
            print(f"  {r}")

        # Save HTML
        body = page.evaluate("() => document.querySelector('.l-main') ? document.querySelector('.l-main').innerHTML : document.body.innerHTML")
        with open("/tmp/history_main.html", "w") as f:
            f.write(body)
        print("\nHTML saved to /tmp/history_main.html")

        browser.close()

if __name__ == "__main__":
    main()
