"""Command-line entry point for cv-job."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

from cv_job.config import (
    REPO_ROOT,
    WorkspaceConfig,
    configured_path_issues,
    is_legacy_artifact_path,
    load_config,
    resolve_artifact_path,
)
from cv_job.settings import settings_issues


def _load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load compatibility script {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def initialize() -> int:
    destination = REPO_ROOT / "private"
    staging = REPO_ROOT / "private.migrating"
    sample = REPO_ROOT / "sample"
    if destination.exists() or destination.is_symlink():
        print(f"error: refusing to overwrite existing workspace path: {destination}; "
              "inspect and resume or repair it instead", file=sys.stderr)
        return 2
    if staging.exists() or staging.is_symlink():
        print(f"error: refusing to overwrite staging path: {staging}; inspect it before retrying", file=sys.stderr)
        return 2
    if not sample.is_dir():
        print(f"error: sample workspace is missing: {sample}", file=sys.stderr)
        return 2
    try:
        shutil.copytree(sample, staging)
        source = sorted(p.relative_to(sample) for p in sample.rglob("*") if p.is_file())
        copied = sorted(p.relative_to(staging) for p in staging.rglob("*") if p.is_file())
        if source != copied:
            raise OSError("sample copy file list does not match")
        for rel in source:
            if hashlib.sha256((sample / rel).read_bytes()).digest() != hashlib.sha256((staging / rel).read_bytes()).digest():
                raise OSError(f"sample copy hash mismatch: {rel}")
        staging.rename(destination)
    except OSError as exc:
        print(f"error: initialization stopped; staging data is at {staging}: {exc}", file=sys.stderr)
        return 1
    print(f"initialized private workspace: {destination}")
    print(f"config: {destination / 'cv-job.yaml'}")
    return 0


def audit_workspace(config: WorkspaceConfig) -> int:
    path_issues = configured_path_issues(config)
    missing = [issue["path"] for issue in path_issues if issue["reason"] == "missing"]
    findings: list[dict] = []

    def add_error(finding: dict) -> None:
        findings.append({"severity": "error", **finding})

    for issue in path_issues:
        add_error({"type": "invalid_configured_path", **issue})
    for issue in settings_issues(config):
        add_error(issue)

    log_path = config.path("applications")
    if log_path.is_file():
        parse_error = False
        try:
            data = json.loads(log_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            add_error({"type": "invalid_applications_log", "message": str(exc)})
            data = None
            parse_error = True

        applications = data.get("applications") if isinstance(data, dict) else None
        runs = data.get("runs") if isinstance(data, dict) else None
        invalid_top_level = (data is None and not parse_error) or (
            data is not None and not isinstance(data, dict)
        )
        if invalid_top_level:
            add_error({"type": "invalid_applications_log", "message": "top-level value must be a mapping"})
        elif isinstance(data, dict) and not isinstance(applications, list):
            add_error({"type": "invalid_applications_log", "field": "applications",
                       "message": "applications must be a list"})
        elif isinstance(data, dict) and not isinstance(runs, list):
            add_error({"type": "invalid_applications_log", "field": "runs",
                       "message": "runs must be a list"})
        elif isinstance(data, dict):
            for index, run in enumerate(runs):
                if not isinstance(run, dict):
                    add_error({"type": "invalid_applications_log", "field": "runs",
                               "index": index, "message": "run record must be a mapping"})
                elif not isinstance(run.get("id"), str) or not run.get("id"):
                    add_error({"type": "invalid_applications_log", "field": "runs",
                               "index": index, "message": "run record must have a non-empty string id"})
            for index, app in enumerate(applications):
                if not isinstance(app, dict):
                    add_error({"type": "invalid_applications_log", "field": "applications",
                               "index": index, "message": "application record must be a mapping"})
                    continue
                app_id = app.get("id", "<unknown>")
                invalid_fields = [
                    field for field in ("id", "folder", "resume", "cover_letter", "status")
                    if field in app and not isinstance(app[field], str)
                ]
                if not isinstance(app.get("id"), str) or not app.get("id"):
                    invalid_fields.append("id")
                if invalid_fields:
                    add_error({"type": "invalid_applications_log", "id": app_id,
                               "field": sorted(set(invalid_fields)),
                               "message": "application fields have invalid types or values"})
                    continue
                _audit_application(app, app_id, config, findings, add_error)

    result = {
        "workspace": str(config.workspace),
        "missing_configured_paths": missing,
        "configured_path_issues": path_issues,
        "findings": findings,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if path_issues or any(item.get("severity") == "error" for item in findings) else 0


def _audit_application(app: dict, app_id: str, config: WorkspaceConfig,
                       findings: list[dict], add_error) -> None:
    folder_value = app.get("folder", "")
    folder = resolve_artifact_path(folder_value, config) if folder_value else config.path("applications_dir") / app_id
    has_attachment = any(app.get(field) for field in ("resume", "cover_letter"))
    folder_expected = app.get("status") in {"in_progress", "review_ready", "applied"} or has_attachment
    if folder_expected and not folder.exists():
        add_error({"type": "missing_folder", "id": app_id, "path": str(folder)})
    if folder_value and is_legacy_artifact_path(folder_value):
        findings.append({"type": "legacy_reference", "severity": "info", "id": app_id,
                         "field": "folder", "value": folder_value, "path": str(folder)})
    for field in ("resume", "cover_letter"):
        value = app.get(field)
        if not value:
            continue
        path = resolve_artifact_path(value, config)
        if is_legacy_artifact_path(value):
            findings.append({"type": "legacy_reference", "severity": "info", "id": app_id,
                             "field": field, "value": value, "path": str(path)})
        if not path.exists():
            add_error({"type": "missing_attachment", "id": app_id, "field": field, "path": str(path)})
        elif folder.exists() and folder.resolve() not in path.resolve().parents:
            add_error({"type": "cross_folder_attachment", "id": app_id, "field": field, "path": str(path)})


def run_script(script: Path, args: list[str], config: WorkspaceConfig) -> int:
    if script.name == "validate_claims.py":
        module = _load_script("cv_job_validate_claims", script)
        return module.main(["--config", str(config.config_path), *args])
    if script.name == "jobs.py":
        module = _load_script("cv_job_jobs", script)
        return module.main(["--config", str(config.config_path), *args])
    proc = subprocess.run([sys.executable, str(script), *args], cwd=REPO_ROOT, check=False)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cv-job")
    parser.add_argument("--config", type=Path, default=None, help="workspace YAML config (default: private/cv-job.yaml)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="atomically initialize private/ from sample/")
    validate = sub.add_parser("validate", help="validate the configured experience ledger and CV bases")
    validate.add_argument("files", nargs="*", type=Path)
    validate.add_argument("--check-ledger", action="store_true")
    validate.add_argument("--hashes", action="store_true")
    validate.add_argument("--cover-letter", action="store_true")
    validate.add_argument("--audit-ledger", action="store_true")
    sub.add_parser("audit-workspace", help="check configured files and application attachments")
    apps = sub.add_parser("applications", help="manage the application log")
    apps.add_argument("args", nargs=argparse.REMAINDER)
    render = sub.add_parser("render", help="render resume, cover letter, or TeX source")
    render.add_argument("kind", choices=["resume", "cover-letter", "tex"])
    render.add_argument("args", nargs=argparse.REMAINDER)
    parsed = parser.parse_args(argv)
    if parsed.command == "init":
        return initialize()
    try:
        config = load_config(parsed.config, check_paths=parsed.command != "audit-workspace")
    except (FileNotFoundError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if parsed.command == "validate":
        issues = settings_issues(config)
        if issues:
            print(json.dumps({"settings_issues": issues}, indent=2), file=sys.stderr)
            return 1
        args = [flag for flag, enabled in (
            ("--check-ledger", parsed.check_ledger), ("--hashes", parsed.hashes),
            ("--cover-letter", parsed.cover_letter), ("--audit-ledger", parsed.audit_ledger),
        ) if enabled]
        args.extend(str(path) for path in parsed.files)
        return run_script(REPO_ROOT / "scripts" / "validate_claims.py", args, config)
    if parsed.command == "audit-workspace":
        return audit_workspace(config)
    if parsed.command == "applications":
        script = REPO_ROOT / "skills" / "apply-to-jobs" / "scripts" / "jobs.py"
        return run_script(script, parsed.args, config)
    script_name = {
        "resume": "render_resume.py",
        "cover-letter": "render_cover_letter.py",
        "tex": "render_tex.py",
    }[parsed.kind]
    if parsed.kind == "tex":
        script = REPO_ROOT / "scripts" / script_name
    else:
        script = REPO_ROOT / "skills" / "apply-to-jobs" / "scripts" / script_name
    return run_script(script, parsed.args, config)


if __name__ == "__main__":
    raise SystemExit(main())
