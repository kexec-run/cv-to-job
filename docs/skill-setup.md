# Use the included application skill

The maintained source is `skills/apply-to-jobs/` in this repository. It includes the entry point, detailed supporting guides, template, and metadata. Use this adapted cv-job version only. The original author's repository is credited in `THIRD_PARTY_NOTICES.md`; it is not an alternative install target.

## Choose how Codex reads it

You can ask Codex to read `skills/apply-to-jobs/SKILL.md` directly while working in this checkout. Root `AGENTS.md` routes application work there. To make the same skill available through automatic discovery, install it with `npx skills` from this repository's root:

```bash
# Inspect existing installations first:
npx skills list --agent codex
npx skills list --agent codex --global

# Choose project-local installation:
npx skills add . --skill apply-to-jobs --agent codex

# OR choose global installation:
npx skills add . --skill apply-to-jobs --agent codex --global
```

Project installs live in `.agents/skills/apply-to-jobs/`; global installs live in `~/.agents/skills/apply-to-jobs/`. Keep one selected entry point for the project. Codex can discover same-named skills separately, so do not merge divergent instructions. If a duplicate is confusing, ask which installation to retain rather than deleting it automatically.

## Preserve existing customizations

Before replacing an existing installation, resolve symlinks, inspect differences against the repository source, and make a verified backup outside skill-discovery directories. Do not print secrets if a legacy installation contains private data. Ask before discarding customizations or removing another installation.

Put approved generic workflow changes in `skills/apply-to-jobs/` in this repo. Candidate-specific facts and policies stay in the selected private workspace, not the public skill. Refresh the selected installed copy from this source after changes; do not assume a copied local install follows edits automatically. Do not update it from the original author's upstream repository or recreate the old profile/auto-submit workflow.

## Check the result

List the selected scope again and confirm it is this repo's cv-job variant: it uses `cv-job.yaml`, the repository CLI, evidence-backed TeX CVs, saved submission preferences, and the Gmail wrapper. If discovery is stale, restart Codex. Installed copies are not the source of truth; if they differ, read the maintained repository source and report the mismatch before application work.

Run commands from the cv-job project root, not an installed skill folder. Even when `npx skills` also copies the package's compatibility scripts, use this project's `uv run cv-job ...` CLI so configured paths resolve in the intended repository.

Installation does not initialize private data, install Python/TeX, connect Gmail, or authorize submissions. Follow `docs/initialization.md` before real applications. Do not access email, create accounts, or submit a test application just to check skill discovery.
