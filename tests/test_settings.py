import json
import shutil
from pathlib import Path

import pytest
import yaml

from cv_job import cli
from cv_job.config import load_config
from cv_job.settings import settings_issues

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "workspace"
    shutil.copytree(ROOT / "sample", root)
    return load_config(root / "cv-job.yaml")


@pytest.mark.parametrize("file_key,data,field", [
    ("preferences", {"submission": "automatic"}, "submission"),
    ("preferences", {"remote": "maybe"}, "remote"),
    ("preferences", {"job_kinds": {"accepted": ["full_time"], "excluded": ["full_time"]}}, "job_kinds"),
    ("preferences", {"job_kinds": {"accepted": ["full_time", "full_time"]}}, "job_kinds.accepted"),
    ("preferences", {"job_kinds": {"accepted": ["freelance"]}}, "job_kinds.accepted"),
    ("preferences", {"job_kinds": {"accepted": "full_time"}}, "job_kinds.accepted"),
    ("preferences", {"locations": {"countries": [None]}}, "locations.countries"),
    ("preferences", {"salary": {"minimum": True}}, "salary.minimum"),
    ("preferences", {"salary": {"minimum": float("inf")}}, "salary.minimum"),
    ("preferences", {"salary": {"minimum": -1}}, "salary.minimum"),
    ("preferences", {"salary": {"minimum": 100}}, "salary"),
    ("preferences", {"salary": {"currency": "dollars"}}, "salary.currency"),
    ("preferences", {"salary": {"period": "weekly"}}, "salary.period"),
    ("preferences", {"notice_period_days": True}, "notice_period_days"),
    ("preferences", {"notice_period_days": -2}, "notice_period_days"),
    ("preferences", {"salary": []}, "salary"),
    ("ats_answers", {"answers": []}, "answers"),
    ("ats_answers", {"demographics": {"gender": "guess"}}, "demographics.gender"),
    ("ats_answers", {"consent": {"marketing": True}}, "consent.marketing"),
    ("ats_answers", {"consent": {"combined_or_unclear_consent": "accept"}}, "consent.combined_or_unclear_consent"),
    ("ats_answers", {"unknown_required_answer": "guess"}, "unknown_required_answer"),
    ("ats_answers", {"work_authorization": {"by_country": {"Exampleland": {"authorized": "yes"}}}},
     "work_authorization.by_country"),
])
def test_settings_reject_invalid_documented_values(workspace, file_key, data, field):
    workspace.path(file_key).write_text(yaml.safe_dump(data))
    assert field in [issue["field"] for issue in settings_issues(workspace)]


def test_valid_sample_and_legacy_choices_are_supported(workspace):
    assert settings_issues(workspace) == []
    workspace.path("preferences").write_text(yaml.safe_dump({
        "remote": True, "onsite": "accept_if_posting_requires", "relocation": {"example_city": "ask"},
        "private_extension": {"keep": "me"},
    }))
    workspace.path("ats_answers").write_text("demographics: prefer_not_to_answer\n")
    assert settings_issues(workspace) == []


@pytest.mark.parametrize("contents", ["null", "[]", "secret-value: [unterminated"])
def test_malformed_settings_do_not_leak_values(workspace, contents):
    workspace.path("preferences").write_text(contents)
    issues = settings_issues(workspace)
    assert issues
    assert "secret-value" not in json.dumps(issues)


def test_cli_validate_and_audit_report_settings_errors_without_writes(workspace, capsys):
    path = workspace.path("preferences")
    path.write_text("submission: secret-value\n")
    before = path.read_bytes()
    assert cli.main(["--config", str(workspace.config_path), "validate"]) == 1
    assert "secret-value" not in capsys.readouterr().err
    assert cli.main(["--config", str(workspace.config_path), "audit-workspace"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert any(item["type"] == "invalid_workspace_settings" for item in report["findings"])
    assert path.read_bytes() == before


def test_partial_unknown_answers_are_valid_but_not_personal_readiness(workspace):
    workspace.path("preferences").write_text("salary: {minimum: null, currency: null, period: null}\n")
    workspace.path("ats_answers").write_text("work_authorization: {by_country: {Exampleland: {authorized: null}}}\n")
    assert settings_issues(workspace) == []
