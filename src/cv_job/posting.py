"""Preserve a public posting response without an agent or a browser session."""

import ipaddress
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BYTES = 2 * 1024 * 1024


class PostingError(ValueError):
    """Capture failed; do not create a record pretending to have saved a JD."""


def public_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise PostingError("posting URL must be public HTTP(S), without credentials")
    try:
        addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except (OSError, ValueError) as exc:
        raise PostingError("posting host could not be resolved") from exc
    if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
        raise PostingError("posting URL must not target a private or local network")


class PublicRedirects(HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden += 1
        if tag in {"p", "div", "li", "br", "h1", "h2", "h3", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li", "h1", "h2", "h3", "section"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


@dataclass(frozen=True)
class Posting:
    text: str
    captured_at: str
    source_url: str
    final_url: str
    raw: bytes | None = None
    content_type: str = "text/plain"

    def save(self, folder: Path, company: str, title: str, location: str) -> dict:
        # The caller has reserved a new folder under the application lock.
        header = (f"# {company} — {title}\n\nLocation: {location}\nSource: {self.source_url}\n"
                  f"Captured (UTC): {self.captured_at}\nFinal URL: {self.final_url}\n\n")
        if self.raw is not None:
            header += ("Capture: public HTTP response; JavaScript was not run. Full JD completeness is not verified.\n"
                       "The original response is preserved in posting.html.\n\n")
            (folder / "posting.html").write_bytes(self.raw)
        else:
            header += "Capture: supplied posting file.\n\n"
        (folder / "job.md").write_text(header + "---\n\n" + self.text, encoding="utf-8")
        return {"captured_at": self.captured_at, "source_url": self.source_url, "final_url": self.final_url,
                "method": "http" if self.raw is not None else "posting_file",
                "content_type": self.content_type, "text": "job.md",
                "raw": "posting.html" if self.raw is not None else None}


def capture_posting(url: str, posting_file: str = "") -> Posting:
    captured_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    if posting_file:
        try:
            text = Path(posting_file).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PostingError("cannot read the supplied posting file as UTF-8") from exc
        if not text.strip():
            raise PostingError("supplied posting file is empty")
        return Posting(text, captured_at, url, url)

    public_url(url)
    request = Request(url, headers={"User-Agent": "cv-job/0.1 (job posting preservation)",
                                   "Accept": "text/html, text/plain", "Accept-Encoding": "identity"})
    try:
        with build_opener(PublicRedirects()).open(request, timeout=10) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
                raise PostingError("posting response is not HTML or text; supply --posting-file")
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise PostingError("posting response exceeds the 2 MiB capture limit")
            final_url = response.geturl()
            encoding = response.headers.get_content_charset() or "utf-8"
    except HTTPError as exc:
        raise PostingError(f"posting fetch returned HTTP {exc.code}; supply --posting-file") from None
    except (URLError, OSError, TimeoutError) as exc:
        raise PostingError("posting fetch failed; supply --posting-file from the browser") from exc
    try:
        text = raw.decode(encoding, errors="replace")
    except LookupError as exc:
        raise PostingError("posting response has an unsupported encoding") from exc
    if content_type != "text/plain":
        parser = PageText()
        parser.feed(text)
        text = "\n".join(line for part in "".join(parser.parts).splitlines() if (line := " ".join(part.split())))
    if len(text.strip()) < 100:
        raise PostingError("posting response has too little readable text; supply --posting-file from the browser")
    if any(message in text[:1000].lower() for message in
           ("verify you are human", "checking your browser", "enable javascript and cookies", "access denied")):
        raise PostingError("posting site returned an access challenge; supply --posting-file from the browser")
    return Posting(text, captured_at, url, final_url, raw, content_type)
