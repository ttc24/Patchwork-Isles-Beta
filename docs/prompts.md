# Codex Prompt Library

Reusable prompt patterns for expanding the Patchwork Isles story world. Replace the placeholder tokens (such as `HUB_N`, `TAG_X`, or `FACTION_Y`) before sending a prompt to Codex. Every prompt below assumes the model already knows the base world pitch; prepend any extra lore snippets that are relevant to the module you are working on.

All prompts ask Codex to emit JSON that matches the engine schema:

- `nodes` is an object keyed by node IDs.
- Each node contains `title`, `text`, and a list of `choices` (3–4 choices unless noted otherwise).
- Each choice must include `text` and `target`, plus optional `condition` and `effects`.
<!-- schema-docs:start -->
- Allowed condition types: `has_item`, `missing_item`, `flag_eq`, `has_tag`, `has_advanced_tag`, `has_trait`, `rep_at_least`, `rep_at_least_count`, `profile_flag_eq`, `profile_flag_is_true`, `profile_flag_is_false`.
- Allowed effect types: `add_item`, `remove_item`, `set_flag`, `add_tag`, `add_trait`, `rep_delta`, `hp_delta`, `teleport`, `end_game`, `unlock_start`.
- Regenerate docs with `python tools/generate_schema_docs.py` when the schema spec changes.
<!-- schema-docs:end -->

Ask Codex to return only JSON—no commentary or Markdown—so the output can be dropped straight into a module file.

## “Add 10 nodes for HUB_N”
```
You are expanding the Patchwork Isles narrative. Add ten new story nodes for the hub called "HUB_N". Each node should:
- Have an ID that starts with "HUB_N" and describes the scene (e.g., "HUB_N_market_heist").
- Include a vivid `title` and `text` rooted in HUB_N's tone and motifs.
- Offer 3 or 4 choices. At least one choice should be available to all players (no condition), and at least one should be gated by a `has_tag` or `has_trait` condition.
- Reference existing factions, items, flags, and tags when useful; invent no new factions.
- Send the `target` to either another new node from this batch, an established HUB_N anchor node, or a known ending ID.

Use only the allowed condition and effect shapes listed above. Return JSON in the form:
{
  "nodes": {
    "NODE_ID": {
      "title": "...",
      "text": "...",
      "choices": [ { ... } ]
    },
    ...
  }
}
```

## “Create mentor micro-arc that unlocks TAG_X”
```
Design a compact mentor storyline that grants the player the tag "TAG_X". Produce 3–4 sequential nodes that introduce the mentor, test the player, and culminate in awarding the tag.

Constraints:
- Give the nodes IDs prefixed with "mentor_TAG_X_".
- Early choices can branch but should converge so the final node reliably offers a choice with an `add_tag` effect that gives "TAG_X".
- Use conditions (`has_tag`, `has_trait`, `flag_eq`, etc.) to reflect the mentor gauging the player. Include at least one optional challenge choice that yields faction reputation or an item.
- Direct targets so the micro-arc can both loop internally and hand off to an existing HUB node when it ends.

Return JSON shaped as `{ "nodes": { ... } }` using only the allowed condition and effect types.
```

## “Insert rep-gated options for FACTION_Y”
```
Augment existing nodes with reputation-gated choices for the faction "FACTION_Y". Provide a JSON object mapping node IDs to the new choices that should be appended to each node's `choices` list.

For every choice you add:
- Use a `rep_at_least` condition keyed to "FACTION_Y" with the minimum reputation required.
- Offer meaningful payoffs: extra `rep_delta`, special items, or shortcuts unlocked via `teleport`.
- Keep the `target` pointing at valid node IDs or endings that already exist.
- You may include optional secondary requirements such as `has_item` or `flag_eq` so long as the primary gate is reputation-based.

Example shape:
{
  "NODE_ID": [
    {
      "text": "(FACTION_Y Allies) ...",
      "condition": { "type": "rep_at_least", "faction": "FACTION_Y", "value": 1 },
      "effects": [ { "type": "rep_delta", "faction": "FACTION_Y", "value": 1 } ],
      "target": "some_node_id"
    }
  ]
}
Output only JSON that follows the allowed condition and effect rules.
```
