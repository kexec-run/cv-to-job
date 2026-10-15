# Agent-guided initialization

Use this guide when the user asks to initialize, personalize, or finish setting up a workspace. This is a short conversation plus YAML edits, not a separate wizard or a second application skill. Commands below run from the repository root.

## 1. Inspect before asking or copying

Read the root `AGENTS.md`, selected configuration, and existing configured instructions and candidate sources. Default to `private/cv-job.yaml`; honor an explicitly selected workspace. Do not display personal files wholesale in chat.

Check the needed capabilities before promising a full application workflow: local command execution, CV text extraction, a TeX engine, browser interaction for the ATS, access to this repo's included skill, and optional Gmail access. The skill may be read directly or installed project-locally/globally for discovery. Missing browser/connector support means a manual handoff, not permission to invent a tool or claim an automated step succeeded. Explain missing dependencies and propose platform-appropriate installation steps before asking the user to run them; do not require a novice to debug a toolchain unaided.

Before deciding to initialize, check the actual `private/` path, not just whether `private/cv-job.yaml` exists. Check for a symlink too, including a broken one. Also check the initializer's staging path (`private.migrating`). For an explicitly selected configuration, inspect its destination and workspace as well; do not silently fall back to the default.

- Existing directory with a valid config: load and resume it. Ask only about missing or conflicting information; do not copy sample defaults over personal choices.
- Existing directory with a missing or invalid config, even if apparently empty: preserve it and ask how to repair or adopt it. Do not run `init` or treat it as a fresh workspace.
- Existing file, symlink, or staging path: stop initialization and report the exact conflict. Do not remove it or follow a symlink for writes without resolving the target and user intent.
- No destination or staging path: initialize the default workspace as below.

Only when the default destination and staging path are both absent, install the locked dependencies if needed and initialize it:

```bash
uv sync --frozen
uv run cv-job init
```

`init` creates only the default `private/` workspace, using its verified staging-and-rename flow. Do not use it to initialize a custom path. If a destination or staging directory already exists, stop that operation and inspect it; do not delete it, overwrite it, or blindly rerun initialization. For a new custom workspace, first agree its location with the user and use the same non-overwriting, verified copy approach. Keep real data under ignored repository-local `private/` for this version.

If a workspace already exists, resume it in place. A missing configuration in a nonempty directory is a repair question, not permission to replace the directory. Preserve existing records, attachments, confirmed answers, and comments. Before changing existing personal files, make verified copies of the exact files being edited in a non-conflicting location under the ignored private workspace; never overwrite a previous backup. Do not run Git history changes as part of onboarding.

For a full external backup or restoration, use `docs/backup.md`. Include existing ignored ATS credential files without printing their values, and preserve their permissions. Never restore on top of a current workspace.

## 2. Interview in small batches

Start with a brief summary of what is already known and what is missing. Ask two or three closely related questions at a time. Accept free-text replies and "unknown", "later", or "prefer not to disclose". Do not repeat questions answered in the workspace or current conversation. Ask about a contradiction instead of silently choosing a source.

Use these groups in order, skipping confirmed information:

1. **Identity and evidence.** Ask for preferred/legal name as needed, application email, city/country/timezone, and a current CV or other candidate-approved factual source. Ask for phone/profile links only if needed or volunteered; defer full street address until a form requires it. Confirm official titles, employers, dates, and education against the supplied source. Do not ask for account passwords, OTPs, ID numbers, or unnecessary sensitive details.
2. **Job preferences.** Ask which role families and job kinds to include/exclude; target countries/cities; remote, hybrid, onsite, and relocation choices. Then ask about travel, shifts, salary minimum with currency/period, and notice period where relevant. Explain that remote does not establish work authorization. Separate hard exclusions from preferences that the user is willing to discuss.
3. **Screening and privacy.** Ask about work authorization and current/future sponsorship separately for each target country. Offer the sample's non-disclosure choices for optional demographics without requiring the user to reveal gender, ethnicity, disability, or veteran status. Confirm marketing, future-opportunity retention, and optional SMS choices. Leave employer-specific processing, policy acknowledgments, background checks, and unclear/combined consent as `ask` unless the user explicitly approves a defined scope; do not seek blanket agreement to unseen policies.
4. **Operating boundaries.** Explain `review_before_submit` and retain it unless the user explicitly changes it. Confirm any stricter site-specific rules. Use the included cv-job skill, explain optional project/global installation for discovery, and explain the optional Gmail connector for verification. Ask whether the user wants to connect Gmail or handle verification manually; do not search their mailbox, create ATS accounts, or submit anything merely to test setup.

Example opening:

> I found a workspace with fictional sample data. What name and application email should it use, which city/country are you based in, and which CV should I use as the factual source? You can defer anything you don't want to provide yet.

After that reply, ask the next relevant group—not the whole questionnaire again.

### When the user brings a PDF, Word CV, or no TeX source

Keep the supplied original unchanged in the selected private workspace. Use available document-reading tools to extract its text; if extraction is unreliable or unavailable, ask for readable text or the user's help. Show a concise factual outline and ask about gaps or contradictions. Do not infer metrics, dates, titles, skill depth, or identity from missing text.

After the user approves those facts, create a new master TeX source (roughly three pages is a target, not a quota), an evidence ledger tied to its exact wording, and one role-specific base from the relevant subset. Do not overwrite an existing real master without permission. Preserve detailed original facts without padding the CV or upgrading evidence states. Render the master with a TeX engine directly and the application base with the 1–2-page renderer. Show the PDFs for factual/layout review before calling the documents ready.

If the user has no CV yet, draft the factual outline from their answers first and obtain approval before generating CV sources. Missing genuine experience information leaves document preparation incomplete; sample achievements are never a substitute.

## 3. Save confirmed answers in the right place

- `candidate.yaml`: confirmed identity, contact, employment, and education facts.
- `preferences.yaml`: job scope, working arrangements, salary/notice preferences, and submission setting.
- `ats_answers.yaml`: country-specific eligibility, disclosure/consent preferences, and confirmed answers to exact screening questions.
- `experience.yaml` and CV sources: evidence-backed experience only. Inspect their existing format before editing. Ask before changing an existing master CV; do not relabel sample accomplishments as the user's work or upgrade evidence without support.

Edit the selected workspace, never `sample/`. Keep useful YAML comments listing options. Preserve unrelated keys and existing file formats; do not replace established schemas with the sample layout. Unknown factual values stay `null` or unresolved, not false or zero. A request to skip a demographic question is a disclosure preference, not an identity claim. Conflicting answers remain unresolved until clarified.

For a new workspace copied from the sample, replace fictional identity, employment, education, master CV, bases, and ledger with internally consistent candidate-approved material before using them for real jobs. Do not fabricate filler to satisfy validation. If genuine source material is missing, leave the workspace demo-only and report what is needed. Retain historical material in an established workspace; do not reset application history or regenerate submitted documents.

These preference fields guide the agent; the CLI does not enforce all answer choices or determine whether a consent checkbox has equivalent wording.

## 4. Verify and hand off

For the default workspace:

```bash
uv run cv-job validate --check-ledger
uv run cv-job validate
uv run cv-job audit-workspace
```

For another workspace, put `--config PATH` before each subcommand. The unified CLI checks documented settings types/choices, salary units, and overlapping accepted/excluded job kinds; it keeps supported legacy formats readable. Also check that known sample identity/experience has not been carried into a real profile and confirm actual country-specific authorization. A valid setting is not proof of a fact or consent. If rendering was requested, use a new private preview output; never overwrite a submitted artifact.

Report the chosen workspace, changed files, confirmed job scope and submission mode, deferred answers, and checks that passed or failed. Existing historical audit findings should be reported, not silently repaired. Summarize sensitive choices without echoing sensitive identity details.

Ask the user to confirm the setup summary. Distinguish "ready for CV preparation", "ready for application review", and "blocked pending source facts or setup". Optional unknowns need not block preparation; required unanswered questions block the affected application. Technical validation alone does not establish readiness. Setup confirmation is not authorization to submit, accept new legal terms, or begin unrelated mailbox access. On later runs, ask only for missing, changed, or job-specific answers rather than repeating onboarding.
