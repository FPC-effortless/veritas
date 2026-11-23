"""Optional real-browser acceptance for a generated constructed evidence bundle."""

import argparse
import json
from pathlib import Path


def main():
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    errors = []
    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1100, "height": 850})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((args.bundle.resolve() / "atlas.html").as_uri())
        page.locator("#color").select_option("id")
        page.locator("#lines").check()
        point = page.evaluate("screen[0]")
        page.locator("#plot").click(position={"x": point[0], "y": point[1]})
        if "id" not in page.locator("#detail").inner_text():
            raise RuntimeError("point pinning did not reveal its observed row")
        with page.expect_download() as download:
            page.locator("#export").click()
        destination = args.output / "plotted-rows.csv"
        download.value.save_as(destination)
        if len(destination.read_text().splitlines()) != page.evaluate("view().rows.length+1"):
            raise RuntimeError("exported rows differ from displayed observations")
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
