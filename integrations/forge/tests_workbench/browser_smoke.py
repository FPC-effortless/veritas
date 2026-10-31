"""Actual Forge GUI acceptance, optional retained video and screenshots.

Requires both packages, trainlab-local[server], Playwright and Chromium.
All records are constructed. No source or training network calls occur.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from trainlab.production import create_credentials


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
        temp = tempfile.TemporaryDirectory(prefix="forge-gui-browser-")
        root = Path(temp.name)
    for name in ("screenshots", "videos", "downloads"):
        (root / name).mkdir()
    password = secrets.token_urlsafe(24)
    create_credentials(root / "users.json", "operator", password)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    result = {
        "status": "RUNNING",
        "data": "CONSTRUCTED_ONLY",
        "checks": [],
        "browser_errors": [],
        "console_errors": [],
    }
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
            "--runs",
            str(root / "runs"),
            "--forge-workspace",
            str(root / "datasets"),
            "--auth-file",
            str(root / "users.json"),
        ],
        env=os.environ.copy(),
        stdout=log,
        stderr=log,
    )

    def passed(message):
        result["checks"].append(message)
        print("PASS: " + message, flush=True)

    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                with urllib.request.urlopen(url + "/healthz", timeout=1) as response:
                    assert response.status == 200
                    break
            except OSError:
                if server.poll() is not None or time.monotonic() > deadline:
                    raise AssertionError("Server startup failed; inspect server.log") from None
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, slow_mo=130)
            anonymous = browser.new_context()
            for path in ("/forge/", "/forge/app.js", "/forge/shared.css", "/api/forge/state"):
                response = anonymous.request.get(url + path)
                assert response.status == 401, path
            anonymous.close()
            passed("Forge assets and APIs deny anonymous production access")
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                http_credentials={"username": "operator", "password": password},
                accept_downloads=True,
                record_video_dir=str(root / "videos"),
                record_video_size={"width": 1440, "height": 1000},
                timezone_id="America/Vancouver",
            )
            page = context.new_page()
            page.on("pageerror", lambda error: result["browser_errors"].append(str(error)))
            page.on(
                "console",
                lambda message: (
                    result["console_errors"].append(message.text)
                    if message.type == "error"
                    else None
                ),
            )

            def shot(name):
                page.wait_for_timeout(500)
                page.screenshot(path=str(root / "screenshots" / name), full_page=True)

            page.goto(url)
            page.get_by_role("link", name="Open Forge", exact=False).click()
            expect(page).to_have_title("Forge · Dataset workspace")
            expect(page.locator("#empty-state")).to_be_visible()
            shot("01-forge-empty-library.png")
            page.get_by_role("button", name="Try constructed example", exact=True).click()
            expect(page.locator("#dataset-name")).to_have_value("Workshop sensor observations")
            expect(page.locator("#source-state")).to_contain_text("Constructed example")
            shot("02-create-dataset.png")
            page.get_by_role("button", name="Create immutable release", exact=False).click()
            expect(page.locator("#detail-view")).to_be_visible(timeout=15000)
            expect(page.locator(".split-numbers strong")).to_have_text(["24", "3", "3"])
            expect(page.locator(".dataset-actions .status")).to_have_text("Verified")
            shot("03-release-overview.png")
            passed("GUI creates and verifies a persistent 30-record release with 24/3/3 splits")
            page.get_by_role("button", name="Data explorer", exact=True).click()
            expect(page.locator(".data-table tbody tr")).to_have_count(24)
            expect(page.locator(".data-table tbody")).to_contain_text("Not available at cutoff")
            page.get_by_label("Choose a separate outcome cutoff", exact=True).check()
            page.get_by_label("Preview split", exact=True).select_option("validation")
            page.get_by_role("button", name="Apply preview", exact=False).click()
            expect(page.locator(".data-table tbody tr")).to_have_count(3)
            expect(page.locator(".data-table tbody")).to_contain_text("Source verified flag: false")
            shot("04-temporal-data-explorer.png")
            with page.expect_download() as download:
                page.get_by_role("button", name="Export JSONL", exact=False).click()
            download.value.save_as(root / "downloads/validation.jsonl")
            values = [
                json.loads(line)
                for line in (root / "downloads/validation.jsonl").read_text().splitlines()
            ]
            assert len(values) == 3 and all(row["target"]["verified"] is False for row in values)
            assert all(
                set(row["features"]) == {"temperature", "pressure"} and "action" not in row
                for row in values
            )
            with page.expect_download() as download:
                page.get_by_role("button", name="Export CSV", exact=False).click()
            download.value.save_as(root / "downloads/validation.csv")
            assert (
                len(
                    list(
                        csv.DictReader(io.StringIO((root / "downloads/validation.csv").read_text()))
                    )
                )
                == 3
            )
            pin = page.locator(".pin-label code").inner_text()
            with page.expect_download() as download:
                page.get_by_role("button", name="Download manifest", exact=False).click()
            download.value.save_as(root / "downloads/manifest.json")
            assert (
                hashlib.sha256((root / "downloads/manifest.json").read_bytes()).hexdigest() == pin
            )
            passed(
                "Temporal explorer withholds future labels, applies selected fields "
                "and exports exact JSONL/CSV/manifest bytes"
            )
            page.get_by_role("button", name="Files & provenance", exact=True).click()
            expect(page.locator("#detail-tab-content")).to_contain_text("Operator declared")
            shot("05-provenance.png")
            page.get_by_role("button", name="Verify integrity", exact=False).click()
            page.locator('[data-view="activity"]').click()
            expect(page.locator("#activity-list .status").first).to_have_text(
                "Completed", timeout=10000
            )
            passed("GUI verifies frozen hashes and retains completed verification activity")
            page.locator('[data-view="create"]').click()
            page.get_by_role("button", name="Load constructed example", exact=False).click()
            expect(
                page.get_by_role("button", name="Load constructed example", exact=False)
            ).to_be_enabled()
            page.get_by_label("Dataset name", exact=True).fill(
                "Workshop observations · version two"
            )
            page.get_by_label("Source version", exact=True).fill("v2")
            page.get_by_role("button", name="Create immutable release", exact=False).click()
            expect(page.locator("#page-title")).to_have_text(
                "Workshop observations · version two", timeout=15000
            )
            page.locator('[data-view="library"]').click()
            expect(page.locator("#datasets-body tr")).to_have_count(2)
            page.get_by_label("Search datasets", exact=True).fill("version two")
            expect(page.locator("#datasets-body tr")).to_have_count(1)
            page.get_by_label("Search datasets", exact=True).fill("")
            page.get_by_label("Sort datasets", exact=True).select_option("name")
            shot("06-populated-library.png")
            page.get_by_label("Select all visible datasets", exact=True).check()
            page.locator("#compare-button").click()
            expect(page.locator(".compare-datasets tbody tr")).to_have_count(2)
            expect(page.locator(".comparison-note")).to_contain_text("source_version")
            shot("07-release-comparison.png")
            with page.expect_download() as download:
                page.get_by_role("button", name="Export comparison JSON", exact=False).click()
            download.value.save_as(root / "downloads/comparison.json")
            assert (
                len(json.loads((root / "downloads/comparison.json").read_text())["releases"]) == 2
            )
            passed("Library search/sort and real two-release comparison/export work")
            page.get_by_role("link", name="Open TrainLab", exact=False).click()
            expect(page).to_have_title("TrainLab · Experiment workspace")
            page.get_by_role("link", name="Open Forge", exact=False).click()
            expect(page).to_have_title("Forge · Dataset workspace")
            passed("Authenticated workbench switcher opens both real applications")
            page.locator('[data-view="create"]').click()
            page.get_by_role("button", name="Load constructed example", exact=False).click()
            expect(page.locator("#dataset-name")).to_have_value("Workshop sensor observations")
            page.locator("#source-file").set_input_files(
                {
                    "name": "malformed.jsonl",
                    "mimeType": "application/x-ndjson",
                    "buffer": b"{invalid json}\n",
                }
            )
            expect(page.locator("#source-state")).to_contain_text("malformed.jsonl")
            for selector in ("#ai-use", "#redistribution", "#privacy"):
                expect(page.locator(selector)).not_to_be_checked()
                page.locator(selector).check()
            page.get_by_role("button", name="Create immutable release", exact=False).click()
            expect(page.locator("#activity-view")).to_be_visible()
            expect(page.locator("#activity-list .status").first).to_have_text(
                "Failed", timeout=15000
            )
            shot("08-source-validation-error.png")
            passed(
                "Malformed JSONL produces a visible retained failure "
                "without another dataset release"
            )
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator('[data-view="library"]').click()
            expect(page.locator("#datasets-body tr")).to_have_count(2)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            shot("09-mobile-library.png")
            page.locator("#datasets-body .run-name").first.click()
            page.get_by_role("button", name="Data explorer", exact=True).click()
            expect(page.locator(".data-table tbody tr")).to_have_count(24)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            shot("10-mobile-explorer.png")
            passed("390px library and temporal explorer have no document horizontal overflow")
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.locator('[data-view="create"]').click()
            page.get_by_role("button", name="Load constructed example", exact=False).click()
            spec = json.loads((root / "downloads/manifest.json").read_text())
            spec = {
                key: spec[key]
                for key in (
                    "dataset_id",
                    "source_id",
                    "source_version",
                    "adapter",
                    "license_id",
                    "provenance_uri",
                    "split_salt",
                )
            }
            spec.update(
                dataset_id="Decoded robot replay",
                adapter="robot-jsonl",
                ai_use_allowed=True,
                redistribution_allowed=True,
                privacy_reviewed=True,
            )
            robot_rows = [
                {
                    "episode_id": f"ep-{i}",
                    "subject_id": f"robot-{i}",
                    "record_id": f"frame-{i}",
                    "time_seconds": 0,
                    "available_seconds": 1,
                    "frame_index": i,
                    "action": None,
                    "outcome": None,
                    "observation": {
                        "joint_angle": i / 10,
                        "note": "<img src=x onerror=alert(1)>" + "x" * 700,
                    },
                }
                for i in range(12)
            ]
            page.locator("#source-file").set_input_files(
                {
                    "name": "robot.jsonl",
                    "mimeType": "application/x-ndjson",
                    "buffer": "".join(json.dumps(row) + "\n" for row in robot_rows).encode(),
                }
            )
            page.locator("#spec-file").set_input_files(
                {
                    "name": "spec.json",
                    "mimeType": "application/json",
                    "buffer": json.dumps(spec).encode(),
                }
            )
            expect(page.locator("#adapter")).to_have_value("robot-jsonl")
            page.get_by_role("button", name="Create immutable release", exact=False).click()
            expect(page.locator("#page-title")).to_have_text("Decoded robot replay", timeout=15000)
            page.get_by_role("button", name="Data explorer", exact=True).click()
            expect(
                page.get_by_text("Feature visibility cutoff (relative seconds)", exact=True)
            ).to_be_visible()
            expect(page.locator(".data-table tbody tr")).to_have_count(10)
            expect(page.locator(".data-table tbody")).to_contain_text("Display truncated")
            assert page.locator(".data-table img").count() == 0
            page.screenshot(path=str(root / "screenshots/11-robot-explorer.png"), full_page=False)
            passed(
                "Robot JSONL/spec file upload uses relative clocks; "
                "HTML values are inert and long cells are bounded"
            )
            identity = page.url.split("#dataset/")[1]
            file = root / "datasets/releases" / identity / "train.jsonl"
            file.write_bytes(file.read_bytes() + b" ")
            page.get_by_role("button", name="Verify integrity", exact=False).click()
            expect(page.locator(".dataset-actions .status")).to_have_text(
                "Needs attention", timeout=15000
            )
            expect(page.locator("#notice")).to_contain_text("no longer match")
            shot("12-integrity-failure.png")
            passed(
                "Changed release bytes produce a visible failed integrity check "
                "and withhold the preview"
            )
            page.get_by_role("button", name="Open Forge guide", exact=True).click()
            expect(page.locator("#guide-dialog")).to_be_visible()
            page.keyboard.press("Escape")
            expect(page.locator("#guide-dialog")).not_to_be_visible()
            assert not result["browser_errors"], result["browser_errors"]
            # Malformed source is an asynchronous accepted job, not a failed HTTP request.
            assert not result["console_errors"], result["console_errors"]
            video = page.video
            page.close()
            context.close()
            video.save_as(str(root / "videos/forge-gui.webm"))
            video.delete()
            browser.close()
        server.send_signal(signal.SIGTERM)
        server.wait(timeout=12)
        assert server.returncode == 0
        result["status"] = "PASS"
        print(json.dumps(result, indent=2), flush=True)
    finally:
        if server.poll() is None:
            server.kill()
            server.wait(timeout=5)
        log.close()
        (root / "users.json").unlink(missing_ok=True)
        (root / "results.json").write_text(json.dumps(result, indent=2))
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    main()
