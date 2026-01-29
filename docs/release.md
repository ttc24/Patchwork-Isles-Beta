# Release Builds (Player-Friendly)

This project ships as a single zip that contains a self-contained `.pyz` launcher plus
simple `run.sh` / `run.bat` scripts.

## Build a release zip

From the repo root:

```bash
python tools/build_release.py
```

Artifacts land in `dist/` as `Patchwork-Isles-YYYYMMDD.zip`.

### Optional flags

```bash
python tools/build_release.py --tag v0.9-beta
python tools/build_release.py --output-dir /tmp/releases
python tools/build_release.py --name Patchwork-Isles-Beta
```

## Run the game (no setup)

1. Unzip the release archive.
2. Launch:
   - **macOS/Linux:** double-click `run.sh` or run `./run.sh` from a terminal.
   - **Windows:** double-click `run.bat`.
3. The launcher runs `Patchwork-Isles.pyz` using your system Python 3.9+.

> If Python is not installed, download it from https://www.python.org/downloads/ and
> re-run the launcher.

## Beta drop cadence

We ship **beta drops biweekly** (every two weeks). Each drop includes:
- a tagged build in `dist/`,
- a short changelog summary,
- a playtest packet link for structured feedback.

If a drop needs to slip, we still post a short update so playtesters know when to expect the next build.
