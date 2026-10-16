# cv-to-job

Use an AI agent to tailor CVs, apply for jobs, and track applications.

Keep a detailed master CV and make shorter versions for specific jobs. Real CVs, answers, and application history stay in an ignored `private/` folder. `sample/` contains fictional examples to copy and replace.

The repository is **cv-to-job**; the command is still `cv-job` and the config file is `cv-job.yaml`.

The agent workflow has been tested only with Codex. Other agents have not been verified. The Python CLI also works manually, without an agent.

## Use truthful information

I built this tool to help prepare and manage job applications, not to invent qualifications. Tailoring can change wording and emphasis, but should not change facts, titles, dates, experience, or results.

You are responsible for reviewing your applications and deciding what to submit. The checks can catch some mistakes; they cannot guarantee that an application is accurate.

## Start here with Codex

You do not need to learn TeX or YAML before starting. Codex can maintain those files; you supply facts, decide preferences, and review the documents and forms.

1. Download/extract this repository from GitHub, or clone it if you already use Git. Open the resulting project folder in Codex. The folder containing this README is the **repository root**.
2. Ask Codex: “Check the requirements for this project on my operating system. Explain what is missing and help me install it. Preserve any existing private folder and credentials.” The commands below are POSIX-shell examples; other platforms need adapted installation/activation commands. Do not paste shell commands into Python.
3. Use the included [apply-to-jobs skill](skills/apply-to-jobs/SKILL.md). You can ask Codex to read it directly, or install it for automatic discovery using [project or global setup](#skill-installation-project-or-global). No separate upstream adaptation is needed.
4. Give Codex your current PDF, Word CV, or TeX source and ask it to follow [guided initialization](docs/initialization.md). It should preserve the original, extract and confirm facts, create the master/ledger/base, and show you a PDF. If you have no CV, it should interview you first.
5. Once the readiness checks below are satisfied, start with **one job URL** using the [first-application prompt](#prepare-your-first-application).

Browser interaction, document extraction, Gmail, and secure credential entry depend on your Codex environment. Ask the agent to check what is actually available. Missing capabilities require a manual handoff—not a claim that the step was completed.

## The CVs you need

| Document | Why it exists | Suggested length | Location |
|---|---|---|---|
| Master CV | Your fuller record of employment, projects, responsibilities, tools, and supported results | Ideally about **3 pages** | `private/master_cv/` |
| Role-specific base | A reusable selection for a role family, such as infrastructure or security | 1–2 pages | `private/cv_bases/` |
| Job-specific CV | A copy of the closest base, tailored to one posting | 1–2 pages | That job's folder under `private/applications/` |
| Cover letter | Explain a useful connection between your experience and the job | 1 page; optional unless required | The same application folder |

Start with the master. Derive role-specific bases from it, then derive each job CV from the closest base. Select, trim, and reorder relevant experience. Keep official titles, dates, numbers, and factual scope intact. Do not automatically upload the master or overwrite it during tailoring.

Three pages is a working target for the master, not a validator requirement. Include enough detail to derive shorter CVs, without padding. The fictional sample is deliberately much shorter.

### Why there is an experience ledger

`experience.yaml` records which claims have support and what may appear in a CV. Supported bullets link to wording in the master. This helps stop an agent from turning a listed skill into an invented achievement.

| Evidence state | Allowed use |
|---|---|
| `unverified` | Unknown; do not claim it |
| `listed` | Skills line only |
| `candidate_confirmed` | Skills line only; detailed scope is not yet supported |
| `demonstrated` | Supported experience bullets |
| `quantified` | Supported bullets with the documented number |

TeX base/job bullets outside the skills block need a comment such as `% ev:linux_automation` referencing the ledger. Keep skills between `% skills:allowed` and `% skills:end`. See the [sample base](sample/cv_bases/example.tex) and [sample ledger](sample/experience.yaml). Validation checks these links and known wording; it does not prove every sentence is true. Review the CV yourself.

## Requirements

| Requirement | Needed for |
|---|---|
| Python 3.11+ | CLI, validation, application records, document helpers |
| [uv](https://docs.astral.sh/uv/), recommended | Installing locked Python dependencies and running commands |
| Tectonic **or** `pdflatex`, on `PATH` | Turning `.tex` CV source into PDF |
| Node.js 22+ with npm/npx | Skill installation via `npx skills`, plus the optional Gmail wrapper/tests |
| Codex + this repo's included `apply-to-jobs` skill | Agent-driven job search and applications; optional project/global install for discovery |
| Connected Gmail in Codex | Optional ATS signup, login, or submission email verification |

You can use pip in a virtual environment instead of uv. Gmail and an installed skill are not required for manual CV preparation or application-log commands.

Workspace settings live in `private/cv-job.yaml` and its referenced YAML files; the CLI does not load `.env` configuration. Existing private `.env` files may hold ATS login credentials—see [ATS login credentials](#ats-login-credentials). `.venv/` is the Python virtual environment, not a credential folder.

### TeX setup

`.tex` files are editable CV sources. PDFs are what you review and upload. Install one TeX engine separately; Python dependencies do not install it. The renderer prefers Tectonic when both are available, otherwise it uses `pdflatex`.

Check whichever engine you installed:

```bash
tectonic --version
# Or:
pdflatex --version
```

Your template's TeX packages and fonts must also be available. Tectonic may download missing resources on first use; `pdflatex` needs the corresponding packages in its TeX installation. A minimal installation may not contain everything a custom template uses. CI uses Tectonic 0.17.0.

## First-time setup

Run commands from the repository root.

### 1. Install Python dependencies

```bash
uv sync --frozen
```

Or use pip:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.txt` pins runtime dependencies from `uv.lock`. Development tools are in the `dev` group in `pyproject.toml`. With pip, use `cv-job` directly instead of `uv run cv-job` below. The activation command shown is for a POSIX shell.

### 2. Create the private folder

```bash
uv run cv-job init
```

This copies `sample/` to `private.migrating/`, compares file lists and SHA-256 hashes, then renames the verified copy to `private/`. It refuses an existing destination or staging path, including empty directories, files, and broken symlinks.

If `private/` already exists, resume or repair it—do not initialize again. `init` always creates the default workspace; it does not initialize a custom `--config` destination.

### 3. Replace the fictional data

Edit the copied YAML manually, or ask the agent:

> Initialize my cv-job workspace. Ask for missing information in small batches, preserve existing files, and confirm the setup before starting application work.

The agent follows the [initialization guide](docs/initialization.md): check existing files, ask about your identity/CV, job preferences, authorization, and consent choices, then save confirmed answers. You can defer unknown or sensitive answers. `cv-job init` itself only copies files; it is not a questionnaire.

Replace the fictional identity **and** sample employment, education, CV sources, and ledger before real applications. Passing sample validation does not make a workspace ready for personal use. Never copy sample accomplishments into your own experience.

### 4. Validate your workspace

```bash
uv run cv-job validate --check-ledger
uv run cv-job validate
uv run cv-job audit-workspace
```

Normal CV validation expects exactly one master `.tex` file and at least one base `.tex` file. Audit checks configured paths and application records/attachments. Review findings; do not delete historical records just to make the check pass.

## What goes where

These names follow the sample layout. `cv-job.yaml` selects the actual paths.

```text
private/                         # Ignored by Git: real candidate material
├── cv-job.yaml                  # Workspace location and file paths
├── AGENTS.md                    # Candidate-specific instructions
├── candidate.yaml               # Identity, contact, employment, education
├── experience.yaml              # Evidence and allowed claims
├── preferences.yaml             # Jobs, locations, salary, submission choices
├── ats_answers.yaml             # Screening answers, demographics, consent
├── applications.json            # Application records and history
├── master_cv/                   # Fuller master CV source
├── cv_bases/                    # Reusable role-specific CV sources
├── applications/                # Per-job postings, sources, and PDFs
├── previews/                    # Private draft previews
└── templates/                   # Workspace document templates
```

The sample preferences and answers contain YAML comments listing possible options. `null` means unknown, not “No”. Disclosure preferences are not identity claims. `validate` and `audit-workspace` check documented settings types/choices, salary units, and conflicting job kinds, while accepting supported legacy formats and unrelated extension fields. They do not establish factual truth, match jobs, or interpret legal consent wording. Compatibility scripts do not add these unified-CLI settings checks.

Commands default to `private/cv-job.yaml`. Select another config with `--config PATH` **before** the subcommand:

```bash
uv run cv-job --config sample/cv-job.yaml validate
```

The YAML `workspace` path is relative to the config file; `paths.*` are relative to that workspace. Older attachment references beginning with `private/` remain readable. New attachments should use workspace-relative paths.

## Render and review

### Application CVs: 1–2 pages

Try rendering the fictional base without touching your private workspace:

```bash
uv run cv-job --config sample/cv-job.yaml render tex \
  --in sample/cv_bases/example.tex --out /tmp/cv-job-sample.pdf
```

For real work, put the tailored source and PDF in that job's private application folder. The TeX renderer rejects PDFs outside **1–2 pages**. A rejected PDF may still exist at the output path; do not treat it as approved. Validate the source, inspect the PDF for clipping/readability, and check the selected attachment after upload.

### Master CV: compile directly

Do **not** use `cv-job render tex` for a three-page master: its application-CV page limit will reject it. Compile a draft preview with the engine directly. After initialization, for example:

```bash
tectonic --outdir private/previews private/master_cv/master.tex
# Or:
pdflatex -interaction=nonstopmode -output-directory=private/previews \
  private/master_cv/master.tex
```

Replace `master.tex` with your actual filename. Use a fresh preview location/name if an existing output needs preserving. Compile trusted TeX only. Direct engine commands do not run the project's claim or page-count checks.

### Other document helpers

`cv-job render resume` is a separate Markdown-to-PDF helper expecting exactly one page; it is not the TeX renderer. `cv-job render cover-letter` renders a one-page letter. Use each command's `--help` for its input format and options. An optional cover-letter upload field alone does not require writing a letter.

## Agent setup and applications

### Skill installation: project or global

The source is included at [skills/apply-to-jobs/](skills/apply-to-jobs/). Maintain changes there only. Both installation scopes are supported; installed copies are for discovery, not separate versions to edit. [Codex supports repository and user skill locations](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills).

| Scope | Location | Use when |
|---|---|---|
| Project, default for `npx skills add` | `.agents/skills/apply-to-jobs/` inside this checkout | You want the installation scoped to this project |
| Global, with `--global` | `~/.agents/skills/apply-to-jobs/` | You want this cv-job skill discoverable across projects |

First list existing installs. Preserve a customized installation rather than installing over it:

```bash
npx skills list --agent codex
npx skills list --agent codex --global
```

From this repository's root, install **our included version** using `.` as the source:

```bash
# Project-local:
npx skills add . --skill apply-to-jobs --agent codex
npx skills list --agent codex

# Or global:
npx skills add . --skill apply-to-jobs --agent codex --global
npx skills list --agent codex --global
```

`list` only lists skills. The install command copies/links the skill; it does not install Python or TeX, initialize personal data, connect Gmail, or authorize applications. Review [skill setup](docs/skill-setup.md) before replacing an existing customized installation. If discovery is stale, restart Codex. Do not merge same-named installs or update this workflow from the original upstream repository. After changing the maintained source, refresh the selected installed copy; a local install is not guaranteed to update automatically. Project installs remain ignored under `.agents/`.

The skill was adapted from **Luiz Felipe Barbosa's [job-application-skill](https://github.com/luizfelipebarbosa/job-application-skill)**. That link credits the original author; it is not the install target for cv-job. See [third-party attribution](THIRD_PARTY_NOTICES.md) and the retained [upstream MIT license](skills/apply-to-jobs/LICENSE).

The agent reads root `AGENTS.md` and the selected workspace's configured instructions. It checks prior applications, prepares documents, and reviews populated forms. `review_before_submit` is the sample default. Required unresolved answers prevent submission; setup confirmation alone is not submission permission.

```bash
uv run cv-job applications list
uv run cv-job applications show --id APPLICATION_ID
```

### Ready for the first application?

- Your real identity and experience replaced the fictional sample; you approved the extracted facts and reviewed the master/base PDFs.
- Target jobs, locations, and submission preferences are confirmed; unknown eligibility or required screening answers are clearly unresolved, not guessed.
- Workspace validation/audit passed, or existing findings have been explained and do not affect this job.
- The selected skill and needed browser access are available, or you have agreed which steps you will do manually.
- You know where the job-specific CV and record will be saved, and have a verified private backup.

### Prepare your first application

Give Codex a real posting URL:

> Prepare an application for this job: [URL]. Check my selected workspace and prior applications first. Ask about missing required answers, create and review the tailored CV, and stop before final submission. If browser access is unavailable, give me the CV and answers for manual application.

Expect a job-specific PDF and private application record, a prepared/reviewed form when browser access permits, and a short list of anything unresolved. Read the PDF and form yourself. Explicitly approve submission only when ready; a click or a requested verification code is not proof of success. You can begin with Greenhouse's tested direct flow below.

### Multiple agents

The code supports multiple agents working on applications. I tested two agents handing off one job and filling its form, without submitting it. I have not tested multiple agents filling and submitting applications at the same time. File locking and claim tests pass, but they do not guarantee that agents won’t submit the same application twice.

For multiple workers, follow [multiagent coordination](docs/multiagent.md): one shared-run coordinator, one owner per application, and short automatic file locks around JSON changes. Claim a job before working on it; a file lock alone does not prevent duplicate website submissions. Linux is tested locally; macOS CI coverage is configured and actual WSL2 verification remains a separate check. Keep WSL workspaces under `/home/...`, not a mixed Windows/WSL folder.

Claiming an existing application automatically includes it in the active run's reports without changing its original run. Use `applications show --id APPLICATION_ID` to inspect a complete record. Handoffs remain explicit release → claim.

### Tested websites

These are the websites reported as working with Codex in the maintainer's workflow, not a guarantee that every employer's form will work. Start with Greenhouse when you do not already have a preferred job site.

| Website | Account setup | Notes |
|---|---|---|
| Greenhouse — default starting option | No candidate signup needed for the tested direct application flow | Open the employer's Greenhouse job posting. An email security code may still be required; verification is separate from signup. |
| LinkedIn | Use an existing account, or sign up and sign in yourself | Ask the user to finish login or account challenges before continuing. A posting may redirect to an employer's external ATS; that destination can have different requirements. |

The agent should not create a LinkedIn account or ask for its password in chat. A tested website does not bypass the saved review/submission preference. Other ATS websites may work, but are not listed here as tested. Live Gmail retrieval through the wrapper has also been checked; this is not an automated end-to-end website test suite.

### Gmail and ATS verification

Connect Gmail in Codex if you want the agent to retrieve codes or links for the active ATS flow. Otherwise complete verification manually. Messages must match the recipient, request time, employer/ATS tenant, and event. Signup confirmation is not application-submission confirmation.

The [Gmail wrapper](docs/gmail.md) exposes read-only calls, runs them sequentially, leaves two seconds between requests, and retries rate limits at most twice. It uses exposed `Retry-After` headers or waits 30 then 60 seconds. Other failures pass through. After exhausted retries, report the unchecked scope—not “no email arrived”. The wrapper must be loaded in Codex's execution environment; it is not a standalone Gmail client or an automatic interception layer.

Do not save OTPs, tokens, or credentials in application records or YAML. User-only challenges or unresolved authentication block that job's flow. Record `applied` only after the browser confirms submission.

### ATS login credentials

Some existing workspaces keep employer-specific login details in private files such as `private/companies/<employer>/.env`. These files are separate from YAML settings and are not required for every site. Greenhouse's tested direct application flow does not require creating such a file.

Before creating or resetting an account, the agent checks relevant private account metadata, an available OS credential store, and existing credential-file locations. Git-ignored hidden files must be included in that presence check. Credentials must match the active employer/ATS tenant and application email.

Existing credential files are preserved as-is; setup does not move, rewrite, or migrate them. Never paste passwords into chat or dump a `.env` file into a terminal/tool response. Do not shell-source the file. Use a supported secure login method, or sign in yourself if the agent cannot enter credentials without exposing them. Prefer an OS credential store for newly saved passwords; never save OTPs in these files.

Keep any existing credential files under ignored `private/`, untracked, and owner-readable only (`600` on POSIX systems). A `.env` file is plaintext, not a vault; protect its backups too. The agent should report an unsafe permission/tracking state and ask before changing existing files. Do not commit these files or copy real credentials into examples.

## Privacy

Keep real candidate material under `private/`. The entire directory is ignored by Git. Do not commit personal CVs, logs, answers, postings, submitted documents, credentials, or screenshots. Keep `sample/` fictional and unchanged during real application work. Generated PDFs do not belong in public source files.

Git ignore is not encryption or a backup, and it does not remove files already committed. Check staged files before publishing and keep a separate verified backup of your private workspace.

### Backup and recovery

Follow [the backup guide](docs/backup.md) for exact commands to make a verified external copy, test restoration, and restore into a new checkout without overwriting a current workspace. The helper preserves credential bytes and child permissions and refuses existing destination/staging paths. Protect the backup: it may contain plaintext ATS passwords.

Cloning GitHub on another computer does **not** restore `private/`. Restore your backup before resuming applications; do not run `init` over recovered personal data.

### If setup gets stuck

| Problem | What to do |
|---|---|
| `uv`, `npx`, or a TeX engine is not found | Ask Codex to check the OS and propose the missing installation; restart the terminal/session if `PATH` changed |
| `init` refuses an existing path | Preserve it; ask Codex to inspect/resume it, not delete it |
| Missing TeX package or font | Give Codex the compile error, not credentials; install the template's required resources or choose a compatible template |
| Validation reports an evidence mismatch | Compare the claim with its source; do not invent facts or disable checks to make it pass |
| No browser/connector/secure login support | Complete that step manually and confirm the resulting state |
| YAML settings are rejected | Ask Codex to check the field's commented options and preserve existing answers while fixing the format |

## Checks and development

```bash
uv sync --frozen
uv run ruff check .
uv run pytest -q
node --test tests/gmail-wrapper.test.cjs
uv run cv-job --config sample/cv-job.yaml validate
uv run cv-job --config sample/cv-job.yaml audit-workspace
uv run cv-job --config sample/cv-job.yaml render tex \
  --in sample/cv_bases/example.tex --out /tmp/cv-job-sample-check.pdf
```

CI checks local code, the fictional sample, rendering, and fake-connector wrapper behavior. Live Gmail search/read has been checked with Codex; live rate-limit retries and end-to-end ATS submissions are not covered by CI.

Validation/audit return `0` on success, `1` for validation or audit errors, and `2` for configuration-loading errors. Legacy attachment paths alone are informational, not audit failures.

Compatibility entry points remain available:

```bash
uv run scripts/validate_claims.py --config sample/cv-job.yaml
uv run skills/apply-to-jobs/scripts/jobs.py --config sample/cv-job.yaml list
```

After dependency changes, regenerate pip requirements with:

```bash
uv export --frozen --no-dev --no-hashes --no-header --output-file requirements.txt
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution checks. Licensed under [MIT](LICENSE).
