# Tailored documents

Use the selected workspace's master CV, evidence ledger, candidate records, configured bases, and writing preferences. Keep the master unchanged. Prefer selecting, trimming, and reordering supported base wording; stronger phrasing must preserve factual scope, official employment titles, tools, numbers, duration, and design/test/production distinctions. A target-role headline does not change an employment title.

Each resume bullet outside the skills block needs `% ev:<id>` for a `demonstrated` or `quantified` record. Place permitted skills-only claims between `% skills:allowed` and `% skills:end`. `listed` and `candidate_confirmed` do not establish production depth or years; `unverified` is unknown and must not appear as a claim. Validate structure and known claims, then compare changed wording semantically with the sources: validator success does not establish factual truth.

Use a cover letter when required or when it explains a concrete experience-to-role connection. An optional upload field alone does not require one. Prefer the selected workspace's template and house style; otherwise use [the generic template](../assets/cover-letter.template.md). Replace placeholders and use supported examples rather than invented enthusiasm, metrics, or experience. Compare factual statements with both the resume and ledger.

Run commands from the selected project root, carrying `--config PATH` before the command for a non-default workspace:

```bash
uv run cv-job validate <application-folder>/resume.tex
uv run cv-job validate --cover-letter <application-folder>/cover_letter.md
uv run cv-job render tex --in <application-folder>/resume.tex --out <application-folder>/resume.pdf
uv run cv-job render cover-letter --in <application-folder>/cover_letter.md --out <application-folder>/cover_letter.pdf
```

Use the TeX renderer for TeX CV bases. The CLI's Markdown resume renderer is a compatibility tool, not a replacement for a configured TeX base. Inspect rendered PDFs for layout, clipping, page count, and unresolved placeholders; follow workspace page-length preferences. Keep sources, PDFs, and previews in the application folder. Preserve already-submitted artifacts byte-for-byte and use a new filename for a revision. Record the selected base, attachment paths, unresolved facts, and completed form check in the application log.
