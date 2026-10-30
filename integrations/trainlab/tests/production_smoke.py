"""Actual authenticated Waitress HTTP/browser and SIGTERM acceptance.

Install trainlab-local[server], Playwright and Chromium first. Constructed only.
Optional --evidence retains native browser video, screenshots and run records.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from trainlab.production import create_credentials
from trainlab.runner import list_runs, run_experiment, verify_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    temp = None
    if args.evidence:
        args.evidence.mkdir(parents=True, exist_ok=False)
        root = args.evidence.resolve()
    else:
        temp = tempfile.TemporaryDirectory(prefix="trainlab-production-")
        root = Path(temp.name)
    server = None
    result = {
        "data": "CONSTRUCTED_ONLY",
        "qualification": "NOT_QUALIFIED",
        "checks": [],
        "browser_errors": [],
        "method": "Actual Waitress subprocess and Chromium mouse/keyboard automation",
    }
    try:
        shutil.copytree(Path(__file__).resolve().parents[1] / "examples", root / "recipes")
        for name in ("linear", "mean"):
            config = root / f"recipes/{name}.json"
            recipe = json.loads(config.read_text())
            recipe["command"][0] = sys.executable
            config.write_text(json.dumps(recipe))
            assert run_experiment(config, root / "runs")["status"] == "succeeded"
        password = secrets.token_urlsafe(24)
        create_credentials(root / "users.json", "operator", password)
        # An ephemeral bound socket selects a free test port. Startup retries
        # below detect a bind race rather than assuming the server started.
        import socket

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        log = (root / "server.log").open("wb")
        server = subprocess.Popen(
            [
                args.python,
                "-m",
                "trainlab",
                "serve",
                "--production",
                "--port",
                str(port),
                "--auth-file",
                str(root / "users.json"),
                "--runs",
                str(root / "runs"),
                "--experiments",
                str(root / "recipes"),
            ],
            stdout=log,
            stderr=log,
            env=os.environ.copy(),
        )
        deadline = time.monotonic() + 20
        while True:
            try:
                with urllib.request.urlopen(url + "/healthz", timeout=1) as response:
                    assert response.status == 200
                    break
            except (OSError, urllib.error.URLError):
                if server.poll() is not None or time.monotonic() >= deadline:
                    raise AssertionError(
                        "production server failed startup; inspect server.log"
                    ) from None
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, slow_mo=100)
            anon = browser.new_context()
            denied = anon.request.get(url + "/api/state")
            assert denied.status == 401 and "token" not in denied.text()
            assert anon.request.get(url + "/").status == 401
            assert anon.request.get(url + "/healthz").status == 200
            anon.close()
            result["checks"].append("Anonymous dashboard/API denied; aggregate health available")
            videos = root / "videos"
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                http_credentials={"username": "operator", "password": password},
                record_video_dir=str(videos),
                record_video_size={"width": 1440, "height": 1000},
                accept_downloads=True,
            )
            page = context.new_page()
            page.on("pageerror", lambda error: result["browser_errors"].append(str(error)))
            page.goto(url)
            expect(page.locator("#runs-body tr")).to_have_count(2)
            page.wait_for_timeout(1000)
            page.screenshot(path=str(root / "01-authenticated-overview.png"), full_page=True)
            page.get_by_label("Search runs").fill("Mean baseline")
            expect(page.locator("#runs-body tr")).to_have_count(1)
            page.get_by_label("Search runs").fill("")
            page.get_by_label("Select all visible runs").check()
            page.locator("#compare-button").click()
            expect(page.locator(".compare-table tbody tr")).to_have_count(2)
            expect(page.locator(".comparison-note")).to_contain_text("differ")
            page.wait_for_timeout(1000)
            page.screenshot(path=str(root / "02-comparison.png"), full_page=True)
            with page.expect_download() as download:
                page.get_by_role("button", name="Export CSV").click()
            download.value.save_as(root / "comparison.csv")
            assert "NOT_QUALIFIED" in (root / "comparison.csv").read_text()
            page.locator(".compare-table .run-name").first.click()
            page.get_by_role("button", name="Verify saved files").click()
            expect(page.locator("#verification")).to_contain_text("match")
            page.get_by_role("button", name="View output", exact=True).click()
            expect(page.locator("#log-content")).to_contain_text("CONSTRUCTED_ONLY")
            page.wait_for_timeout(1000)
            page.screenshot(path=str(root / "03-verified-run.png"), full_page=True)
            page.get_by_role("button", name="Close run details").click()
            page.get_by_role("link", name="Experiments", exact=True).click()
            page.locator('[data-launch="linear.json"]').click()
            expect(page.locator("#stat-completed")).to_have_text("3", timeout=20000)
            result["checks"].append(
                "Authenticated search/compare/CSV/logs/hash verification and UI launch passed"
            )
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(root / "04-mobile.png"), full_page=True)
            result["checks"].append("390px mobile layout has no page overflow")
            # Register one controlled long job; service shutdown must cancel it.
            config = json.loads((root / "recipes/linear.json").read_text())
            config["name"] = "Constructed shutdown acceptance"
            config["command"] = [sys.executable, "-c", "import time; time.sleep(60)"]
            config["timeout_seconds"] = 120
            (root / "recipes/shutdown.json").write_text(json.dumps(config))
            page.get_by_role("link", name="Experiments", exact=True).click()
            expect(page.locator('[data-launch="shutdown.json"]')).to_be_visible(timeout=10000)
            page.locator('[data-launch="shutdown.json"]').click()
            expect(page.locator("#stat-running")).to_have_text("1", timeout=10000)
            page.wait_for_timeout(500)
            page.screenshot(path=str(root / "05-before-shutdown.png"), full_page=True)
            video = page.video
            page.close()
            context.close()
            video.save_as(str(videos / "production-browser.webm"))
            video.delete()
            browser.close()
        server.send_signal(signal.SIGTERM)
        server.wait(timeout=12)
        log.close()
        assert server.returncode == 0
        runs = list_runs(root / "runs")
        interrupted = [run for run in runs if run["name"] == "Constructed shutdown acceptance"]
        assert len(interrupted) == 1 and interrupted[0]["status"] == "interrupted"
        assert all(verify_run(root / "runs" / run["id"])["valid"] for run in runs)
        result["checks"].append(
            "SIGTERM shuts down within 12s; active process finalized interrupted; "
            "all 4 run records verify"
        )
        assert not result["browser_errors"], result["browser_errors"]
        result["status"] = "PASS"
        print(json.dumps(result, indent=2))
    finally:
        if server is not None and server.poll() is None:
            server.kill()
            server.wait(timeout=5)
        (root / "results.json").write_text(json.dumps(result, indent=2))
        # Authentication material is deliberately excluded from retained evidence.
        (root / "users.json").unlink(missing_ok=True)
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    main()
