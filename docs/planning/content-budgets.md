# Content Budgets

This document defines content budgets for modules and chapters in Patchwork Isles. Budgets
are expressed as maximum node counts, choice counts, and word counts for prose and choice
text. The report tooling reads the JSON block below to compare the current world data
against these limits.

## Budget configuration

```json
{
  "modules": {
    "tutorial": {
      "node_prefixes": ["tutorial_"],
      "max_nodes": 12,
      "max_choices": 45,
      "max_words": 700
    },
    "sky": {
      "node_prefixes": ["sky_"],
      "max_nodes": 2,
      "max_choices": 12,
      "max_words": 140
    },
    "startways": {
      "node_prefixes": ["startways_"],
      "max_nodes": 2,
      "max_choices": 30,
      "max_words": 320
    },
    "nexus": {
      "node_prefixes": ["nexus_"],
      "max_nodes": 6,
      "max_choices": 30,
      "max_words": 500
    },
    "root": {
      "node_prefixes": ["root_"],
      "max_nodes": 16,
      "max_choices": 95,
      "max_words": 1200
    },
    "prism": {
      "node_prefixes": ["prism_"],
      "max_nodes": 2,
      "max_choices": 20,
      "max_words": 260
    },
    "guestlaw": {
      "node_prefixes": ["guestlaw_"],
      "max_nodes": 2,
      "max_choices": 8,
      "max_words": 120
    },
    "luminous": {
      "node_prefixes": ["luminous_"],
      "max_nodes": 2,
      "max_choices": 10,
      "max_words": 150
    },
    "mentor": {
      "node_prefixes": ["mentor_"],
      "max_nodes": 20,
      "max_choices": 75,
      "max_words": 1100
    },
    "amber": {
      "node_prefixes": ["amber_"],
      "max_nodes": 20,
      "max_choices": 85,
      "max_words": 1200
    },
    "cloud": {
      "node_prefixes": ["cloud_"],
      "max_nodes": 26,
      "max_choices": 105,
      "max_words": 1500
    },
    "shed": {
      "node_prefixes": ["shed_"],
      "max_nodes": 35,
      "max_choices": 140,
      "max_words": 2000
    },
    "saltglass": {
      "node_prefixes": ["saltglass_"],
      "max_nodes": 22,
      "max_choices": 95,
      "max_words": 1400
    },
    "starfallen": {
      "node_prefixes": ["starfallen_"],
      "max_nodes": 22,
      "max_choices": 85,
      "max_words": 1300
    },
    "moon": {
      "node_prefixes": ["moon_"],
      "max_nodes": 2,
      "max_choices": 8,
      "max_words": 120
    },
    "storm": {
      "node_prefixes": ["storm_"],
      "max_nodes": 2,
      "max_choices": 8,
      "max_words": 120
    },
    "orchard": {
      "node_prefixes": ["orchard_"],
      "max_nodes": 2,
      "max_choices": 6,
      "max_words": 110
    },
    "ending": {
      "node_prefixes": ["ending_"],
      "max_nodes": 36,
      "max_choices": 2,
      "max_words": 1600
    }
  },
  "chapters": {
    "chapter_one": {
      "module_ids": [
        "tutorial",
        "sky",
        "startways",
        "nexus",
        "root",
        "prism",
        "guestlaw",
        "luminous",
        "mentor"
      ],
      "max_nodes": 60,
      "max_choices": 320,
      "max_words": 4200
    },
    "chapter_two": {
      "module_ids": [
        "amber",
        "cloud",
        "shed",
        "saltglass",
        "starfallen",
        "moon",
        "storm",
        "orchard",
        "ending"
      ],
      "max_nodes": 160,
      "max_choices": 540,
      "max_words": 9000
    }
  }
}
```
