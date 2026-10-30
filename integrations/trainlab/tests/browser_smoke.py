"""Optional real-browser acceptance check. Requires playwright + Chromium.

Run from integrations/trainlab: PYTHONPATH=src python tests/browser_smoke.py
Only constructed fixtures and a temporary run store are used.
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from trainlab.runner import run_experiment
from trainlab.server import Dashboard


def main():
    examples = Path(__file__).resolve().parents[1] / "examples"
    with tempfile.TemporaryDirectory(prefix="trainlab-browser-") as temp:
        root = Path(temp)
        first = run_experiment(examples / "linear.json", root)
        second = run_experiment(examples / "mean.json", root)
        repeat = run_experiment(examples / "linear.json", root)
        assert first["metrics"] == repeat["metrics"]
        assert first["artifacts"] == repeat["artifacts"]
        assert first["status"] == second["status"] == "succeeded"
        with Dashboard(root, examples, 0) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(f"http://127.0.0.1:{server.server_port}")
                    expect(page.locator("#runs-body tr")).to_have_count(3)
                    page.get_by_role("button", name="Running", exact=True).click()
                    expect(page.locator("#runs-body tr")).to_have_count(0)
                    page.get_by_role("button", name="All runs", exact=True).click()
                    page.get_by_label("Search runs", exact=True).fill("Mean baseline")
                    expect(page.locator("#runs-body tr")).to_have_count(1)
                    page.get_by_label("Search runs", exact=True).fill("")
                    page.locator("#select-all").check()
                    page.locator("#compare-button").click()
                    expect(page.locator(".compare-table tbody tr")).to_have_count(3)
                    expect(page.locator(".comparison-note")).to_contain_text("differ")
                    page.get_by_label("Metric to visualize").select_option("validation_mse")
                    expect(page.locator("#chart-label")).to_contain_text("validation_mse")
                    with page.expect_download() as download:
                        page.get_by_role("button", name="Export CSV").click()
                    csv = Path(download.value.path()).read_text()
                    assert "NOT_QUALIFIED" in csv and "validation_mse" in csv
                    page.evaluate("state.comparison.runs[0].name = '  =2+2'")
                    with page.expect_download() as download:
                        page.get_by_role("button", name="Export CSV").click()
                    assert '"\'  =2+2"' in Path(download.value.path()).read_text(), (
                        "CSV formula escaped after whitespace"
                    )
                    page.locator(".compare-table .run-name").first.click()
                    expect(page.locator("#detail-dialog")).to_be_visible()
                    page.get_by_role("button", name="Verify saved files").click()
                    expect(page.locator("#verification")).to_contain_text("match")
                    page.get_by_role("button", name="View output", exact=True).click()
                    expect(page.locator("#log-content")).to_contain_text("CONSTRUCTED_ONLY")
                    with page.expect_download() as download:
                        page.get_by_role("button", name="Export record").click()
                    assert Path(download.value.path()).read_text()
                    page.get_by_role("button", name="Close run details").click()
                    page.get_by_role("link", name="Experiments", exact=True).click()
                    expect(page.locator(".recipe")).to_have_count(2)
                    page.locator('[data-launch="linear.json"]').click()
                    expect(page.locator("#runs-body tr")).to_have_count(4, timeout=15000)
                    expect(page.locator("#stat-completed")).to_have_text("4", timeout=15000)
                    page.get_by_role("button", name="Open quick start").click()
                    expect(page.locator("#guide-dialog")).to_be_visible()
                    page.keyboard.press("Escape")
                    expect(page.locator("#guide-dialog")).not_to_be_visible()
                    screenshot_root = Path("/tmp/trainlab-browser-qa")
                    screenshot_root.mkdir(exist_ok=True)
                    page.screenshot(path=str(screenshot_root / "desktop.png"), full_page=True)
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                        "mobile page overflow"
                    )
                    page.screenshot(path=str(screenshot_root / "mobile.png"), full_page=True)
                    assert not errors, errors
                    browser.close()
                    print(
                        "PASS: CLI replay, dashboard launch, filters, comparison, CSV/JSON export, "
                        "logs, hash verification, quick start, mobile layout; no browser errors."
                    )
            finally:
                server.shutdown()
                thread.join(timeout=5)


if __name__ == "__main__":
    main()
