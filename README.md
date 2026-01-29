# Patchwork Isles

**Tag/Trait-driven narrative engine for weaving political intrigue across a living archipelago.**

> _Gameplay screenshot coming soon._

## Controls at a Glance
- Type the number or letter shown next to a choice and press <kbd>Enter</kbd> to advance the story.
- Enter `i` at any prompt to view your current tags, traits, inventory, and faction reputation.
- Enter `o` to open the Options screen for audio, display, and UI scale settings.
- Enter `h` to review the last few story beats, or `q` to quit to the title screen and optionally save.
- Accessibility settings (text speed, high contrast, reduced animations, caption-friendly cues) are documented in [`docs/accessibility.md`](docs/accessibility.md).

## Quick Start
1. **Install Python 3.9 or newer.** The engine is pure Python with no third-party dependencies required for runtime.
2. **Clone this repo and enter the folder.**
3. **(Optional) Create and activate a virtual environment.**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
4. **Install development tools (ruff, black, mypy, Pillow for placeholder art).**
   ```bash
   python -m pip install -r requirements-dev.txt
   ```
   > If you only want to play, you can skip installing dev tools.
5. **Run the engine.**
   ```bash
   python engine/engine_min.py world/world.json
   ```
6. **Validate content before committing changes.**
   ```bash
   python tools/validate.py
   ```

## Release Build (for players)
Create a zip that includes a single `.pyz` launcher plus `run.sh` / `run.bat` helpers:

```bash
python tools/build_release.py
```

Share the resulting `dist/Patchwork-Isles-YYYYMMDD.zip`. For step-by-step usage, see
[`docs/release.md`](docs/release.md).

## Folder Map
| Path | What lives here |
| --- | --- |
| `engine/` | The minimal interactive fiction engine (`engine_min.py`). |
| `world/` | Narrative content including `world.json` and modular story beats. |
| `docs/` | Lore bible, prompts, planning notes, and other supporting reference material. |
| `tools/` | Authoring utilities (`validate.py`, `list_unreachable.py`, `merge_modules.py`, etc.). |
| `playtests/` | Session transcripts and QA notes. |
| `profile.json` | Local save data storing unlocked starts and seen endings (generated on first run; ignored by git). |
| `profile.example.json` | Template profile to copy if you want a prefilled save file. |

## Roadmap (toward v0.9 Beta)
- [ ] Standalone quickstart world tailored for first-time players.
- [ ] Faction reputation UI polish and readable summaries.
- [ ] World authoring guidelines synced with in-game terminology.
- [ ] Automated content linting with CI (validate, ruff, mypy).
- [ ] Save-slot manager supporting multiple profiles.
- [ ] Balance pass on unlockable starts and faction rewards.
- [ ] Playtest feedback incorporation loop with tracked issues.
- [ ] Audio/visual dressing for key beats (accessibility friendly).
- [ ] Localization-ready strings and tooling.
- [ ] Spec: [v0.9 minimum playable beta](docs/planning/v0.9-min-playable-beta.md).

See [`docs/planning/v0.9-beta-backlog.md`](docs/planning/v0.9-beta-backlog.md) for the full milestone issue list.

## Authoring Quick Reference
- **Gate a choice by Tag:**
  ```json
  "condition": {"type": "has_tag", "value": "Sneaky"}
  ```
- **Require multiple Tags (ALL-of):**
  ```json
  "condition": {"type": "has_tag", "value": ["Weaver", "Diplomat"]}
  ```
- **Reward a Tag or Trait:**
  ```json
  {"type": "add_tag", "value": "Judge"}
  {"type": "add_trait", "value": "People-Reader"}
  ```
- **Use Reputation gates/rewards:**
  ```json
  "condition": {"type": "rep_at_least", "faction": "Root Court", "value": 1}
  {"type": "rep_delta", "faction": "Wind Choirs", "value": 1}
  ```
- **End the story:**
  ```json
  {"type": "end_game", "value": "Hidden Docks Escape"}
  ```
- **Unlock a new start:**
  1. Author the start entry in `world/world.json` with `locked: true`, a `locked_title`, and the destination `node`.
  2. Deliver the unlock via an `on_enter` reward node with `{ "type": "unlock_start", "value": "your_start_id" }`.
  3. Playtest the loop, run `python tools/validate.py`, and update any lists that track available origins.

> Always author at least one "tagless" path (e.g., trade an item or spend faction favor) so players are never hard-locked.

## Filing Bugs & Contributing
- Read the [Code of Conduct](CODE_OF_CONDUCT.md) and [Contributing Guide](CONTRIBUTING.md) before opening pull requests.
- Use the issue templates under `.github/ISSUE_TEMPLATE/` so we can triage bug, feature, and balance requests quickly.
- Track shipped features and fixes in the [Changelog](CHANGELOG.md).

## License
Patchwork Isles is released under the [MIT License](LICENSE).
