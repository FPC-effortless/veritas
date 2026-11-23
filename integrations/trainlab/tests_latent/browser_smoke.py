"""Optional real-browser acceptance for a generated constructed evidence bundle."""

import argparse
import csv
import json
from pathlib import Path


def main():
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser-executable", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    errors = []
    options = {"executable_path": str(args.browser_executable)} if args.browser_executable else {}
    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True, **options)
        page = browser.new_page(viewport={"width": 1100, "height": 850})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((args.bundle.resolve() / "atlas.html").as_uri())
        page.locator("#color").select_option("id")
        page.locator("#lines").check()
        point = page.evaluate("screen[0]")
        page.locator("#plot").click(position={"x": point[0], "y": point[1]})
        if "id" not in page.locator("#detail").inner_text():
            raise RuntimeError("point pinning did not reveal its observed row")
        page.evaluate(
            "view().rows[0].spreadsheet_probe='=1+1';view().rows[1].spreadsheet_probe='\\t=2+2'"
        )
        with page.expect_download() as download:
            page.locator("#export").click()
        destination = args.output / "plotted-rows.csv"
        download.value.save_as(destination)
        with destination.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != page.evaluate("view().rows.length"):
            raise RuntimeError("exported rows differ from displayed observations")
        if rows[0]["spreadsheet_probe"] != "'=1+1" or rows[1]["spreadsheet_probe"] != "'\t=2+2":
            raise RuntimeError("spreadsheet formulas were not neutralized")
        page.screenshot(path=str(args.output / "atlas-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 800})
        page.goto((args.bundle.resolve() / "report.html").as_uri())
        if page.locator("tbody tr").count() != 6:
            raise RuntimeError("constructed diagnostic coverage is incomplete")
        if page.evaluate("document.documentElement.scrollWidth>innerWidth"):
            raise RuntimeError("report overflows the mobile viewport")
        page.screenshot(path=str(args.output / "report-mobile.png"), full_page=True)
        browser.close()
    if errors:
        raise RuntimeError(f"browser errors: {errors}")
    (args.output / "browser.json").write_text(json.dumps({"status": "PASS", "page_errors": errors}))


if __name__ == "__main__":
    main()
