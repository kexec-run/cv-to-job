#!/usr/bin/env python3
"""Application log for the apply-to-jobs skill.

Data lives in <repo>/private/applications.json and one folder per application
under <repo>/private/applications/<id>/. CLI writes use short flock transactions.

  jobs.py run start --target 10 --objective "..."     refuses an already active run
  jobs.py run end
  jobs.py check --url URL [--company C --title T]     -> {"status": "new" | <existing status>, ...}
  jobs.py add --company C --title T --url URL --site S [--location L] [--status in_progress|skipped]
              [--reason R] [--note N] [--posting-file job.txt]
  jobs.py update --id ID [--status S] [--add-url URL] [--confirmation ...] [--reason ...]
              [--note ...] [--cover-letter PATH] [--resume PATH]
  jobs.py status | list [--status S] [--run R] [--limit N] | report
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

STATUSES = ("in_progress", "review_ready", "applied", "rejected", "skipped", "blocked", "needs_input", "abandoned")
TRACKING_KEYS = {"ref", "source", "sourceid", "gh_src", "lever-source", "src", "trk", "trackingtag"}
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
from cv_job.application_lock import LockBusy, LockUnavailable, application_lock
from cv_job.config import load_config
from cv_job.posting import PostingError, capture_posting


def repo_root() -> Path:
    return REPO_ROOT


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def slug(text: str, limit: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:limit].strip("-") or "x"


def norm_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


# ---------------------------------------------------------------- identity

def split_url(url: str):
    parts = urlsplit((url or "").strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in TRACKING_KEYS and not k.lower().startswith("utm_")]
    return host, path, query


def provider(host: str) -> str:
    if host == "app.joinhandshake.com":
        return "handshake"
    if "greenhouse.io" in host:
        return "greenhouse"
    if host == "jobs.lever.co":
        return "lever"
    if host == "jobs.ashbyhq.com":
        return "ashby"
    if "myworkdayjobs.com" in host or "myworkdaysite.com" in host:
        return "workday"
    if "smartrecruiters.com" in host:
        return "smartrecruiters"
    if "icims.com" in host:
        return "icims"
    return host


def job_key(url: str) -> str:
    """Stable identity for a posting URL: 'provider:id' when a job id is recognizable,
    otherwise the canonical URL (host + path + non-tracking query)."""
    parts = split_url(url)
    if not parts:
        return ""
    host, path, query = parts
    prov = provider(host)
    segs = [s for s in path.split("/") if s]
    q = dict(query)
    jid = ""
    if prov == "handshake":
        m = re.fullmatch(r"/(?:job-search|jobs|public/jobs)/(\d+)(?:/.*)?", path)
        jid = m.group(1) if m else ""
    elif prov == "greenhouse":
        m = re.search(r"/(?:jobs|job_app)/(\d+)(?:/|$)", path)
        jid = m.group(1) if m else (q.get("gh_jid") or q.get("token") or "")
    elif prov in ("lever", "ashby") and len(segs) >= 2:
        jid = segs[1]
    elif prov == "workday":
        for seg in reversed(segs):
            if seg.lower() not in ("job", "apply", "login") and "_" in seg:
                jid = seg.rsplit("_", 1)[-1]
                break
    elif prov == "smartrecruiters" and len(segs) >= 2:
        m = re.match(r"(\d+)", segs[1])
        jid = m.group(1) if m else ""
    elif prov == "icims":
        m = re.search(r"/jobs/(\d+)/", path + "/")
        jid = m.group(1) if m else ""
    if jid:
        if prov in {"workday", "icims"}:
            tenant = host
            if host.endswith("myworkdaysite.com") and "recruiting" in segs:
                index = segs.index("recruiting") + 1
                if index < len(segs):
                    tenant += "/" + segs[index].lower()
            return f"{prov}:{tenant}:{jid.lower()}"
        return f"{prov}:{jid.lower()}"
    if prov == "ashby" and path.endswith("/application"):
        path = path[: -len("/application")]
    if prov == "lever" and path.endswith("/apply"):
        path = path[: -len("/apply")]
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


# ---------------------------------------------------------------- storage

class Log:
    def __init__(self, root: Path, applications_path: Path | None = None,
                 applications_dir: Path | None = None, workspace: Path | None = None):
        self.root = root
        self.workspace = workspace or (root / "private")
        self.path = applications_path or (root / "private" / "applications.json")
        self.folder_root = applications_dir or (root / "private" / "applications")
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
        else:
            self.data = {"active_run": None, "runs": [], "applications": []}

    def save(self) -> None:
        # Production callers hold application_lock across construction + mutation + save.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.data, indent=1, ensure_ascii=False) + "\n"
        fd, name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        tmp = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                if self.path.exists():
                    os.fchmod(stream.fileno(), self.path.stat().st_mode & 0o777)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)

    @property
    def apps(self) -> list:
        return self.data["applications"]

    def get(self, app_id: str) -> dict:
        for a in self.apps:
            if a["id"] == app_id:
                return a
        sys.exit(f"error: no application with id {app_id}")

    def find(self, url: str = "", company: str = "", title: str = ""):
        key = job_key(url) if url else ""
        if key:
            for a in self.apps:
                # Recompute old unscoped keys from saved URLs without rewriting history.
                keys = {job_key(u) for u in a.get("urls", [])}
                if key in keys or (not a.get("urls") and key in a.get("keys", [])):
                    return a, "url"
        if not key and company and title:
            c, t = norm_text(company), norm_text(title)
            for a in self.apps:
                if norm_text(a["company"]) == c and norm_text(a["title"]) == t:
                    return a, "company+title"
        return None, ""

    def active_run(self):
        rid = self.data.get("active_run")
        for r in self.data["runs"]:
            if r["id"] == rid:
                return r
        return None

    def apps_for_run(self, run_id) -> list:
        if run_id is None:
            return list(self.apps)
        run = next((r for r in self.data["runs"] if r["id"] == run_id), {})
        participants = set(run.get("applications", []))
        return [app for app in self.apps if app.get("run") == run_id or app["id"] in participants]


def out(obj) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False))


def owner_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value):
        raise argparse.ArgumentTypeError("owner must be an opaque ID of 1–80 letters, digits, dots, underscores or hyphens")
    return value


def require_owner(record: dict, args) -> None:
    claim = record.get("claim")
    owner = getattr(args, "owner", None)
    if claim is not None:
        if not isinstance(claim, dict) or not claim.get("owner") or claim["owner"] != owner:
            sys.exit("error: application is claimed; supply its assigned --owner, or coordinate a handoff")
    elif owner is not None:
        sys.exit("error: application is not claimed; claim it before updating as a worker")


def cmd_claim(log: Log, a) -> None:
    app = log.get(a.id)
    if app.get("status") in {"applied", "rejected"}:
        sys.exit("error: cannot claim an already submitted application")
    changed = False
    if app.get("claim") is not None:
        require_owner(app, a)
    else:
        app["claim"] = {"owner": a.owner, "claimed_at": now()}
        app["updated"] = now()
        changed = True
    run = log.active_run()
    if run and app["id"] not in run.get("applications", []):
        run.setdefault("applications", []).append(app["id"])
        changed = True
    if changed:
        log.save()
    out({"id": app["id"], "claim": app["claim"]})


def cmd_release(log: Log, a) -> None:
    app = log.get(a.id)
    require_owner(app, a)
    app.pop("claim")
    app["updated"] = now()
    log.save()
    out({"id": app["id"], "claim": None})


# ---------------------------------------------------------------- commands

def cmd_run(log: Log, a) -> None:
    if a.action == "start":
        cur = log.active_run()
        if cur:
            sys.exit("error: a run is already active; resume it instead of starting another")
        run = {"id": datetime.now().strftime("%Y%m%d-%H%M%S-%f"), "target": a.target,
               "objective": a.objective, "started": now(), "status": "active"}
        if getattr(a, "owner", None):
            run["owner"] = a.owner
        log.data["runs"].append(run)
        log.data["active_run"] = run["id"]
        log.save()
        out(run)
    else:
        cur = log.active_run()
        if not cur:
            sys.exit("error: no active run")
        if cur.get("owner") and cur["owner"] != getattr(a, "owner", None):
            sys.exit("error: only the assigned coordinator --owner may end this run")
        cur["ended"] = now()
        cur["status"] = "ended"
        log.data["active_run"] = None
        log.save()
        out(summary(log, cur["id"]))


def cmd_check(log: Log, a) -> None:
    app, how = log.find(a.url, a.company or "", a.title or "")
    if not app:
        out({"status": "new", "key": job_key(a.url)})
        return
    out({"status": app["status"], "id": app["id"], "matched_on": how, "company": app["company"],
         "title": app["title"], "run": app.get("run"), "updated": app["updated"], "claim": app.get("claim")})


def cmd_add(log: Log, a) -> None:
    existing, how = log.find(a.url, a.company, a.title)
    if existing:
        sys.exit(f"error: already logged as {existing['id']} ({existing['status']}, matched on {how}); use update")
    run = log.active_run()
    date = datetime.now().strftime("%Y-%m-%d")
    base = f"{date}_{slug(a.company, 30)}_{slug(a.title, 40)}"
    app_id, n = base, 2
    while (any(x["id"] == app_id for x in log.apps)
           or (log.folder_root / app_id).exists() or (log.folder_root / app_id).is_symlink()):
        app_id, n = f"{base}-{n}", n + 1
    key = job_key(a.url)
    folder = log.folder_root / app_id
    rec = {
        "id": app_id, "run": run["id"] if run else None,
        "company": a.company, "title": a.title, "location": a.location or "",
        "site": (a.site or provider(split_url(a.url)[0]) if split_url(a.url) else a.site or "").lower(),
        "keys": [key] if key else [], "urls": [a.url],
        "status": a.status, "reason": a.reason or "", "confirmation": "",
        "cover_letter": "", "resume": "", "folder": str(folder.relative_to(log.workspace)),
        "created": now(), "updated": now(),
        "history": [{"status": a.status, "at": now(), "note": a.note or a.reason or ""}],
    }
    if getattr(a, "owner", None):
        if a.status in {"applied", "rejected"}:
            sys.exit("error: cannot claim an already submitted application")
        rec["claim"] = {"owner": a.owner, "claimed_at": now()}
    folder.mkdir(parents=True, exist_ok=False)
    rec["posting"] = a.captured_posting.save(folder, a.company, a.title, a.location or "")
    log.apps.append(rec)
    log.save()
    out({"id": app_id, "folder": rec["folder"], "status": a.status, "run": rec["run"], "claim": rec.get("claim")})


def cmd_update(log: Log, a) -> None:
    app = log.get(a.id)
    require_owner(app, a)
    if a.details_file:
        details = json.loads(Path(a.details_file).read_text())
        allowed = {"base", "role_orientation", "answers", "unresolved", "form_check"}
        if not isinstance(details, dict) or set(details) - allowed:
            sys.exit("error: details must contain only base, role_orientation, answers, unresolved, form_check")
        if "answers" in details and not isinstance(details["answers"], dict):
            sys.exit("error: answers must map exact form questions to answers")
        if "unresolved" in details and not isinstance(details["unresolved"], list):
            sys.exit("error: unresolved must be a list")
        stored = app.setdefault("details", {})
        if "answers" in details:
            stored.setdefault("answers", {}).update(details.pop("answers"))
        stored.update(details)
    if a.add_url:
        existing, _ = log.find(a.add_url)
        if existing and existing["id"] != app["id"]:
            sys.exit("error: URL already belongs to another application; coordinate a handoff before continuing")
        key = job_key(a.add_url)
        if key and key not in app["keys"]:
            app["keys"].append(key)
        if a.add_url not in app["urls"]:
            app["urls"].append(a.add_url)
    for field in ("confirmation", "reason", "cover_letter", "resume", "location"):
        val = getattr(a, field, None)
        if val:
            if field in {"cover_letter", "resume"}:
                path = Path(val)
                if path.is_absolute():
                    try:
                        val = str(path.resolve().relative_to(log.workspace.resolve()))
                    except ValueError:
                        pass
                elif path.parts[:2] == ("private", "applications"):
                    val = str(Path(*path.parts[1:]))
            app[field] = val
    if a.status:
        app["status"] = a.status
        app["history"].append({"status": a.status, "at": now(), "note": a.note or a.reason or ""})
    elif a.note:
        app["history"].append({"status": app["status"], "at": now(), "note": a.note})
    app["updated"] = now()
    log.save()
    out({"id": app["id"], "status": app["status"], "keys": app["keys"]})


def cmd_history(log: Log, a) -> None:
    matches = [app for app in log.apps
               if norm_text(app["company"]) == norm_text(a.company)]
    submissions = [{"id": app["id"], "title": app["title"], "at": event["at"]}
                   for app in matches for event in app.get("history", [])
                   if event["status"] == "applied"]
    out({"company": a.company, "submissions": submissions,
         "previously_applied": True if submissions else None,
         "note": "Match the question's timeframe and subsidiaries. No recorded submission is not proof of never applying."})


def summary(log: Log, run_id) -> dict:
    apps = log.apps_for_run(run_id)
    counts = {s: sum(1 for x in apps if x["status"] == s) for s in STATUSES}
    counts["total"] = len(apps)
    return counts


def cmd_status(log: Log, a) -> None:
    run = log.active_run()
    result = {"all_time": summary(log, None)}
    if run:
        s = summary(log, run["id"])
        result["run"] = {**run, **s, "remaining": max(run["target"] - s["applied"], 0)}
    else:
        result["run"] = None
    out(result)


def cmd_list(log: Log, a) -> None:
    apps = log.apps_for_run(a.run)
    if a.status:
        apps = [x for x in apps if x["status"] == a.status]
    apps = apps[-a.limit:] if a.limit else apps
    for x in apps:
        print(f"{x['status']:<12} {x['id']:<60} {x['company']} — {x['title']}"
              + (f"  [{x['reason']}]" if x.get("reason") else ""))
    print(f"({len(apps)} shown)")


def cmd_show(log: Log, a) -> None:
    out(log.get(a.id))


def cmd_report(log: Log, a) -> None:
    run = log.active_run() or (log.data["runs"][-1] if log.data["runs"] else None)
    if not run:
        print("No runs yet.")
        return
    apps = log.apps_for_run(run["id"])
    s = summary(log, run["id"])
    print(f"## Run {run['id']} — {run['objective']}\n")
    print(f"Target {run['target']} · applied {s['applied']} · review ready {s['review_ready']} · "
          f"rejected {s['rejected']} · skipped {s['skipped']} · blocked {s['blocked']} · "
          f"needs input {s['needs_input']} · "
          f"in progress {s['in_progress']}\n")
    for status, label in (("applied", "Applied"), ("rejected", "Rejected"),
                          ("review_ready", "Ready for review"),
                          ("needs_input", "Needs your input"), ("blocked", "Blocked"),
                          ("in_progress", "Still open"), ("skipped", "Skipped")):
        rows = [x for x in apps if x["status"] == status]
        if not rows:
            continue
        print(f"### {label} ({len(rows)})")
        for x in rows:
            extra = x.get("confirmation") if status == "applied" else x.get("reason")
            print(f"- {x['company']} — {x['title']}" + (f": {extra}" if extra else "")
                  + f"  ({x['urls'][0]})")
        print()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=None, help="workspace YAML config")
    p.add_argument("--root", type=Path, default=None, help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("action", choices=["start", "end"])
    r.add_argument("--target", type=int, default=0)
    r.add_argument("--objective", default="")

    c = sub.add_parser("check")
    c.add_argument("--url", required=True)
    c.add_argument("--company")
    c.add_argument("--title")

    ad = sub.add_parser("add")
    for f in ("company", "title", "url"):
        ad.add_argument(f"--{f}", required=True)
    ad.add_argument("--site", default="")
    ad.add_argument("--location", default="")
    ad.add_argument("--status", choices=STATUSES, default="in_progress")
    ad.add_argument("--reason", default="")
    ad.add_argument("--note", default="")
    ad.add_argument("--posting-file", default="", help="use supplied UTF-8 posting text instead of automatic HTTP capture")

    u = sub.add_parser("update")
    u.add_argument("--id", required=True)
    u.add_argument("--status", choices=STATUSES)
    u.add_argument("--add-url")
    u.add_argument("--details-file", help="JSON with base, role_orientation, answers, unresolved, form_check")
    for f in ("confirmation", "reason", "note", "cover-letter", "resume", "location"):
        u.add_argument(f"--{f}")

    claim = sub.add_parser("claim", help="claim an existing unsubmitted application")
    claim.add_argument("--id", required=True)
    release = sub.add_parser("release", help="explicit owner handoff; inspect ambiguous submissions first")
    release.add_argument("--id", required=True)
    for command in (r, ad, u, claim, release):
        command.add_argument("--owner", type=owner_id, required=command in (claim, release),
                             help="unique coordinator/worker ID; required for claimed records")
        command.add_argument("--lock-timeout", type=float, default=10,
                             help="seconds to wait for the application-log transaction lock (default: 10)")

    sub.add_parser("status")
    show = sub.add_parser("show", help="print one complete application record as JSON (read-only)")
    show.add_argument("--id", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--status", choices=STATUSES)
    ls.add_argument("--run")
    ls.add_argument("--limit", type=int, default=0)
    sub.add_parser("report")
    h = sub.add_parser("history")
    h.add_argument("--company", required=True)

    a = p.parse_args(argv)
    try:
        config = load_config(a.config)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    root = (a.root or repo_root()).resolve()
    lock = (application_lock(config.path("applications"), a.lock_timeout)
            if a.cmd in {"run", "add", "update", "claim", "release"} else nullcontext())
    try:
        if a.cmd == "add":
            # Fetch before locking; recheck deduplication inside the transaction.
            snapshot = Log(root, config.path("applications"), config.path("applications_dir"), config.workspace)
            existing, _ = snapshot.find(a.url, a.company, a.title)
            if existing:
                sys.exit(f"error: already logged as {existing['id']}; use show/claim/update")
            a.captured_posting = capture_posting(a.url, a.posting_file)
        with lock:
            # Read only after locking: locking save() alone still loses concurrent changes.
            log = Log(root, config.path("applications"), config.path("applications_dir"), config.workspace)
            {"run": cmd_run, "check": cmd_check, "add": cmd_add, "update": cmd_update,
             "status": cmd_status, "list": cmd_list, "show": cmd_show, "report": cmd_report,
             "history": cmd_history, "claim": cmd_claim, "release": cmd_release}[a.cmd](log, a)
    except PostingError as exc:
        print(f"error: {exc}; no application added", file=sys.stderr)
        return 2
    except LockBusy as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except LockUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("error: application transaction failed; inspect the log before retrying; no lock bypass is allowed",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
