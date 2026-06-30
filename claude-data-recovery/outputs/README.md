# outputs/ — local & dry-run collection output (GITIGNORED)

This folder is where the collector writes when you point it here (e.g. a
`--dry-run` or local test on your own machine, instead of a real USB drive).

> ⚠️ **Everything in this folder except this README is git-ignored on purpose.**
> A collected backup contains full Claude Code transcripts, pasted content, and
> **live OAuth credentials**. It must **never** be committed or pushed — not by
> you, not by a teammate, not by accident.

The ignore rules live in the repo-root `.gitignore`:

```gitignore
claude-data-recovery/outputs/*
!claude-data-recovery/outputs/README.md
claude-backup/
__SECRETS__/
```

In real use, the tool defaults its output to a `claude-backup\` folder on the
**drive it is launched from** (the flash drive). This `outputs/` folder is only
for safe local testing.
