"""Load the workspace configuration shared by the CLI and compatibility scripts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "private" / "cv-job.yaml"
REQUIRED_PATHS = {
    "instructions",
    "candidate",
    "experience",
    "preferences",
    "ats_answers",
    "applications",
    "applications_dir",
    "master_cv_dir",
    "cv_bases_dir",
    "previews_dir",
    "templates_dir",
}


@dataclass(frozen=True)
class WorkspaceConfig:
    config_path: Path
    workspace: Path
    paths: dict[str, Path]
    repo_root: Path = REPO_ROOT

    def path(self, key: str) -> Path:
        return self.paths[key]


def configured_path_issues(config: WorkspaceConfig) -> list[dict]:
    """Return missing or wrongly typed workspace paths in stable key order."""
    expected_types = {"workspace": "directory"}
    expected_types.update({
        key: "file" if key in {"instructions", "candidate", "experience", "preferences",
                              "ats_answers", "applications"} else "directory"
        for key in REQUIRED_PATHS
    })
    paths = {"workspace": config.workspace, **config.paths}
    issues = []
    for key in sorted(expected_types):
        path_value = paths.get(key)
        if path_value is None:
            continue
        expected = expected_types[key]
        if not path_value.exists():
            reason = "missing"
        elif ((expected == "file" and not path_value.is_file())
              or (expected == "directory" and not path_value.is_dir())):
            reason = "wrong_type"
        else:
            continue
        issues.append({"key": key, "path": str(path_value),
                       "expected_type": expected, "reason": reason})
    return issues


def load_config(path: str | Path | None = None, *, check_paths: bool = True) -> WorkspaceConfig:
    config_path = Path(path).expanduser().resolve() if path else DEFAULT_CONFIG
    if not config_path.is_file():
        raise FileNotFoundError(
            f"workspace config not found: {config_path}; initialize with `uv run cv-job init`"
        )
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TypeError(f"{config_path} must contain a YAML mapping")
    if raw.get("version") != 1:
        raise ValueError(f"unsupported workspace config version: {raw.get('version')!r}")
    workspace_value = raw.get("workspace", ".")
    if not isinstance(workspace_value, str):
        raise TypeError("workspace must be a path string")
    workspace = (config_path.parent / workspace_value).resolve()
    configured = raw.get("paths")
    if not isinstance(configured, dict):
        raise TypeError("paths must be a YAML mapping")
    missing = REQUIRED_PATHS - configured.keys()
    if missing:
        raise ValueError(f"configuration is missing paths: {', '.join(sorted(missing))}")
    paths: dict[str, Path] = {}
    for key in REQUIRED_PATHS:
        value = configured[key]
        if not isinstance(value, str) or not value:
            raise TypeError(f"paths.{key} must be a non-empty path string")
        paths[key] = (workspace / value).resolve()
    config = WorkspaceConfig(config_path, workspace, paths)
    if check_paths:
        issues = configured_path_issues(config)
        if issues:
            details = "; ".join(
                f"{issue['key']} ({issue['reason']} {issue['expected_type']}): {issue['path']}"
                for issue in issues
            )
            raise FileNotFoundError(f"workspace has invalid configured paths: {details}")
    return config


def resolve_artifact_path(value: str | Path, config: WorkspaceConfig) -> Path:
    """Resolve both legacy repository-relative and current workspace-relative paths."""
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    if is_legacy_artifact_path(path):
        return (config.repo_root / path).resolve()
    return (config.workspace / path).resolve()


def is_legacy_artifact_path(value: str | Path) -> bool:
    """Whether a relative artifact value uses the original repository private/ prefix."""
    path = Path(value)
    return not path.is_absolute() and bool(path.parts) and path.parts[0] == "private"
