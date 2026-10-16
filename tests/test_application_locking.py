"""Real process contention against fictional temporary workspaces only."""

import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cv_job import application_lock as locking
from cv_job.application_lock import LockBusy, application_lock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "apply-to-jobs" / "scripts" / "jobs.py"
pytestmark = pytest.mark.skipif(locking.fcntl is None, reason="POSIX flock required")


@pytest.fixture
def workspace(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(ROOT / "sample", workspace)
    (workspace / "posting.txt").write_text("Fictional systems engineering job posting for temporary CLI tests.")
    return workspace


def command(workspace, *args):
    return subprocess.run([sys.executable, str(SCRIPT), "--config", str(workspace / "cv-job.yaml"), *args],
                          capture_output=True, text=True, timeout=20, check=False)


def data(workspace):
    return json.loads((workspace / "applications.json").read_text())


def add(workspace, index=0, *args):
    return command(workspace, "add", "--company", "Example", "--title", "Systems Engineer",
                   "--url", f"https://example.test/jobs/{index}",
                   "--posting-file", str(workspace / "posting.txt"), *args)


def successful(result):
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_concurrent_adds_do_not_lose_records_or_collide_folders(workspace):
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda i: add(workspace, i), range(30)))
    ids = {successful(result)["id"] for result in results}
    assert len(ids) == 30
    records = data(workspace)["applications"]
    assert {app["id"] for app in records} == ids
    assert len({app["folder"] for app in records}) == 30
    assert all((workspace / app["folder"]).is_dir() for app in records)
    assert not list(workspace.glob(".applications.json.*.tmp"))


def test_concurrent_deduplication_add_and_claim_has_one_winner(workspace):
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda i: add(workspace, 0, "--owner", f"worker-{i}"), range(15)))
    winners = [result for result in results if result.returncode == 0]
    assert len(winners) == 1
    app = data(workspace)["applications"][0]
    assert len(data(workspace)["applications"]) == 1
    assert app["claim"]["owner"] == successful(winners[0])["claim"]["owner"]


def test_parallel_history_updates_preserve_existing_events_and_artifacts(workspace):
    app = successful(add(workspace))
    artifact = workspace / app["folder"] / "submitted.pdf"
    artifact.write_bytes(b"fictional historical artifact\x00\xff")
    before = data(workspace)["applications"][0]["history"][:]
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda i: command(workspace, "update", "--id", app["id"],
                                                "--note", f"event-{i}"), range(25)))
    assert all(result.returncode == 0 for result in results)
    history = data(workspace)["applications"][0]["history"]
    assert history[:len(before)] == before
    assert {event["note"] for event in history[len(before):]} == {f"event-{i}" for i in range(25)}
    assert artifact.read_bytes() == b"fictional historical artifact\x00\xff"


def test_claims_require_matching_owner_and_explicit_handoff(workspace):
    app = successful(add(workspace))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: command(workspace, "claim", "--id", app["id"],
                                                "--owner", f"worker-{i}"), range(8)))
    assert sum(result.returncode == 0 for result in results) == 1
    owner = data(workspace)["applications"][0]["claim"]["owner"]
    claim_before = data(workspace)["applications"][0]["claim"].copy()
    successful(command(workspace, "claim", "--id", app["id"], "--owner", owner))
    assert data(workspace)["applications"][0]["claim"] == claim_before
    for args in [[], ["--owner", "someone-else"]]:
        before = (workspace / "applications.json").read_bytes()
        assert command(workspace, "update", "--id", app["id"], "--note", "not allowed", *args).returncode != 0
        assert (workspace / "applications.json").read_bytes() == before
    assert command(workspace, "release", "--id", app["id"], "--owner", "wrong-owner").returncode != 0
    successful(command(workspace, "update", "--id", app["id"], "--owner", owner, "--status", "review_ready"))
    successful(command(workspace, "release", "--id", app["id"], "--owner", owner))
    assert command(workspace, "update", "--id", app["id"], "--owner", owner, "--note", "stale").returncode != 0
    successful(command(workspace, "claim", "--id", app["id"], "--owner", "next-worker"))
    assert data(workspace)["applications"][0]["claim"]["owner"] == "next-worker"


def test_run_start_refuses_to_end_an_active_run_and_end_checks_coordinator(workspace):
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda i: command(workspace, "run", "start", "--owner", f"coordinator-{i}"),
                                range(6)))
    assert sum(result.returncode == 0 for result in results) == 1
    before = data(workspace)
    assert len(before["runs"]) == 1
    assert command(workspace, "run", "end").returncode != 0
    assert command(workspace, "run", "end", "--owner", "wrong-owner").returncode != 0
    assert data(workspace) == before
    owner = before["runs"][0]["owner"]
    successful(command(workspace, "run", "end", "--owner", owner))
    assert data(workspace)["active_run"] is None


def test_submitted_records_cannot_be_claimed(workspace):
    app = successful(add(workspace))
    successful(command(workspace, "update", "--id", app["id"], "--status", "applied"))
    before = (workspace / "applications.json").read_bytes()
    assert command(workspace, "claim", "--id", app["id"], "--owner", "worker").returncode != 0
    assert (workspace / "applications.json").read_bytes() == before


def test_duplicate_external_url_is_rejected_without_rewriting_records(workspace):
    first = successful(add(workspace, 0))
    second = successful(add(workspace, 1))
    before = (workspace / "applications.json").read_bytes()
    result = command(workspace, "update", "--id", second["id"], "--add-url", "https://example.test/jobs/0")
    assert result.returncode != 0
    assert (workspace / "applications.json").read_bytes() == before
    assert first["id"] != second["id"]


def test_timeout_and_killed_holder_do_not_require_deleting_lock_file(workspace):
    path = workspace / "applications.json"
    before = path.read_bytes()
    program = ("import sys,time; from pathlib import Path; "
               "from cv_job.application_lock import application_lock; "
               "\nwith application_lock(Path(sys.argv[1])):\n print('locked',flush=True)\n time.sleep(30)\n")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    holder = subprocess.Popen([sys.executable, "-c", program, str(path)], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, env=env)
    try:
        # An empty line/EOF fails immediately if the child cannot import or lock.
        assert holder.stdout.readline().strip() == "locked"
        result = add(workspace, 0, "--lock-timeout", "0.05")
        assert result.returncode == 3
        assert "busy" in result.stderr
        assert path.read_bytes() == before
        # Atomic replacement permits readers without taking the writer lock.
        assert command(workspace, "list").returncode == 0
    finally:
        holder.kill()
        holder.communicate(timeout=5)
    lock_path = path.with_name(path.name + ".lock")
    inode = lock_path.stat().st_ino
    with application_lock(path, timeout=0):
        assert lock_path.stat().st_ino == inode
    successful(add(workspace))


@pytest.mark.parametrize("timeout", [-1, math.nan, math.inf])
def test_invalid_timeout_fails_without_modifying_ledger(workspace, timeout):
    path = workspace / "applications.json"
    before = path.read_bytes()
    with pytest.raises(ValueError), application_lock(path, timeout):
        pytest.fail("invalid timeout accepted")
    assert path.read_bytes() == before


def test_canonical_paths_contend_on_the_same_lock_and_refuse_sidecar_symlinks(workspace):
    path = workspace / "applications.json"
    alias = workspace / "alias.json"
    alias.symlink_to(path)
    with application_lock(path), pytest.raises(LockBusy), application_lock(alias, timeout=0):
        pytest.fail("alias bypassed lock")
    another = workspace / "another.json"
    sidecar = workspace / "another.json.lock"
    sidecar.symlink_to(path)
    before = path.read_bytes()
    with pytest.raises(OSError), application_lock(another):
        pytest.fail("sidecar symlink accepted")
    assert sidecar.is_symlink()
    assert path.read_bytes() == before


def test_failed_replace_preserves_old_json_permissions_and_unrelated_temp(workspace, monkeypatch):
    spec = importlib.util.spec_from_file_location("jobs_lock_test", SCRIPT)
    jobs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(jobs)
    path = workspace / "applications.json"
    path.chmod(0o640)
    old_tmp = workspace / "applications.json.tmp"
    old_tmp.write_bytes(b"pre-existing staging data")
    before = path.read_bytes()
    with application_lock(path):
        log = jobs.Log(ROOT, path, workspace / "applications", workspace)
        log.data["extra"] = "new"

        def fail_replace(*args):
            raise OSError("simulated write failure")

        with monkeypatch.context() as patch:
            patch.setattr(jobs.os, "replace", fail_replace)
            with pytest.raises(OSError):
                log.save()
        assert path.read_bytes() == before
        assert old_tmp.read_bytes() == b"pre-existing staging data"
        assert not list(workspace.glob(".applications.json.*.tmp"))
        log.save()
    assert path.stat().st_mode & 0o777 == 0o640
    assert data(workspace)["extra"] == "new"


def test_missing_flock_fails_closed(workspace, monkeypatch):
    monkeypatch.setattr(locking, "fcntl", None)
    with pytest.raises(RuntimeError, match="POSIX"), application_lock(workspace / "applications.json"):
        pytest.fail("unlocked write allowed")


def test_unified_cli_passes_worker_and_timeout_options(workspace):
    result = subprocess.run([
        sys.executable, "-m", "cv_job.cli", "--config", str(workspace / "cv-job.yaml"), "applications", "add",
        "--company", "Example", "--title", "Engineer", "--url", "https://example.test/jobs/unified",
        "--owner", "worker-unified", "--lock-timeout", "1",
        "--posting-file", str(workspace / "posting.txt"),
    ], capture_output=True, text=True, timeout=20, check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    app = successful(result)
    assert app["claim"]["owner"] == "worker-unified"


def test_existing_unrecorded_folder_is_not_overwritten(workspace):
    first = successful(add(workspace))
    old_artifact = workspace / first["folder"] / "keep.pdf"
    old_artifact.write_bytes(b"preserve existing folder")
    (workspace / "applications.json").write_text(json.dumps({"active_run": None, "runs": [], "applications": []}))
    second = successful(add(workspace, 1))
    assert first["id"] != second["id"]
    assert old_artifact.read_bytes() == b"preserve existing folder"


def test_resumed_application_participates_without_changing_origin(workspace):
    original = successful(command(workspace, "run", "start", "--objective", "Original"))
    app = successful(add(workspace))
    original_record = data(workspace)["applications"][0].copy()
    successful(command(workspace, "run", "end"))
    resumed = successful(command(workspace, "run", "start", "--objective", "Resume"))
    successful(command(workspace, "claim", "--id", app["id"], "--owner", "worker"))
    after_claim = (workspace / "applications.json").read_bytes()
    successful(command(workspace, "claim", "--id", app["id"], "--owner", "worker"))
    assert (workspace / "applications.json").read_bytes() == after_claim
    saved = data(workspace)
    assert saved["runs"][-1]["applications"] == [app["id"]]
    assert saved["applications"][0]["run"] == original["id"]
    assert saved["applications"][0]["history"] == original_record["history"]
    assert len(saved["applications"]) == 1
    assert successful(command(workspace, "status"))["run"]["total"] == 1
    for run in (original, resumed):
        listed = command(workspace, "list", "--run", run["id"])
        assert listed.returncode == 0
        assert app["id"] in listed.stdout
        assert "(1 shown)" in listed.stdout
    report = command(workspace, "report")
    assert report.returncode == 0
    assert "Example — Systems Engineer" in report.stdout
    assert successful(command(workspace, "run", "end"))["total"] == 1
    assert "Example — Systems Engineer" in command(workspace, "report").stdout


def test_failed_claim_does_not_register_participation(workspace):
    app = successful(add(workspace, 0, "--owner", "first"))
    successful(command(workspace, "run", "start"))
    before = (workspace / "applications.json").read_bytes()
    assert command(workspace, "claim", "--id", app["id"], "--owner", "other").returncode != 0
    assert (workspace / "applications.json").read_bytes() == before
    assert successful(command(workspace, "status"))["run"]["total"] == 0
    # An idempotent claim in a later run still records that run's participation.
    successful(command(workspace, "claim", "--id", app["id"], "--owner", "first"))
    assert successful(command(workspace, "status"))["run"]["total"] == 1
    successful(command(workspace, "release", "--id", app["id"], "--owner", "first"))
    successful(command(workspace, "claim", "--id", app["id"], "--owner", "other"))
    assert data(workspace)["runs"][-1]["applications"] == [app["id"]]


def test_claim_new_application_counted_once_and_no_run_required(workspace):
    successful(command(workspace, "run", "start"))
    app = successful(add(workspace, 0, "--owner", "worker"))
    successful(command(workspace, "claim", "--id", app["id"], "--owner", "worker"))
    assert successful(command(workspace, "status"))["run"]["total"] == 1
    successful(command(workspace, "run", "end"))
    runs = data(workspace)["runs"]
    successful(command(workspace, "claim", "--id", app["id"], "--owner", "worker"))
    assert data(workspace)["runs"] == runs


def test_show_is_complete_read_only_and_missing_id_fails(workspace):
    app = successful(add(workspace, 0, "--owner", "worker"))
    successful(command(workspace, "update", "--id", app["id"], "--owner", "worker",
                       "--note", "Inspect this history"))
    before = (workspace / "applications.json").read_bytes()
    # No writer lock or ownership needed for inspecting an atomic snapshot.
    with application_lock(workspace / "applications.json"):
        shown = successful(command(workspace, "show", "--id", app["id"]))
    assert shown == data(workspace)["applications"][0]
    missing = command(workspace, "show", "--id", "missing")
    assert missing.returncode != 0
    assert "no application" in missing.stderr
    assert (workspace / "applications.json").read_bytes() == before


def test_concurrent_resumes_preserve_all_participants(workspace):
    apps = [successful(add(workspace, index)) for index in range(8)]
    successful(command(workspace, "run", "start"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda app: command(workspace, "claim", "--id", app["id"],
                                                   "--owner", app["id"]), apps))
    assert all(result.returncode == 0 for result in results)
    assert set(data(workspace)["runs"][-1]["applications"]) == {app["id"] for app in apps}
    assert successful(command(workspace, "status"))["run"]["total"] == 8
