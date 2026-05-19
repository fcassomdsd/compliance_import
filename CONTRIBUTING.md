# Contributing Guide

Thank you for contributing to this repository.

Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before participating.

## 1. Branch Workflow

This project uses a `main` / `develop` model:

- `main`: stable and production-ready.
- `develop`: active development branch. Open merge requests to `develop` unless instructed otherwise.
- `feature/*`: new features, for example `feature/add-followup-metrics`.
- `fix/*`: bug fixes, for example `fix/followup-evidence-validation`.
- `hotfix/*`: urgent fixes for production.

Example workflow:

```bash
# 1. Start from develop
git checkout develop
git pull

# 2. Create a branch
git checkout -b feature/awesome-improvement

# 3. Make changes and commit
git add .
git commit -m "feat: add awesome improvement"

# 4. Push branch
git push origin feature/awesome-improvement
```

Then open a merge request to `develop`.

## 2. Code Style and Quality

Keep changes focused and easy to review:

- Follow existing coding style in the touched files.
- Prefer small, single-purpose pull requests.
- Update documentation when behavior or contracts change.
- Add or update tests when changing logic.

## 3. Commit Message Convention

Use Conventional Commits:

- `feat:` new feature
- `fix:` bug fix
- `chore:` maintenance/tooling/dependency updates
- `docs:` documentation-only changes
- `test:` tests added/updated
- `refactor:` internal restructuring without behavior changes

Examples:

- `feat: add follow-up filename list to API response`
- `fix: validate missing FollowUpEvidence files`
- `docs: clarify follow-up payload structure`

Avoid vague messages such as `update stuff`.

## 4. Testing

Run tests locally before opening a merge request:

```bash
venv/bin/python -m unittest discover -s tests -v
```

If your environment uses `.venv`, adapt the command accordingly.

## 5. Merge Request Checklist

Include in your merge request description:

- Summary: what changed and why.
- Type: feat, fix, docs, refactor, test, or chore.
- Testing: commands executed and results.

Checklist:

- [ ] My code follows the existing style and project patterns.
- [ ] I performed a self-review of my changes.
- [ ] I updated documentation where needed.
- [ ] New and existing tests pass locally.
- [ ] Commit messages follow Conventional Commits.

## 6. SPDX and Copyright Headers

For new source files, include an SPDX license identifier and copyright line
at the top of the file when appropriate.

Recommended header:

```text
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fernando A. Casso Rodriguez
```

Notes:

- Use comment syntax that matches the file type (`#`, `//`, `/* ... */`, etc.).
- Keep existing third-party license headers intact when present.
- Do not remove or alter upstream copyright notices.
