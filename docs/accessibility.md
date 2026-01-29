# Accessibility Options

Patchwork Isles ships with accessibility-focused settings so players can tune readability, reduce motion, and keep important cues visible in a text-only presentation.

## Defaults
- **Text speed:** `1.0x` (baseline reveal speed).
- **High contrast:** `Off`.
- **Reduce animations/flicker:** `Off`.
- **Caption audio cues:** `Off`.

These defaults preserve the existing terminal pacing and layout while letting players opt into more accessible presentation.

## Intent and Behavior
- **Text speed** controls how quickly narrative lines and effect messages reveal. Set to `0` for instant output.
- **High contrast** increases visual emphasis by using stronger separators, uppercase headers, and clearer choice markers.
- **Reduce animations/flicker** disables text reveal delays entirely, useful for players sensitive to motion or flicker.
- **Caption audio cues** prints short, bracketed cues alongside effect messages so sound-like feedback (rewards, state changes) stays readable.

All options are available from the in-game Options menu and persist across sessions via `settings.json`.
