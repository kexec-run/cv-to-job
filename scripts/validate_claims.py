"""Structural and known-claim checks; not a semantic proof of truthful prose.

  uv run scripts/validate_claims.py --config sample/cv-job.yaml --check-ledger
  uv run scripts/validate_claims.py --config sample/cv-job.yaml --hashes
  uv run scripts/validate_claims.py --config sample/cv-job.yaml sample/cv_bases/example.tex
  uv run scripts/validate_claims.py --config sample/cv-job.yaml scripts/fixtures/bad_claim.tex

Every \\item outside % skills:allowed ... % skills:end must carry % ev:<id>.
The id must be demonstrated or quantified, and its master_quote must be an
exact substring of the master TeX. Prohibited rewrites fail the file.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cv_job.config import load_config

BULLET_STATUSES = {"demonstrated", "quantified"}
SKILL_ONLY_STATUSES = {"listed", "candidate_confirmed"}
EV_RE = re.compile(r"(?<!\\)%\s*ev:([a-z][a-z0-9_.]*(?:,[a-z][a-z0-9_.]*)*)")
ITEM_END_RE = re.compile(
    r"\\(?:item|workheading|cvsection|projectheading|worktitle)\b|\\end\{itemize\}"
)


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        sys.exit(f"error: {path} did not parse to a mapping")
    return data


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strip_comments(text: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", text)


def norm(text: str) -> str:
    text = strip_comments(text)
    text = text.replace(r"\%", "%").replace(r"\&", "&")
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def has_phrase(haystack: str, phrase: str) -> bool:
    needle = norm(phrase)
    if not needle:
        return False
    return re.search(
        r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])",
        haystack,
    ) is not None


def skills_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    start = 0
    while True:
        i = text.find("% skills:allowed", start)
        if i < 0:
            return spans
        j = text.find("% skills:end", i)
        if j < 0:
            sys.exit("error: % skills:allowed without % skills:end")
        spans.append((i, j + len("% skills:end")))
        start = j + len("% skills:end")


def in_spans(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= index < b for a, b in spans)


def drop_spans(text: str, spans: list[tuple[int, int]]) -> str:
    out = []
    cursor = 0
    for a, b in spans:
        out.append(text[cursor:a])
        cursor = b
    out.append(text[cursor:])
    return "".join(out)


def skill_tokens(item_body: str) -> list[str]:
    text = strip_comments(item_body)
    text = text.replace(r"\&", "&")
    text = re.sub(r"\\textbf\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = text.replace("{", "").replace("}", "")
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    tokens: list[str] = []
    for part in parts:
        part = part.strip()
        if ":" in part:
            part = part.split(":")[-1].strip()
        inner = re.findall(r"\(([^)]*)\)", part)
        outer = re.sub(r"\([^)]*\)", "", part).strip()
        if outer:
            tokens.append(outer)
        for group in inner:
            for token in group.split(","):
                token = token.strip()
                if token:
                    tokens.append(token)
    return tokens


def item_spans(text: str) -> list[tuple[int, int]]:
    starts = [m.start() for m in re.finditer(r"\\item\b", text)]
    spans = []
    for i, start in enumerate(starts):
        rest = text[start + len("\\item"):]
        nxt = ITEM_END_RE.search(rest)
        end = start + len("\\item") + (nxt.start() if nxt else len(rest))
        if i + 1 < len(starts):
            end = min(end, starts[i + 1])
        spans.append((start, end))
    return spans


def check_ledger(records: dict, master: str) -> list[str]:
    errors = []
    for key, rec in records.items():
        if not isinstance(rec, dict):
            errors.append(f"{key}: record is not a mapping")
            continue
        status = rec.get("status")
        quote = rec.get("master_quote")
        if status in BULLET_STATUSES or status == "listed":
            if not isinstance(quote, str) or not quote:
                errors.append(f"{key}: {status} record needs master_quote")
            elif quote not in master:
                errors.append(f"{key}: master_quote is not in the master CV")
        elif status == "unverified":
            if quote not in (None, ""):
                errors.append(f"{key}: unverified record must not carry master_quote")
        elif status == "candidate_confirmed":
            if quote not in (None, ""):
                errors.append(f"{key}: candidate_confirmed record must not carry master_quote")
            if not isinstance(rec.get("user_confirmation"), str) or not rec["user_confirmation"].strip():
                errors.append(f"{key}: candidate_confirmed record needs user_confirmation")
            if not rec.get("evidence") or not rec.get("allowed_claims"):
                errors.append(f"{key}: candidate_confirmed record needs evidence and allowed_claims")
        else:
            errors.append(f"{key}: unknown status {status!r}")
    return errors


def check_file(path: Path, records: dict, master: str, titles: tuple[str, ...]) -> list[str]:
    text = path.read_text()
    errors = []
    spans = skills_spans(text)
    allowed = set()
    for rec in records.values():
        if rec.get("status") not in BULLET_STATUSES | SKILL_ONLY_STATUSES:
            continue
        for claim in rec.get("allowed_claims") or []:
            allowed.add(claim)

    for start, end in item_spans(text):
        if in_spans(start, spans):
            for token in skill_tokens(text[start:end]):
                if token not in allowed:
                    errors.append(f"{path.name}: skills token {token!r} is not an allowed claim")
            continue
        body = text[start:end]
        found = EV_RE.findall(body)
        if not found:
            snippet = norm(body)[:80]
            errors.append(f"{path.name}: item has no % ev: id ({snippet})")
            continue
        ids = []
        for group in found:
            ids.extend(group.split(","))
        for ev in ids:
            rec = records.get(ev)
            if rec is None:
                errors.append(f"{path.name}: unknown evidence id {ev}")
                continue
            if rec.get("status") not in BULLET_STATUSES:
                errors.append(f"{path.name}: {ev} is {rec.get('status')}, not bullet evidence")
                continue
            quote = rec.get("master_quote")
            if not isinstance(quote, str) or quote not in master:
                errors.append(f"{path.name}: {ev} master_quote is missing from the master CV")

    document = norm(text)
    outside = norm(drop_spans(text, spans))
    for key, rec in records.items():
        for rule in rec.get("prohibited_rewrites") or []:
            phrase = rule.get("phrase") if isinstance(rule, dict) else rule
            scope = rule.get("scope", "document") if isinstance(rule, dict) else "document"
            haystack = document if scope == "document" else outside
            if phrase and has_phrase(haystack, phrase):
                errors.append(f"{path.name}: prohibited rewrite from {key}: {phrase}")

    visible = strip_comments(text)
    employment_titles = tuple(re.findall(r"\\worktitle\s*\{([^{}]+)\}", visible))
    if employment_titles != titles:
        errors.append(f"{path.name}: employment titles must be {titles!r}; got {employment_titles!r}")
    return errors


def check_letter(path: Path, records: dict) -> list[str]:
    """Letters have no skills-only area. Review all other facts against the resume."""
    document = re.sub(r"\s+", " ", path.read_text()).strip().lower()
    errors = []
    for key, rec in records.items():
        phrases = [rule.get("phrase") if isinstance(rule, dict) else rule
                   for rule in rec.get("prohibited_rewrites") or []]
        if rec.get("status") in {"listed", "candidate_confirmed", "unverified"}:
            phrases.extend(rec.get("allowed_claims") or [])
        for phrase in set(filter(None, phrases)):
            # Normalize the rule, not Markdown: a literal percent is not a TeX comment.
            if has_phrase(document, phrase):
                errors.append(f"{path.name}: unsupported/prohibited letter phrase from {key}: {phrase}")
    return errors


def ledger_questions(records: dict) -> list[dict]:
    """Surface existing ambiguities once without upgrading facts or blocking other skills."""
    return [{"id": key, "status": rec.get("status"), "years": rec.get("years"),
             "question": "Confirm personal hands-on scope and duration before using in ATS answers."}
            for key, rec in records.items()
            if rec.get("status") in {"listed", "candidate_confirmed", "unverified"}
            and (rec.get("years") is not None or rec.get("allowed_claims"))]


def titles_from_candidate(candidate: dict) -> tuple[str, ...]:
    found = []
    for record in candidate.get("employment", {}).values():
        if record.get("title_mutation_allowed") is False:
            found.extend(row["title"] for row in record.get("titles", []) if row.get("title"))
    return tuple(found)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--check-ledger", action="store_true")
    parser.add_argument("--hashes", action="store_true")
    parser.add_argument("--cover-letter", action="store_true")
    parser.add_argument("--audit-ledger", action="store_true")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    check_only, hashes, files = args.check_ledger, args.hashes, args.files
    if args.cover_letter and not files:
        parser.error("--cover-letter requires a Markdown file")
    try:
        config = load_config(args.config)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    master_files = sorted(config.path("master_cv_dir").glob("*.tex"))
    if len(master_files) != 1:
        sys.exit(f"error: expected one master CV TeX file in {config.path('master_cv_dir')}, found {len(master_files)}")
    master_path = master_files[0]
    ledger_path = config.path("experience")
    records = load_yaml(ledger_path).get("records")
    if not isinstance(records, dict):
        sys.exit("error: experience.yaml has no records mapping")
    master = master_path.read_text()
    titles = titles_from_candidate(load_yaml(config.path("candidate")))
    errors = check_ledger(records, master)
    if args.audit_ledger:
        print(yaml.safe_dump({"questions": ledger_questions(records)}, sort_keys=False))
        for err in errors:
            print(err, file=sys.stderr)
        return 1 if errors else 0
    if hashes:
        print(f"master_sha256: {sha256(master_path)}")
        print(f"experience_sha256: {sha256(ledger_path)}")
    if check_only or hashes and not files:
        for err in errors:
            print(err, file=sys.stderr)
        if not errors and check_only:
            print(f"ledger ok ({len(records)} records)")
        return 1 if errors else 0
    if not files:
        files = sorted(config.path("cv_bases_dir").glob("**/*.tex"))
        if not files:
            print(f"error: no CV TeX files found under {config.path('cv_bases_dir')}", file=sys.stderr)
            return 1
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1
    file_errors: list[str] = []
    for path in files:
        file_errors.extend(check_letter(path, records) if args.cover_letter
                           else check_file(path, records, master, titles))
    for err in file_errors:
        print(err, file=sys.stderr)
    if file_errors:
        return 1
    print(f"ok {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
