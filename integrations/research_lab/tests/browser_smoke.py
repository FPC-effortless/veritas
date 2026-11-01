"""Optional actual-browser acceptance; constructed data, no model/provider calls."""

from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

from research_lab.server import LabWorkspace
from trainlab.server import Dashboard


def main():
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    server = Dashboard(
        args.root, None, 0, workspace_factory=LabWorkspace, forge_workspace=args.root / "forge-view"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    checks, errors = [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base)
                page.wait_for_function("document.querySelectorAll('#tasks tr').length === 24")
                assert page.locator(".card").count() == 4
                checks.append("Real durable queue and four summaries rendered")
                page.select_option("#protocol", "LABOS001-causal")
                page.wait_for_function(
                    "document.querySelector('#synthesis').textContent.includes('Seed 701')"
                )
                checks.append("Protocol selection fetched live per-seed synthesis")
                page.fill("#search", "DPSL")
                page.wait_for_function(
                    "document.querySelector('#knowledge').textContent"
                    ".includes('stale associations')"
                )
                checks.append("Knowledge search retrieved the DPSL lifecycle question")
                page.screenshot(path=str(args.evidence / "observatory-desktop.png"), full_page=True)
                page.select_option("#filter", "failed")
                assert page.locator("#tasks tr").count() == 0
                page.select_option("#filter", "")
                checks.append("Status filter supports empty and restored states")
                page.get_by_role("link", name="TrainLab runs").click()
                page.wait_for_function("document.title.includes('TrainLab')")
                page.wait_for_function("document.body.textContent.includes('LABOS001')")
                page.screenshot(path=str(args.evidence / "trainlab-runs.png"), full_page=True)
                checks.append("Existing TrainLab view rendered retained executions")
                page.goto(base + "/forge/")
                page.wait_for_function("document.title.includes('Forge')")
                page.screenshot(path=str(args.evidence / "forge-workspace.png"), full_page=True)
                checks.append("Existing Forge workspace rendered through shared host")
                mobile = browser.new_page(
                    viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
                )
                mobile.on("pageerror", lambda error: errors.append(str(error)))
                mobile.goto(base)
                mobile.wait_for_function("document.querySelectorAll('#tasks tr').length === 24")
                mobile.select_option("#protocol", "LABOS001-robustness")
                mobile.wait_for_function(
                    "document.querySelector('#synthesis').textContent.includes('Seed 271')"
                )
                assert not mobile.evaluate("document.documentElement.scrollWidth > innerWidth")
                mobile.screenshot(
                    path=str(args.evidence / "observatory-mobile.png"), full_page=True
                )
                checks.append("390px mobile synthesis rendered without page overflow")
                assert not errors, errors
                result = {
                    "status": "PASS",
                    "checks": checks,
                    "page_errors": errors,
                    "scope": "ACTUAL_BROWSER_IMPLEMENTATION_ACCEPTANCE",
                }
                (args.evidence / "browser-qa.json").write_text(json.dumps(result, indent=2) + "\n")
                print(json.dumps(result))
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
