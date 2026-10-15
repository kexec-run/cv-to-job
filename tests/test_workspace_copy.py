import stat

import pytest

from cv_job import workspace_copy


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "empty").mkdir()
    (root / "credentials.env").write_bytes(b"fictional credential\x00\xff")
    (root / "credentials.env").chmod(0o600)
    (root / "applications.json").write_bytes(b'{"applications": []}\n')
    return root


def test_backup_and_restore_preserve_bytes_permissions_and_empty_directories(source, tmp_path):
    before = workspace_copy.manifest(source)
    backup = tmp_path / "backup"
    restored = tmp_path / "restored"
    workspace_copy.copy_verified(source, backup)
    workspace_copy.copy_verified(backup, restored)
    assert workspace_copy.manifest(source) == workspace_copy.manifest(backup) == before
    assert workspace_copy.manifest(restored) == before
    assert stat.S_IMODE(backup.stat().st_mode) == 0o700
    assert stat.S_IMODE(restored.stat().st_mode) == 0o700
    assert (restored / "credentials.env").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("name", ["backup", "backup.copying"])
@pytest.mark.parametrize("kind", ["directory", "file", "broken_symlink"])
def test_copy_refuses_existing_targets(source, tmp_path, name, kind):
    path = tmp_path / name
    if kind == "directory":
        path.mkdir()
    elif kind == "file":
        path.write_bytes(b"preserve")
    else:
        path.symlink_to(tmp_path / "missing")
    before = workspace_copy.manifest(source)
    with pytest.raises(FileExistsError):
        workspace_copy.copy_verified(source, tmp_path / "backup")
    assert workspace_copy.manifest(source) == before
    if kind == "file":
        assert path.read_bytes() == b"preserve"
    elif kind == "broken_symlink":
        assert path.is_symlink()


def test_copy_refuses_nested_paths_and_symlinks(source, tmp_path):
    with pytest.raises(ValueError, match="non-nested"):
        workspace_copy.copy_verified(source, source / "backup")
    (source / "link").symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError, match="symlink"):
        workspace_copy.copy_verified(source, tmp_path / "backup")
    assert not (tmp_path / "backup.copying").exists()


def test_failed_verification_keeps_source_and_staging(source, tmp_path, monkeypatch):
    before = workspace_copy.manifest(source)
    real_copy = workspace_copy.shutil.copy2

    def corrupt_copy(src, dst, **kwargs):
        result = real_copy(src, dst, **kwargs)
        dst.write_bytes(b"corrupt copy")
        return result

    monkeypatch.setattr(workspace_copy.shutil, "copy2", corrupt_copy)
    with pytest.raises(ValueError, match="verification failed"):
        workspace_copy.copy_verified(source, tmp_path / "backup")
    assert workspace_copy.manifest(source) == before
    assert not (tmp_path / "backup").exists()
    assert (tmp_path / "backup.copying").is_dir()


def test_copy_refuses_a_source_change_during_copy(source, tmp_path, monkeypatch):
    real_copy = workspace_copy.shutil.copy2

    def change_source(src, dst, **kwargs):
        result = real_copy(src, dst, **kwargs)
        src.write_bytes(b"changed during copy")
        return result

    monkeypatch.setattr(workspace_copy.shutil, "copy2", change_source)
    with pytest.raises(ValueError, match="source changed"):
        workspace_copy.copy_verified(source, tmp_path / "backup")
    assert not (tmp_path / "backup").exists()


def test_copy_cli_does_not_expose_secret_values(source, tmp_path, capsys):
    assert workspace_copy.main(["--source", str(source), "--destination", str(tmp_path / "backup")]) == 0
    assert "fictional credential" not in capsys.readouterr().out
