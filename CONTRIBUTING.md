# Contributing

- Keep the tool candidate-neutral. Candidate facts and policies belong in the selected workspace.
- Keep `sample/` entirely fictional. Do not copy real application history, job postings, documents, or contact information into it.
- Add regression tests for behavior changes and run Ruff and pytest.
- Do not commit generated PDFs, credentials, private configuration, or files from `private/`.
- Preserve compatibility for existing application logs and their recorded attachment paths.
- Maintain the adapted application skill in `skills/apply-to-jobs/`; project/global installs are copies for discovery, not separate sources to edit. Preserve upstream attribution/license and refresh installed copies deliberately after reviewing changes.
