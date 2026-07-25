---
name: bubblehub-release-notes
description: Write BubbleHub release notes from git commits using the repository release template. Use when preparing a BubbleHub release, creating release notes, filling .github/release_template.md, summarizing commits since the last tag, or publishing release announcements. Always finish with the bash commands to commit the notes and push the release tag.
---

# BubbleHub Release Notes

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

4. Read contributor names from the actual commit range, including commit authors and co-authors:

```bash
git log --format='%an <%ae>%n%B' <previous-tag>..HEAD
```

5. Read `.github/release_template.md`.
6. Replace `vX.Y.Z` and `X.Y.Z` placeholders with the target tag/version.
7. Fill the template with concise, user-facing notes grouped into:
   - New Features
   - Improvements
   - Bug Fixes
   - Security & Sandboxing
8. Save the finished notes to:

```text
.github/releases/<target-tag>.md
```

Example:

```text
.github/releases/v0.1.0.md
```

9. Before committing or tagging, update release-facing docs and examples for the target version. At minimum, check `README.md`, `docs/`, and installation/package examples for the previous tag or version:

```bash
rg '<previous-tag>|<previous-version>' README.md docs .github
```

Update stale release commands, Docker image tags, download URLs, installer filenames, and package examples to the target tag/version. The release tag must point at a commit that already includes these docs updates.

10. After saving the notes and docs updates, inspect the current branch and remotes before writing publish commands:

```bash
git branch --show-current
git remote -v
git remote get-url origin
git remote get-url upstream
git rev-parse --abbrev-ref --symbolic-full-name @{u}
```

If `upstream` does not exist, ignore that command's failure. Do not assume `origin` is the release remote; in forked checkouts, `origin` is usually the user's fork and `upstream` is usually the project repository.

11. After saving the notes and docs updates, always tell the user how to publish the release. End your response with a **Next step** section containing the exact bash commands to run.

The release workflow triggers on a pushed `v*` tag and uses `.github/releases/<tag>.md` from that commit. The notes file must be committed before tagging.

Use this pattern after replacing `<changed-release-files>`, `<release-remote>`, `<branch>`, and `<tag>` with values from the actual file/remote/branch context:

```bash
git add <changed-release-files>
git commit -m "Add release notes for <tag>"
git push <release-remote> <branch>
git tag <tag>
git push <release-remote> <tag>
```

Before giving these commands:

- Confirm CI is green on the commit you are about to tag.
- Confirm `README.md` and other user-facing docs no longer contain stale release versions, URLs, Docker tags, package filenames, or install commands for the previous release.
- Identify the release remote from `git remote -v`; prefer the project repository remote that owns the release workflow, not a fork remote. If the checkout only has a fork remote, say so and give PR/coordination steps instead of tag-push commands to the fork.
- Use the current branch name in `git push <release-remote> <branch>`; do not use `HEAD` when a concrete branch name is available.
- If `<tag>` already exists locally or on the remote, say so and do not repeat create/push tag commands blindly.

Keep the command block copy-pasteable. Do not omit this section when the user asked for release notes.

## Rules

- Write for users, not only maintainers.
- Mention the Docker image when release work includes container publishing.
- Keep bullets concrete and based on commits.
- Do not invent changes not supported by commit history.
- Prefer short `BubbleHub.ai` download links in release notes:
  - Latest asset base: `https://BubbleHub.ai/download/latest`
  - Version asset base: `https://BubbleHub.ai/download/<tag>`
  - Linux installer: `https://BubbleHub.ai/install.sh`
  - Windows installer: `https://BubbleHub.ai/install.ps1`
- Use versioned filenames in package examples, for example `BubbleHub-0.1.0-x64.deb` and `BubbleHub-0.1.0-x64.exe`.
- Preserve the installation section structure from `.github/release_template.md`.
- Keep GitHub links for repository context, not for primary install commands.
- In the Contributors section, thank specific human contributors from the actual commits in the release range. Exclude Daniel Bransky, dBransky, Copilot, copilot-swe-agent, and any other bot account. Never thank Copilot.

The release workflow uses `.github/releases/<tag>.md` when present. If the file is absent, GitHub generated release notes are used as a fallback.
