"""Synthetic, no-network confidentiality checks for the public calibration CLI."""

import importlib.util
import io
import json
import sys
import traceback
import urllib.error
from http.client import InvalidURL
from pathlib import Path

import pytest

from investigation_world import calibration


@pytest.fixture
def cli(monkeypatch, tmp_path):
    path = Path(__file__).parents[2] / "tools/run_endpoint_calibration.py"
    spec = importlib.util.spec_from_file_location("endpoint_calibration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        calibration,
        "run_full_context_calibration",
        lambda generate, **kwargs: {"result": generate("synthetic prompt")},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(path),
            "--endpoint",
            "https://example.invalid:8443/v1/chat/completions",
            "--model",
            "synthetic",
            "--output",
            str(tmp_path / "report.json"),
        ],
    )
    return module


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user:SYNTHETIC_SECRET@example.invalid/v1/chat/completions",
        "https://SYNTHETIC_SECRET@example.invalid/v1/chat/completions",
        "https://example.invalid:SYNTHETIC_SECRET/v1/chat/completions",
        "https://[SYNTHETIC_SECRET/v1/chat/completions",
        "file:///SYNTHETIC_SECRET",
        "https:///SYNTHETIC_SECRET",
    ],
)
def test_url_credentials_are_rejected_before_request(cli, monkeypatch, endpoint, capsys, tmp_path):
    sys.argv[2] = endpoint
    called = []
    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda *a, **kw: called.append(True))
    with pytest.raises(ValueError) as error:
        cli.main()
    assert "SYNTHETIC_SECRET" not in "".join(traceback.format_exception(error.value))
    assert not called
    assert not (tmp_path / "report.json").exists()
    assert "SYNTHETIC_SECRET" not in str(capsys.readouterr())


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.HTTPError(
            "https://example.invalid/?secret=SYNTHETIC_SECRET",
            401,
            "SYNTHETIC_SECRET",
            {},
            io.BytesIO(b"SYNTHETIC_SECRET"),
        ),
        urllib.error.URLError("SYNTHETIC_SECRET"),
        TimeoutError("SYNTHETIC_SECRET"),
        InvalidURL("SYNTHETIC_SECRET"),
    ],
)
def test_endpoint_errors_do_not_echo_response_or_transport_details(
    cli,
    monkeypatch,
    error,
    capsys,
    tmp_path,
):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli.urllib.request, "urlopen", fail)
    with pytest.raises(RuntimeError) as raised:
        cli.main()
    rendered = "".join(traceback.format_exception(raised.value))
    assert "SYNTHETIC_SECRET" not in rendered
    assert "model endpoint" in str(raised.value)
    assert not (tmp_path / "report.json").exists()
    assert "SYNTHETIC_SECRET" not in str(capsys.readouterr())


def test_success_retains_environment_auth_and_only_safe_host(cli, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("VERITAS_MODEL_API_KEY", "SYNTHETIC_SECRET")
    sys.argv[2] += "?key=SYNTHETIC_SECRET"
    requests = []

    def respond(request, **kwargs):
        requests.append(request)
        return io.BytesIO(b'{"choices":[{"message":{"content":"{}"}}]}')

    monkeypatch.setattr(cli.urllib.request, "urlopen", respond)
    cli.main()
    assert requests[0].get_header("Authorization") == "Bearer SYNTHETIC_SECRET"
    report_text = (tmp_path / "report.json").read_text()
    report = json.loads(report_text)
    assert report["runtime"]["endpoint_host"] == "example.invalid:8443"
    assert report["runtime"]["model_calls"] == 1
    assert "SYNTHETIC_SECRET" not in report_text + str(capsys.readouterr())


@pytest.mark.parametrize(
    "body",
    [
        b"SYNTHETIC_SECRET",
        b"\xffSYNTHETIC_SECRET",
        b'{"SYNTHETIC_SECRET": true}',
        b'[{"SYNTHETIC_SECRET": true}]',
    ],
)
def test_invalid_response_diagnostics_are_safe(cli, monkeypatch, body, capsys, tmp_path):
    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(body))
    with pytest.raises(RuntimeError) as raised:
        cli.main()
    assert "SYNTHETIC_SECRET" not in "".join(traceback.format_exception(raised.value))
    assert not (tmp_path / "report.json").exists()
    assert "SYNTHETIC_SECRET" not in str(capsys.readouterr())
