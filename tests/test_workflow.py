"""Regression checks use synthetic facts and never modify candidate/application data."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cv_job import cli
from cv_job.config import (
    REQUIRED_PATHS,
    WorkspaceConfig,
    configured_path_issues,
    load_config,
    resolve_artifact_path,
)
from cv_job.posting import Posting

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


claims = module("claims", "scripts/validate_claims.py")
jobs = module("jobs", "skills/apply-to-jobs/scripts/jobs.py")


@pytest.fixture
def records():
    return {
        "work": {"status": "demonstrated", "master_quote": "Built Linux systems.",
                 "allowed_claims": ["Linux"]},
        "unknown": {"status": "unverified", "master_quote": None,
                    "years": 5, "allowed_claims": ["UnprovenTool"]},
        "listed": {"status": "listed", "master_quote": "ListedTool",
                   "allowed_claims": ["ListedTool"]},
        "confirmed": {"status": "candidate_confirmed", "master_quote": None,
                      "user_confirmation": "I have used ConfirmedTool.",
                      "evidence": ["Candidate-confirmed use; scope unknown."],
                      "allowed_claims": ["ConfirmedTool"],
                      "prohibited_rewrites": [{"phrase": "ConfirmedTool", "scope": "outside_skills"}]},
    }


def resume(tmp_path, title="Official Title", skill="Linux"):
    path = tmp_path / "resume.tex"
    path.write_text("Site Reliability Engineer\n"
                    rf"\worktitle{{{title}}}{{2020 - Present}}" + "\n"
                    "% skills:allowed\n"
                    rf"\item {skill}" + "\n% skills:end\n"
                    r"\item Built Linux systems. % ev:work" + "\n")
    return path


def test_target_headline_allowed_but_employment_title_fixed(tmp_path, records):
    master = "Built Linux systems. ListedTool"
    assert claims.check_file(resume(tmp_path), records, master, ("Official Title",)) == []
    errors = claims.check_file(resume(tmp_path, "Site Reliability Engineer"),
                               records, master, ("Official Title",))
    assert any("employment titles" in error for error in errors)


def test_unverified_skill_rejected_even_with_years_and_allowed_claim(tmp_path, records):
    errors = claims.check_file(resume(tmp_path, skill="UnprovenTool"), records,
                               "Built Linux systems. ListedTool", ("Official Title",))
    assert any("not an allowed claim" in error for error in errors)


def test_listed_skill_allowed_in_resume_skills(tmp_path, records):
    assert claims.check_file(resume(tmp_path, skill="ListedTool"), records,
                             "Built Linux systems. ListedTool", ("Official Title",)) == []


def test_candidate_confirmed_skill_allowed_only_in_resume_skills(tmp_path, records):
    assert claims.check_file(resume(tmp_path, skill="ConfirmedTool"), records,
                             "Built Linux systems. ListedTool", ("Official Title",)) == []
    path = resume(tmp_path)
    path.write_text(path.read_text().replace(
        r"\item Built Linux systems. % ev:work",
        r"\item Used ConfirmedTool in production. % ev:work"))
    errors = claims.check_file(path, records, "Built Linux systems. ListedTool",
                               ("Official Title",))
    assert any("prohibited rewrite" in error for error in errors)


@pytest.mark.parametrize("tool", ["ListedTool", "UnprovenTool", "ConfirmedTool"])
def test_cover_letter_rejects_unsupported_experience(tmp_path, records, tool):
    path = tmp_path / "letter.md"
    path.write_text(f"I operated {tool} in production.")
    assert claims.check_letter(path, records)


def test_letter_keeps_text_after_literal_percent(tmp_path, records):
    path = tmp_path / "letter.md"
    path.write_text("Saved 20% using UnprovenTool.")
    assert claims.check_letter(path, records)
    path.write_text("I built Linux systems. I am applying for Site Reliability Engineer.")
    assert claims.check_letter(path, records) == []


@pytest.mark.parametrize("first,second", [
    ("https://alpha.wd1.myworkdayjobs.com/jobs/job/Role_R123",
     "https://beta.wd1.myworkdayjobs.com/jobs/job/Role_R123"),
    ("https://alpha.icims.com/jobs/123/engineer/job",
     "https://beta.icims.com/jobs/123/engineer/job"),
    ("https://wd1.myworkdaysite.com/recruiting/alpha/jobs/job/Role_R123",
     "https://wd1.myworkdaysite.com/recruiting/beta/jobs/job/Role_R123"),
])
def test_job_identity_is_employer_scoped(first, second):
    assert jobs.job_key(first) != jobs.job_key(second)
    assert jobs.job_key(first) == jobs.job_key(first + "/apply?utm_source=test")


def test_distinct_openings_not_dropped_and_legacy_urls_still_match(tmp_path):
    log = jobs.Log(tmp_path)
    old_url = "https://alpha.wd1.myworkdayjobs.com/jobs/job/Role_R123"
    log.apps.append({"company": "Alpha", "title": "Engineer", "urls": [old_url],
                     "keys": ["workday:r123"]})
    assert log.find(old_url)[0] is log.apps[0]
    assert log.find("https://alpha.wd1.myworkdayjobs.com/jobs/job/Role_R456",
                    "Alpha", "Engineer")[0] is None
    assert log.find("https://beta.wd1.myworkdayjobs.com/jobs/job/Role_R123")[0] is None


def test_history_distinguishes_prepared_from_submitted(tmp_path, capsys):
    log = jobs.Log(tmp_path)
    log.apps.append({"id": "a", "company": "Alpha", "title": "Engineer",
                     "history": [{"status": "review_ready", "at": "2026-09-22"}]})
    jobs.cmd_history(log, SimpleNamespace(company="Alpha"))
    assert json.loads(capsys.readouterr().out)["previously_applied"] is None
    log.apps[0]["history"].append({"status": "applied", "at": "2026-09-23"})
    jobs.cmd_history(log, SimpleNamespace(company="Alpha"))
    assert json.loads(capsys.readouterr().out)["previously_applied"] is True


def test_rejected_status_is_counted(tmp_path):
    log = jobs.Log(tmp_path)
    log.apps.append({"status": "rejected"})
    assert "rejected" in jobs.STATUSES
    assert jobs.summary(log, None)["rejected"] == 1


def test_details_store_answers_without_overwriting_identity(tmp_path):
    log = jobs.Log(tmp_path)
    log.apps.append({"id": "a", "status": "in_progress", "keys": [], "history": []})
    detail_file = tmp_path / "details.json"
    detail_file.write_text(json.dumps({"answers": {"Current city?": "Example"},
                                       "unresolved": [], "form_check": "Compared after upload"}))
    args = SimpleNamespace(id="a", details_file=str(detail_file), add_url=None,
                           status=None, note=None)
    jobs.cmd_update(log, args)
    saved = jobs.Log(tmp_path).get("a")
    assert saved["details"]["answers"] == {"Current city?": "Example"}
    detail_file.write_text('{"answers": {"Notice period?": "30 days"}}')
    jobs.cmd_update(log, args)
    assert jobs.Log(tmp_path).get("a")["details"]["answers"] == {
        "Current city?": "Example", "Notice period?": "30 days"}
    detail_file.write_text('{"id": "overwritten"}')
    with pytest.raises(SystemExit):
        jobs.cmd_update(log, args)
    assert jobs.Log(tmp_path).get("a")["id"] == "a"


def test_sample_workspace_validates_and_uses_configured_titles():
    config_path = ROOT / "sample" / "cv-job.yaml"
    config = load_config(config_path)
    candidate = claims.load_yaml(config.path("candidate"))
    master = next(config.path("master_cv_dir").glob("*.tex")).read_text()
    records = claims.load_yaml(config.path("experience"))["records"]
    assert claims.titles_from_candidate(candidate) == ("Systems Engineer",)
    assert claims.check_ledger(records, master) == []
    assert claims.main(["--config", str(config_path)]) == 0
    assert cli.main(["--config", str(config_path), "validate", "--check-ledger"]) == 0


def test_default_resume_validation_rejects_empty_bases(tmp_path, monkeypatch, capsys):
    config_path = _complete_config_tree(tmp_path / "workspace")
    config = load_config(config_path)
    config.path("master_cv_dir").joinpath("master.tex").write_text("master")
    config.path("experience").write_text("records: {}\n")
    config.path("candidate").write_text("employment: {}\n")
    monkeypatch.setattr(claims, "load_config", lambda _path: config)
    assert claims.main([]) == 1
    assert "no CV TeX files" in capsys.readouterr().err


def test_nested_resume_base_is_found_by_default_validation(tmp_path, monkeypatch, capsys):
    config_path = _complete_config_tree(tmp_path / "workspace")
    config = load_config(config_path)
    config.path("master_cv_dir").joinpath("master.tex").write_text("Built Linux systems.")
    config.path("experience").write_text(json.dumps({"records": {
        "work": {"status": "demonstrated", "master_quote": "Built Linux systems.",
                 "allowed_claims": ["Linux"]},
    }}))
    config.path("candidate").write_text(json.dumps({"employment": {}}))
    nested = config.path("cv_bases_dir") / "nested" / "resume.tex"
    nested.parent.mkdir()
    nested.write_text(r"\item Built Linux systems. % ev:work" + "\n")
    monkeypatch.setattr(claims, "load_config", lambda _path: config)
    assert claims.main([]) == 0
    assert capsys.readouterr().out.strip() == "ok 1 file(s)"


@pytest.mark.parametrize("contents, message", [
    ("not: [valid", "invalid YAML"),
    ("version: 2\nworkspace: .\npaths: {}\n", "unsupported workspace config version"),
    ("version: 1\nworkspace: .\npaths: {}\n", "missing paths"),
])
def test_config_reports_invalid_or_unsupported_files(tmp_path, contents, message):
    config_path = tmp_path / "cv-job.yaml"
    config_path.write_text(contents)
    with pytest.raises(ValueError, match=message):
        load_config(config_path)


def test_config_resolves_paths_relative_to_workspace(tmp_path):
    config_path = ROOT / "sample" / "cv-job.yaml"
    config = load_config(config_path)
    assert config.workspace == config_path.parent.resolve()
    assert config.path("candidate") == (config_path.parent / "candidate.yaml").resolve()


def _complete_config_tree(root):
    files = {"instructions", "candidate", "experience", "preferences", "ats_answers", "applications"}
    raw_paths = {}
    for key in sorted(REQUIRED_PATHS):
        target = root / key
        raw_paths[key] = key
        if key in files:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}\n")
        else:
            target.mkdir(parents=True, exist_ok=True)
    config_path = root.parent / "cv-job.yaml"
    config_path.write_text(json.dumps({"version": 1, "workspace": root.name, "paths": raw_paths}))
    return config_path


def test_configured_path_issues_reports_all_missing_paths_and_workspace(tmp_path):
    config_path = _complete_config_tree(tmp_path / "workspace")
    config = load_config(config_path)
    for path in config.paths.values():
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
    config.workspace.rmdir()
    issues = configured_path_issues(config)
    assert [issue["key"] for issue in issues] == [*sorted(REQUIRED_PATHS), "workspace"]
    assert all(issue["reason"] == "missing" for issue in issues)


def test_configured_path_issues_detects_wrong_types(tmp_path):
    config_path = _complete_config_tree(tmp_path / "workspace")
    config = load_config(config_path)
    for key in ("previews_dir", "templates_dir"):
        config.path(key).rmdir()
        config.path(key).write_text("not a directory")
    issues = configured_path_issues(config)
    assert {issue["key"] for issue in issues} == {"previews_dir", "templates_dir"}
    assert all(issue["reason"] == "wrong_type" for issue in issues)


@pytest.mark.parametrize("key", sorted(REQUIRED_PATHS))
def test_each_configured_path_rejects_wrong_type(tmp_path, key):
    config_path = _complete_config_tree(tmp_path / "workspace")
    config = load_config(config_path)
    path = config.path(key)
    if path.is_dir():
        path.rmdir()
        path.write_text("wrong type")
    else:
        path.unlink()
        path.mkdir()
    issue, = configured_path_issues(config)
    assert issue["key"] == key
    assert issue["reason"] == "wrong_type"


def test_load_config_can_skip_path_checks_for_audit(tmp_path):
    config_path = tmp_path / "cv-job.yaml"
    config_path.write_text(json.dumps({
        "version": 1, "workspace": "workspace", "paths": {key: key for key in REQUIRED_PATHS},
    }))
    with pytest.raises(FileNotFoundError):
        load_config(config_path)
    config = load_config(config_path, check_paths=False)
    assert len(configured_path_issues(config)) == len(REQUIRED_PATHS) + 1


def test_cli_and_compatibility_commands_return_two_for_config_errors(tmp_path, capsys):
    config_path = tmp_path / "cv-job.yaml"
    config_path.write_text("version: 1\nworkspace: .\npaths: {}\n")
    assert cli.main(["--config", str(config_path), "validate"]) == 2
    assert "error:" in capsys.readouterr().err
    assert claims.main(["--config", str(config_path)]) == 2
    assert "error:" in capsys.readouterr().err
    assert jobs.main(["--config", str(config_path), "list"]) == 2
    assert "error:" in capsys.readouterr().err


def test_initialize_copies_sample_atomically_and_does_not_modify_source(tmp_path, monkeypatch):
    sample = tmp_path / "sample"
    sample.mkdir()
    (sample / "cv-job.yaml").write_text("sample config")
    (sample / "applications.json").write_text('{"applications": []}\n')
    before = {p.relative_to(sample): p.read_bytes() for p in sample.rglob("*") if p.is_file()}
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    assert cli.initialize() == 0
    assert not (tmp_path / "private.migrating").exists()
    assert {p.relative_to(sample): p.read_bytes() for p in sample.rglob("*") if p.is_file()} == before
    assert (tmp_path / "private" / "applications.json").read_text() == '{"applications": []}\n'


@pytest.mark.parametrize("existing", ["private", "private.migrating"])
@pytest.mark.parametrize("kind", ["empty_directory", "personal_directory", "file", "symlink", "broken_symlink"])
def test_initialize_refuses_existing_destination_or_staging(tmp_path, monkeypatch, capsys, existing, kind):
    (tmp_path / "sample").mkdir()
    path = tmp_path / existing
    target = tmp_path / "personal-target"
    if kind in {"empty_directory", "personal_directory"}:
        path.mkdir()
        if kind == "personal_directory":
            (path / "personal.txt").write_bytes(b"preserve personal data\x00")
            # Deliberately no cv-job.yaml: missing config must not permit initialization.
    elif kind == "file":
        path.write_bytes(b"preserve existing file\x00")
    else:
        if kind == "symlink":
            target.mkdir()
            (target / "personal.txt").write_bytes(b"preserve symlink target\x00")
        path.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)

    def unexpected_copy(*args, **kwargs):
        pytest.fail("initialization must refuse conflicts before copying")

    monkeypatch.setattr(cli.shutil, "copytree", unexpected_copy)
    assert cli.initialize() == 2
    assert str(path) in capsys.readouterr().err
    if kind in {"empty_directory", "personal_directory"}:
        assert path.is_dir()
        assert sorted(p.name for p in path.iterdir()) == (["personal.txt"] if kind == "personal_directory" else [])
        if kind == "personal_directory":
            assert (path / "personal.txt").read_bytes() == b"preserve personal data\x00"
    elif kind == "file":
        assert path.read_bytes() == b"preserve existing file\x00"
    else:
        assert path.is_symlink()
        assert path.readlink() == target
        if kind == "symlink":
            assert (target / "personal.txt").read_bytes() == b"preserve symlink target\x00"
        else:
            assert not target.exists()
    other = tmp_path / ("private.migrating" if existing == "private" else "private")
    assert not other.exists() and not other.is_symlink()


def test_workspace_audit_supports_legacy_paths_without_mutation(tmp_path, capsys):
    workspace = tmp_path / "private"
    app_dir = workspace / "applications" / "old-app"
    app_dir.mkdir(parents=True)
    (app_dir / "resume.pdf").write_bytes(b"fixture")
    config = WorkspaceConfig(
        config_path=workspace / "cv-job.yaml",
        workspace=workspace,
        paths={"applications": workspace / "applications.json",
               "applications_dir": workspace / "applications"},
        repo_root=tmp_path,
    )
    legacy = {"active_run": None, "runs": [], "applications": [{
        "id": "old-app", "folder": "private/applications/old-app",
        "resume": "private/applications/old-app/resume.pdf", "cover_letter": "",
    }]}
    (workspace / "applications.json").write_text(json.dumps(legacy))
    assert cli.audit_workspace(config) == 0
    assert json.loads((workspace / "applications.json").read_text()) == legacy
    findings = json.loads(capsys.readouterr().out)["findings"]
    assert [(item["field"], item["severity"]) for item in findings] == [
        ("folder", "info"), ("resume", "info")]


@pytest.mark.parametrize("bad_value, expected_message", [
    (None, "top-level value must be a mapping"),
    ([], "top-level value must be a mapping"),
    ({"runs": [], "applications": {}}, "applications must be a list"),
    ({"runs": {}, "applications": []}, "runs must be a list"),
    ({"runs": [{}], "applications": []}, "run record must have a non-empty string id"),
    ({"runs": [], "applications": [None]}, "application record must be a mapping"),
    ({"runs": [], "applications": [{"id": "a", "resume": 4}]}, "invalid types or values"),
])
def test_audit_structures_malformed_application_logs(tmp_path, capsys, bad_value, expected_message):
    workspace = tmp_path / "private"
    workspace.mkdir()
    (workspace / "applications").mkdir()
    config = WorkspaceConfig(
        config_path=workspace / "cv-job.yaml", workspace=workspace,
        paths={"applications": workspace / "applications.json",
               "applications_dir": workspace / "applications"}, repo_root=tmp_path,
    )
    config.path("applications").write_text(json.dumps(bad_value))
    assert cli.audit_workspace(config) == 1
    report = json.loads(capsys.readouterr().out)
    assert any(item["type"] == "invalid_applications_log"
               and expected_message in item["message"] for item in report["findings"])
    assert all(item["severity"] == "error" for item in report["findings"])


def test_audit_reports_invalid_utf8_application_log(tmp_path, capsys):
    workspace = tmp_path / "private"
    workspace.mkdir()
    (workspace / "applications").mkdir()
    config = WorkspaceConfig(
        config_path=workspace / "cv-job.yaml", workspace=workspace,
        paths={"applications": workspace / "applications.json",
               "applications_dir": workspace / "applications"}, repo_root=tmp_path,
    )
    config.path("applications").write_bytes(b"\xff")
    assert cli.audit_workspace(config) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["findings"][0]["type"] == "invalid_applications_log"
    assert report["findings"][0]["severity"] == "error"


def test_audit_legacy_missing_attachment_reports_info_and_error(tmp_path, capsys):
    workspace = tmp_path / "private"
    app_dir = workspace / "applications" / "old-app"
    app_dir.mkdir(parents=True)
    config = WorkspaceConfig(
        config_path=workspace / "cv-job.yaml", workspace=workspace,
        paths={"applications": workspace / "applications.json",
               "applications_dir": workspace / "applications"}, repo_root=tmp_path,
    )
    record = {"id": "old-app", "status": "applied",
              "folder": "private/applications/old-app",
              "resume": "private/applications/old-app/missing.pdf", "cover_letter": ""}
    other_dir = workspace / "applications" / "other-app"
    other_dir.mkdir(parents=True)
    (other_dir / "resume.pdf").write_bytes(b"fixture")
    cross_folder = {"id": "cross-app", "status": "applied",
                    "folder": "private/applications/old-app",
                    "resume": "private/applications/other-app/resume.pdf", "cover_letter": ""}
    config.path("applications").write_text(json.dumps({"runs": [], "applications": [record, cross_folder]}))
    before = config.path("applications").read_bytes()
    assert cli.audit_workspace(config) == 1
    report = json.loads(capsys.readouterr().out)
    assert [(item["type"], item["severity"]) for item in report["findings"]] == [
        ("legacy_reference", "info"), ("legacy_reference", "info"),
        ("missing_attachment", "error"), ("legacy_reference", "info"),
        ("legacy_reference", "info"), ("cross_folder_attachment", "error")]
    assert config.path("applications").read_bytes() == before


def test_audit_keeps_workspace_relative_paths_out_of_legacy_findings(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    app_dir = workspace / "applications" / "new-app"
    app_dir.mkdir(parents=True)
    (app_dir / "resume.pdf").write_bytes(b"fixture")
    config = WorkspaceConfig(
        config_path=workspace / "cv-job.yaml", workspace=workspace,
        paths={"applications": workspace / "applications.json",
               "applications_dir": workspace / "applications"}, repo_root=tmp_path,
    )
    record = {"id": "new-app", "status": "applied", "folder": "applications/new-app",
              "resume": "applications/new-app/resume.pdf", "cover_letter": ""}
    config.path("applications").write_text(json.dumps({"runs": [], "applications": [record]}))
    assert cli.audit_workspace(config) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["findings"] == []


def test_audit_invalid_json_is_a_structured_error(tmp_path, capsys):
    workspace = tmp_path / "private"
    workspace.mkdir()
    (workspace / "applications").mkdir()
    config = WorkspaceConfig(
        config_path=workspace / "cv-job.yaml", workspace=workspace,
        paths={"applications": workspace / "applications.json",
               "applications_dir": workspace / "applications"}, repo_root=tmp_path,
    )
    config.path("applications").write_text("{")
    assert cli.audit_workspace(config) == 1
    report = json.loads(capsys.readouterr().out)
    assert len(report["findings"]) == 1
    assert report["findings"][0]["severity"] == "error"
    assert report["findings"][0]["type"] == "invalid_applications_log"


def test_artifact_resolver_handles_workspace_and_legacy_paths(tmp_path):
    workspace = tmp_path / "private"
    legacy = tmp_path / "private" / "applications" / "old" / "resume.pdf"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"fixture")
    config = WorkspaceConfig(tmp_path / "private" / "cv-job.yaml", workspace, {}, tmp_path)
    assert resolve_artifact_path("private/applications/old/resume.pdf", config) == legacy
    assert resolve_artifact_path("applications/old/resume.pdf", config) == legacy


def test_configured_application_write_uses_workspace_relative_paths(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    log = jobs.Log(tmp_path, workspace / "applications.json", workspace / "applications", workspace)
    args = SimpleNamespace(
        url="https://jobs.example.test/123", company="Example Org", title="Engineer",
        location="Example City", site="", status="in_progress", reason="", note="",
        posting_file="", captured_posting=Posting("Fictional posting.", "2026-10-16T00:00:00+00:00",
                                                   "https://jobs.example.test/123", "https://jobs.example.test/123"),
    )
    jobs.cmd_add(log, args)
    saved = jobs.Log(tmp_path, workspace / "applications.json", workspace / "applications", workspace)
    record = saved.apps[0]
    assert record["folder"].startswith("applications/")
    assert (workspace / record["folder"]).is_dir()
    assert json.loads((workspace / "applications.json").read_text())["applications"][0]["id"] == record["id"]
    capsys.readouterr()


def test_new_attachment_updates_store_workspace_relative_paths(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = jobs.Log(tmp_path, workspace / "applications.json", workspace / "applications", workspace)
    log.apps.append({"id": "example-app", "status": "in_progress", "keys": [], "urls": [],
                     "history": [], "updated": ""})
    args = SimpleNamespace(id="example-app", details_file=None, add_url=None, status=None, note=None,
                           confirmation=None, reason=None, cover_letter=None,
                           resume="private/applications/example-app/resume.pdf", location=None)
    jobs.cmd_update(log, args)
    assert log.apps[0]["resume"] == "applications/example-app/resume.pdf"
    capsys.readouterr()


def test_summary_counts_every_application_status(tmp_path):
    log = jobs.Log(tmp_path)
    log.apps.extend({"status": status} for status in jobs.STATUSES)
    counts = jobs.summary(log, None)
    assert counts["total"] == len(jobs.STATUSES)
    assert all(counts[status] == 1 for status in jobs.STATUSES)


def test_public_privacy_boundary_is_declared_and_sample_has_no_pdfs():
    assert "/private/" in (ROOT / ".gitignore").read_text()
    assert not list((ROOT / "sample").rglob("*.pdf"))


def test_sample_resume_render_is_exactly_one_page(tmp_path):
    import pypdfium2

    output = tmp_path / "sample-resume.pdf"
    result = cli.main([
        "--config", str(ROOT / "sample" / "cv-job.yaml"), "render", "tex",
        "--in", "sample/cv_bases/example.tex", "--out", str(output),
    ])
    assert result == 0
    document = pypdfium2.PdfDocument(str(output))
    try:
        assert len(document) == 1
    finally:
        document.close()
