# Patchwork Isles World Bible

## Setting Snapshot
Patchwork Isles is an archipelago of floating biomes lashed together by songlines, trade, and guest-law. Each hub is a cultural knot where wind-scoured skylanes, living root courts, and prismatic guild towers intersect. The weather, architecture, and inhabitants are vibrant and adaptive, but the tone stays hopeful and clever—every problem has multiple angles and witty repartee is a currency.

**Tone & Themes**
- Hopeful problem-solving with character-driven stakes.
- Clever improvisation over brute force; focus on social, cunning, and care-based play.
- Vivid sensory description rooted in wind, light, living wood, and chorus-like resonance.

## Core Loop Overview
1. Arrive in a hub with a short vignette and 3–5 meaningful choices.
2. Spend tags, traits, items, or reputation to unlock different routes.
3. Earn new story state (flags), rep shifts, and gear to open the next hub.
4. Each hub resolves with a forward beat (new lead, resource, or ending) and never hard-locks.

## Tags (Core 12)
Social:
- **Diplomat** — Formal negotiations, protocol, leverage bureaucracies.
- **Trickster** — Sleight, bluffs, misdirection in social spaces.
- **Judge** — Interpret law, preside over hearings, render binding rulings.

Cunning:
- **Sneaky** — Stealth, infiltration, and ghosting obstacles.
- **Scout** — Navigation, environmental reading, safe pathfinding.
- **Tinkerer** — Repair, jury-rig, and refit technology.

Scholar:
- **Archivist** — Decode records, recall precedent, handle lore.
- **Cartographer** — Map strange routes, triangulate space.

Care / Magic:
- **Healer** — Treat injuries, stabilize people and systems.
- **Weaver** — Bind materials, people, or magic into resilient patterns.
- **Lumenar** — Bend or harness light-based energy.
- **Resonant** — Use vibration, music, and voice to sway forces or crowds.

Reserve 6 late-game upgrade tags; do not use or reference them yet.

## Traits (Starter Pool)
- **People-Reader** — Authors include one hidden branch per hub visible only with this trait; use for social insight or extra intel.
- **Light-Step** — Provide an alternate branch that bypasses the first tag gate encountered in a hub. It should read as agile improvisation, not teleportation.
- **Well-Provisioned** — Grants access to supply caches. Characters with the trait should reliably acquire or refresh a `favor` item that can be spent on tagless routes.
- **Rememberer's Boon** — Unlocks mirrored memories that let the character author an alternate branch of events once per chapter.

Traits are earned diegetically through choices (no menus). When granting a trait, consider pairing it with a resource or flag that motivates future branches.

## Items & Currencies
- **favor** — A tangible promise chit; spend to bypass a tag gate or hire aid.
- **prism shard** — Light-reflecting key used for Prism Guild proofs.
Additional items can appear later, but keep early inventory lean and purposeful.

## Factions & Reputation
Faction reputation ranges from −2 to +2 and is always earned diegetically.
- **Wind Choirs** — Skyward navigators that enforce guest-law aboard stormglass docks.
- **Root Court** — Arboreal magistrates who interpret contracts and living covenants.
- **Prism Guild** — Lenswrights and light engineers balancing innovation with control.
- **Freehands** — Cooperative smugglers and couriers maintaining unofficial routes.

Use reputation gates sparingly; when you do, ensure a tagless alternative remains available (perhaps at a cost).

## Authoring Rules (per node)
- 1–2 sentences of vivid prose establishing the scene.
- 3–5 choices.
- Include at least one tag-gated choice and at least one tagless route (which can be paid for with items, reputation, or flags).
- Never create a hard lock. Provide a no-tag option forward, even if it is costly.
- Multiple tags in a gate are ALL required using `{"type": "has_tag", "value": ["TagA", "TagB"]}`.
- Reference traits via `{"type": "has_trait", "value": "Trait"}` and honor their unique effects.
- Every choice must resolve cleanly: valid target node, appropriate effects, and no dangling references.

## Definition of Done Checklist (per node)
- [ ] Scene text is 1–2 evocative sentences.
- [ ] Choices list meets the rule of 3–5 and covers tag-gated + tagless routes.
- [ ] Optional gates (rep/item/flag) respect the "never hard-lock" guideline.
- [ ] All effects reference existing factions/items/traits.
- [ ] Choice targets exist; playtest from start reaches and exits the node cleanly.
- [ ] `tools/validate.py` passes on updated content.

## How to add a new unlockable start in 3 steps
1. **Author the start entry.** Add a new object to `world/world.json`'s `starts` list with `locked`: `true`, a `locked_title`, and the target `node` that should become the player's origin after unlock. Keep tags consistent with the world bible and make sure the node exists.
2. **Deliver the unlock diegetically.** Script the related hub arc so a single reward node (typically via `on_enter`) grants the start using an `{"type": "unlock_start", "value": "your_start_id"}` effect. Avoid duplicating the effect across multiple choices—route all completion branches through that reward beat.
3. **Wire QA and documentation.** Confirm the new start can be earned in play (playtest + `python tools/validate.py`), ensure it appears in the unlock audit list, and update any hub notes or docs that track available origins.

## Roadmap Notes
- First chapter hubs: **Sky Docks**, **Root Court Market**, **Prism Galleria**.
- Endings available in chapter one: escape via hidden canal or codify guest-law precedent.
- `/world/modules/` can eventually store hub-specific JSON chunks for collaboration; merge into `world/world.json` for shipping builds.
- Log playtest transcripts and observations in `/playtests/`.
