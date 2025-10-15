# Contributing to Patchwork Isles

Thanks for helping expand the archipelago! This guide explains how to set up your environment, propose changes, and keep the narrative engine healthy.

## Getting Started
1. **Fork the repository** and create a topic branch from `main` (e.g., `feature/add-new-faction`).
2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r requirements-dev.txt
   ```
3. **Install runtime dependencies.** The engine currently has no additional dependencies beyond Python 3.8+, but playtest tools may evolve. Check `tools/` for helper scripts.

## Development Workflow
1. **Write or update content/assets** under `world/`, `docs/`, or other relevant folders.
2. **Run the narrative validator** to catch structural issues:
   ```bash
   python tools/validate.py
   ```
3. **Format and lint your changes:**
   ```bash
   black .
   ruff check .
   mypy engine tools
   ```
4. **Playtest** your change path-by-path when authoring new content. Attach transcripts in `playtests/` if you discover bugs or design questions.
5. **Commit with a clear message** (e.g., `Add Reef Herald introduction arc`).
6. **Open a pull request** describing the change, linking to any relevant issues or milestone work.

## Coding & Content Guidelines
- Keep node IDs stable; avoid breaking save data without a migration plan.
- Faction names, tag spellings, and lore details should match `docs/world_bible.md`.
- Always include at least one accessible (tagless) path through new branches.
- Use `tools/list_unreachable.py` when adding new modules to ensure everything is hooked up.
- For large features, break the work into smaller PRs and reference the milestone issue.

## Reporting Issues
Please use the templates under `.github/ISSUE_TEMPLATE/` so maintainers can triage quickly. Include:
- Steps to reproduce
- Expected vs. actual behavior
- Screenshots or transcripts when available
- Save data snippets if relevant (redact personal info)

## Release Process
1. Update `CHANGELOG.md` with the new version under `## [Unreleased]`.
2. Tag the release (e.g., `v0.9.0-beta1`) after merging.
3. Publish release notes summarizing highlights and linking to playtest coverage.

Questions? Reach out in the issue tracker or email the maintainers at [patchwork-isles-maintainers@proton.me](mailto:patchwork-isles-maintainers@proton.me).
