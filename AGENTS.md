# Agent instructions

## Load the selected workspace

Before candidate-related work, load `private/cv-job.yaml` or the user's explicit `--config PATH`. Resolve `workspace` relative to the configuration file and `paths.*` relative to that workspace. Explicitly read `paths.instructions` first, then the configured candidate, experience, preferences, and ATS answers relevant to the task. Do not assume a nested instruction file was automatically loaded. Repeat this when switching configurations; never mix candidate sources between workspaces.

Treat evidence states as authoritative. Do not invent or promote claims. Stop on a master-versus-ledger contradiction. Keep the master CV and submitted artifacts unchanged unless the user explicitly requests a change. Store new application records and documents in the selected workspace. Preserve history and existing attachments. Never put secrets in tracked/public files, workspace YAML, or application records. Preserve existing private ATS credential files as described below. Keep `sample/` fictional and unchanged during real application work.

## First-time setup

When asked to initialize or personalize a workspace, follow `docs/initialization.md`. Check whether `private/` itself already exists (including symlinks), not merely its config file; an existing folder with a missing config needs inspection, not initialization over it. Also offer that flow if the selected workspace is missing or still contains fictional sample identity/experience; do not use fictional data for real applications. Resume existing setup instead of reinitializing it. Ask only for missing or conflicting information in small batches, preserve confirmed values, and distinguish setup readiness from permission to submit. Do not run onboarding merely because an established workspace has an optional unanswered field.

## Agent workflow

For job search and applications, read this repository's `skills/apply-to-jobs/SKILL.md` and its relevant guides. This adapted cv-job skill is the single maintained source. Use it directly in this checkout, or install it project-locally/globally using `docs/skill-setup.md`. Installed copies are discovery entry points, not separate sources to maintain. If an installed copy differs, read the repository source and report the mismatch; do not merge workflows or overwrite customized installations without preserving and reviewing them first. The original author's upstream skill is attribution only, not an alternative workflow for this project.

Run `uv run cv-job ...` from this repository's root, carrying `--config PATH` before the subcommand for a non-default workspace. An installed skill directory is not the project root. Run this project's CLI, not duplicated scripts inside an installed skill copy.

Honor the selected submission preference and site-specific confirmation rules. A target application count does not authorize changing them. Required unresolved answers prevent submission. Record `applied` only after confirming the application's submitted state; account signup or email verification alone is insufficient.

For multiagent application work, read `docs/multiagent.md`. One coordinator owns the shared run; each worker must claim its assigned job with a unique `--owner` and pass it on every update. Never share a job/browser context, edit the JSON directly, delete lock files, or steal stale claims. Stop failed/ambiguous workers and verify portal state before an explicit handoff. Keep Gmail serialized through one coordinator/session. File ownership never expands submission authorization.

## ATS login credentials

Workspace configuration is YAML; private `.env` files are a separate, existing credential source, not an environment-variable configuration interface for `cv-job`. Before creating or resetting an ATS account, check the selected workspace's account metadata, available OS credential store, and relevant employer/tenant credential-file paths. Include hidden, Git-ignored files when checking for presence; normal file searches may omit them. Limit discovery to the selected private workspace and active employer. Match the exact ATS host/tenant and application email; never try another employer's credentials.

Preserve existing credential files byte-for-byte. Do not move, rewrite, delete, migrate, or change permissions without authorization. Report locations and non-secret status only; never dump a `.env` file, print values, put secrets in command arguments/logs/chat, or copy them to YAML, sample data, or application history. Do not shell-source or execute `.env` files. Use a credential only through a supported secure retrieval/entry path for the authorized login; if that path would expose it in tool output, ask the user to sign in manually instead. Do not ask for passwords in chat. Prefer the OS credential store for newly saved credentials; no credential migration is implied by setup work. Never persist OTPs in credential files.

## Email connector calls

Read `skills/apply-to-jobs/references/accounts.md` before ATS signup, login, or email verification. Use the connected Gmail tools for search/read only within the authorized task. Match messages to the active recipient, request time, ATS tenant, and event. Keep codes, tokens, passwords, and email bodies out of retry state and application records.

Route Gmail calls through `scripts/gmail-wrapper.cjs`, using the loading example in `docs/gmail.md`. Do not call raw Gmail tools alongside the wrapper. Reuse its timing state across calls, run one email workflow per mailbox, and stop after exhausted retries. Do not reset timing or request another ATS code to evade a cooldown.

If access fails or remains rate-limited, report the verified findings and unchecked scope. Distinguish an empty search from a failed search. Ask for connector access to be restored on an authentication failure; do not treat a quota limit as missing permission. Gmail is optional for manual CV work and jobs that do not need email verification.

## Repository changes

Read before editing, make focused changes, and preserve unrelated working-tree edits. Run application-write tests only in temporary workspaces. After Python changes, run `uv run ruff check .` and `uv run pytest -q`; after wrapper changes, run `node --test tests/gmail-wrapper.test.cjs`. After configuration or rendering changes, also validate and audit `sample/cv-job.yaml`; keep rendered test output in a temporary directory. Explain failed or unavailable checks rather than claiming they passed. For private backup/restore, follow `docs/backup.md`; never overwrite a current workspace with a backup. See the README for installation and command examples.
