"""
NBCOT School Performance scraper
Outputs: raw/nbcot_pass_rates_2024.csv  (state, program_type, school, pass_rate)

Run:
    python scrape_nbcot.py
"""

import asyncio
import csv
import re
from pathlib import Path

from playwright.async_api import async_playwright

URL = "https://www.nbcot.org/Educators-Folder/SchoolPerformance"
YEAR = "2024"
OUT_PATH = Path("raw/nbcot_pass_rates_2024.csv")

# Maps display label -> option value in #dropdownPrograms
PROGRAMS = {
    "OT Doctoral-Level Programs": "3",
    "OT Masters-Level Programs": "2",
    "OTA Level Program": "1",
}

# JS helper: set a React-controlled <select> value and fire React's onChange.
# Accepts a single [selector, value] array so Playwright's evaluate() is happy.
REACT_SELECT_JS = """
([selector, value]) => {
    const el = document.querySelector(selector);
    if (!el) return false;
    const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLSelectElement.prototype, 'value'
    ).set;
    nativeSetter.call(el, value);
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return el.value;
}
"""


def clean(text):
    return text.strip().replace("\xa0", " ")


async def get_state_options(page) -> list[tuple[str, str]]:
    """Return list of (state_name, abbrev_value) from the state dropdown."""
    opts = await page.evaluate("""() => {
        const sel = document.querySelector('#dropdownstate');
        return [...sel.options]
            .filter(o => o.value)
            .map(o => [o.text.trim(), o.value]);
    }""")
    return opts


async def set_filters(page, state_value: str, program_value: str, year_value: str):
    """Set the three dropdowns using React-compatible events."""
    await page.evaluate(REACT_SELECT_JS, ["#dropdownstate", state_value])
    await asyncio.sleep(0.15)
    await page.evaluate(REACT_SELECT_JS, ["#dropdownPrograms", program_value])
    await asyncio.sleep(0.15)
    await page.evaluate(REACT_SELECT_JS, ["#dropdownYear", year_value])
    await asyncio.sleep(0.15)


async def click_search(page):
    """Click the filter Search button (btn-secondary), not the navbar search."""
    await page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            if (btn.classList.contains('btn-secondary') ||
                btn.getAttribute('value') === 'Search') {
                btn.click();
                return;
            }
        }
    }""")


async def read_table(page) -> list[list[str]]:
    """Read all rows from the results table."""
    rows = await page.query_selector_all("table tbody tr")
    result = []
    for row in rows:
        cells = await row.query_selector_all("td")
        texts = [clean(await c.inner_text()) for c in cells]
        if texts and "no data" not in " ".join(texts).lower():
            result.append(texts)
    return result


async def scrape(playwright) -> list[dict]:
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    print(f"Loading {URL} ...")
    await page.goto(URL, wait_until="networkidle", timeout=60_000)

    states = await get_state_options(page)
    print(f"States in dropdown: {len(states)}")

    results = []
    total = len(states) * len(PROGRAMS)
    done = 0

    for state_name, state_val in states:
        for prog_label, prog_val in PROGRAMS.items():
            done += 1
            print(f"[{done}/{total}] {state_name} | {prog_label}", flush=True)

            await set_filters(page, state_val, prog_val, YEAR)
            await click_search(page)

            # Wait for table to update – either data rows or "no data"
            try:
                await page.wait_for_function(
                    """() => {
                        const rows = document.querySelectorAll('table tbody tr');
                        return rows.length > 0;
                    }""",
                    timeout=8_000,
                )
            except Exception:
                pass

            await asyncio.sleep(0.6)

            rows = await read_table(page)
            for row in rows:
                # Table columns: School (0), State (1), Passing % (2)
                school = row[0] if len(row) > 0 else ""
                # col 1 is state abbreviation (redundant, we already know it)
                pass_rate_raw = row[2] if len(row) > 2 else ""
                # Strip % sign
                pass_rate = re.sub(r"[^0-9.]", "", pass_rate_raw)
                results.append({
                    "state": state_name,
                    "program_type": prog_label,
                    "school": school,
                    "pass_rate": pass_rate,
                })

    await browser.close()
    return results


async def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        rows = await scrape(pw)

    if not rows:
        print("No data collected.")
        return

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["state", "program_type", "school", "pass_rate"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone -- {len(rows)} rows written to {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
