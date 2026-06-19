---
name: ageos-release-notes
description: Write AgeOS release notes from git commits using the repository release template. Use when preparing an AgeOS release, creating release notes, filling .github/release_template.md, summarizing commits since the last tag, or publishing release announcements.
---

# AgeOS Release Notes

## Workflow

When preparing a release, write the release notes yourself from git history:

1. Determine the target tag from the user or branch context, for example `v0.1.0`.
2. Find the previous release tag:

```bash
git describe --tags --abbrev=0 <target-tag>^
```

If the target tag does not exist yet, use the latest existing tag as the previous release.

3. Read commits since the previous release:

```bash
git log --oneline <previous-tag>..HEAD
```

4. Read `.github/release_template.md`.
5. Fill the template with concise, user-facing notes grouped into:
   - New Features
   - Improvements
   - Bug Fixes
   - Security & Sandboxing
6. Save the finished notes to:

```text
.github/releases/<target-tag>.md
```

Example:

```text
.github/releases/v0.1.0.md
```

## Rules

- Write for users, not only maintainers.
- Mention the Docker image when release work includes container publishing.
- Keep bullets concrete and based on commits.
- Do not invent changes not supported by commit history.
- Preserve the install commands and links from `.github/release_template.md`.

The release workflow uses `.github/releases/<tag>.md` when present. If the file is absent, GitHub generated release notes are used as a fallback.
