"""Capture uses synthetic HTTP responses and temporary workspaces only."""

import importlib.util
import json
import shutil
from email.message import Message
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from cv_job import posting
from cv_job.application_lock import application_lock

ROOT = Path(__file__).resolve().parents[1]
URL = "https://jobs.example.test/123"
HTML = ("<html><head><style>hidden css</style><script>secretScript()</script></head><body>"
        "<h1>Systems Engineer</h1><p>Operate Linux &amp; cloud infrastructure. "
        "Maintain backups and diagnose production problems. Five years of experience required.</p></body></html>")


class Response(BytesIO):
    def __init__(self, body=None, content_type="text/html; charset=utf-8"):
        super().__init__(HTML.encode() if body is None else body)
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def geturl(self):
        return URL


def fake_http(monkeypatch, response=None, failure=None):
    monkeypatch.setattr(posting.socket, "getaddrinfo", lambda *args: [(2, 1, 6, "", ("8.8.8.8", 443))])

    class Opener:
        def open(self, request, timeout):
            assert timeout == 10
            assert "Authorization" not in request.headers and "Cookie" not in request.headers
            if failure:
                raise failure
            return response if response is not None else Response()

    monkeypatch.setattr(posting, "build_opener", lambda *args: Opener())


def test_http_capture_preserves_raw_and_readable_text(monkeypatch, tmp_path):
    fake_http(monkeypatch)
    captured = posting.capture_posting(URL)
    assert captured.raw == HTML.encode()
    assert "Operate Linux & cloud" in captured.text
    assert "secretScript" not in captured.text and "hidden css" not in captured.text
    metadata = captured.save(tmp_path, "Example", "Engineer", "India")
    assert (tmp_path / "posting.html").read_bytes() == HTML.encode()
    text = (tmp_path / "job.md").read_text()
    assert URL in text and "Captured (UTC):" in text
    assert "completeness is not verified" in text and metadata["method"] == "http"


@pytest.mark.parametrize("failure", [URLError("unavailable"), HTTPError(URL, 404, "gone", {}, None)])
def test_fetch_errors_are_explicit(monkeypatch, failure):
    fake_http(monkeypatch, failure=failure)
    with pytest.raises(posting.PostingError, match="posting"):
        posting.capture_posting(URL)


@pytest.mark.parametrize("body,content_type", [
    (b"PDF", "application/pdf"),
    (b"x" * (posting.MAX_BYTES + 1), "text/plain"),
    (b"<html><div id='root'></div></html>", "text/html"),
    (("Verify you are human. " * 10).encode(), "text/html"),
])
def test_unusable_responses_fail(monkeypatch, body, content_type):
    fake_http(monkeypatch, Response(body, content_type))
    with pytest.raises(posting.PostingError):
        posting.capture_posting(URL)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.test/job", "https://user:password@example.test/job"])
def test_unsafe_url_shapes_refused(url):
    with pytest.raises(posting.PostingError):
        posting.public_url(url)


def test_local_addresses_and_redirects_refused(monkeypatch):
    monkeypatch.setattr(posting.socket, "getaddrinfo", lambda *args: [(2, 1, 6, "", ("127.0.0.1", 80))])
    with pytest.raises(posting.PostingError, match="private or local"):
        posting.public_url("http://localhost/job")
    with pytest.raises(posting.PostingError):
        posting.PublicRedirects().redirect_request(None, None, 302, "", {}, "http://localhost/job")


def test_supplied_file_needs_no_network_and_preserves_text(monkeypatch, tmp_path):
    source = tmp_path / "posting.txt"
    source.write_text("Fictional posting.\nExact original wording.\n")
    monkeypatch.setattr(posting, "public_url", lambda _: pytest.fail("manual source fetched"))
    assert posting.capture_posting(URL, str(source)).text == source.read_text()
    source.write_text(" ")
    with pytest.raises(posting.PostingError, match="empty"):
        posting.capture_posting(URL, str(source))


@pytest.fixture
def jobs(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(ROOT / "sample", workspace)
    spec = importlib.util.spec_from_file_location("jobs_posting_test", ROOT / "skills/apply-to-jobs/scripts/jobs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, workspace


def test_add_captures_before_lock_and_duplicate_never_overwrites(jobs, monkeypatch, capsys):
    module, workspace = jobs
    calls = []

    def capture(url, posting_file):
        with application_lock(workspace / "applications.json", timeout=0):
            calls.append(url)
        return posting.Posting("Exact synthetic JD", "2026-10-16T00:00:00+00:00", url, url, HTML.encode())

    monkeypatch.setattr(module, "capture_posting", capture)
    args = ["--config", str(workspace / "cv-job.yaml"), "add", "--company", "Example", "--title", "Engineer",
            "--url", URL, "--status", "skipped", "--reason", "Fictional mismatch"]
    assert module.main(args) == 0
    added = json.loads(capsys.readouterr().out)
    folder = workspace / added["folder"]
    before = (folder / "job.md").read_bytes()
    data = json.loads((workspace / "applications.json").read_text())
    assert data["applications"][0]["posting"]["method"] == "http"
    with pytest.raises(SystemExit):
        module.main(args)
    assert calls == [URL] and (folder / "job.md").read_bytes() == before


def test_failed_capture_creates_no_record_or_folder(jobs, monkeypatch, capsys):
    module, workspace = jobs
    before = (workspace / "applications.json").read_bytes()
    folders = list((workspace / "applications").iterdir())

    def fail(*args):
        raise posting.PostingError("synthetic fetch failure")

    monkeypatch.setattr(module, "capture_posting", fail)
    assert module.main(["--config", str(workspace / "cv-job.yaml"), "add", "--company", "Example",
                        "--title", "Engineer", "--url", URL]) == 2
    assert "no application added" in capsys.readouterr().err
    assert (workspace / "applications.json").read_bytes() == before
    assert list((workspace / "applications").iterdir()) == folders
