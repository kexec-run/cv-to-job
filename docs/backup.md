# Back up and restore a private workspace

GitHub does not contain `private/`. Cloning the repository on another computer will not restore your CVs, application history, or ATS credentials. Make a separate backup before personal-data edits and before moving computers.

Stop application runs and other writers while copying. Use a private destination outside this repository, preferably on a separate encrypted drive. The copy includes plaintext credential files if present: do not publish or put it in an unprotected shared folder. The helper does not encrypt anything.

## Create a backup

From the repository root, choose an existing parent directory you control and a new backup name. Replace `/absolute/path/to/private-backups` below; do not use an existing backup name.

```bash
uv run python -m cv_job.workspace_copy \
  --source private \
  --destination /absolute/path/to/private-backups/cv-job-backup-2026-10-15
```

The helper:

1. Refuses an existing destination or `<destination>.copying` staging path, including broken symlinks. It also refuses nested source/destination paths.
2. Copies into a staging directory with owner-only access.
3. Compares file lists, SHA-256 hashes, empty directories, and child entry permissions; checks the source again for changes.
4. Renames the verified copy into place. It never deletes the source or an existing backup.

File contents and child permissions are preserved, including `600` credential files. The destination root is deliberately `700`. Permission preservation is intended for POSIX filesystems; use a filesystem that supports those permissions. Symlinks and special files are refused so external files are not silently omitted or followed. Ask for a review if that check fails—do not remove personal links/files just to pass it.

If copying fails, keep any `.copying` directory and inspect the failure. Do not delete a previous backup or automatically retry into a conflicting location. This is a single-writer copy helper, not a concurrent filesystem snapshot service.

## Test restoration without touching the current workspace

Choose another unused destination outside the repository:

```bash
uv run python -m cv_job.workspace_copy \
  --source /absolute/path/to/private-backups/cv-job-backup-2026-10-15 \
  --destination /absolute/path/to/private-backups/cv-job-restore-test

uv run cv-job --config /absolute/path/to/private-backups/cv-job-restore-test/cv-job.yaml validate
uv run cv-job --config /absolute/path/to/private-backups/cv-job-restore-test/cv-job.yaml audit-workspace
```

The copy verifies bytes and permissions against the backup. CLI checks assess the restored workspace's structure, not whether all facts are true. A new backup cannot prove that already-corrupt source data was correct.

Legacy attachment paths beginning with `private/`, absolute paths, or configured files outside the copied workspace may still refer to the original repository. The copy includes only the source directory. For a complete restoration test of those records, use a separate repository checkout, restore to its absent `private/`, and run checks there. Report unresolved external references; do not rewrite history or attachments automatically.

## Restore on a new checkout

Install dependencies first, but **do not run `cv-job init`**. If the checkout has any `private/` path already, stop and preserve it; restore to a separate test location until you decide what to keep. When `private/` is absent:

```bash
uv run python -m cv_job.workspace_copy \
  --source /absolute/path/to/private-backups/cv-job-backup-2026-10-15 \
  --destination private

uv run cv-job validate
uv run cv-job audit-workspace
```

Confirm the application history, attachments, CVs, and credential permissions before resuming applications. Do not display credentials during verification. Retain the backup until you have confirmed recovery. If using pip, replace `uv run python` with the virtual environment's `python` and `uv run cv-job` with `cv-job`.
