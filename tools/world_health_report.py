#!/usr/bin/env python3
"""Generate a world health report for Patchwork Isles."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORLD = REPO_ROOT / "world" / "world.json"
DEFAULT_BUDGET_DOC = REPO_ROOT / "docs" / "planning" / "content-budgets.md"
DEFAULT_JSON_OUT = REPO_ROOT / "world_health_report.json"
DEFAULT_MD_OUT = REPO_ROOT / "world_health_report.md"

TAG_GATING_TYPES = {"has_tag", "has_trait", "has_advanced_tag"}
LOCALIZATION_KEY_FIELDS = {"loc_key", "loc_id", "localization_key"}
WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)


@dataclass
class BudgetStats:
    nodes: int = 0
    choices: int = 0
    words: int = 0


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def count_words(text: str | None) -> int:
    if not text:
        return 0
    return len(WORD_RE.findall(text))


def collect_teleport_targets(effects: object) -> list[str]:
    if not effects:
        return []
    if isinstance(effects, dict):
        effects_list = [effects]
    elif isinstance(effects, list):
        effects_list = effects
    else:
        return []
    targets = []
    for effect in effects_list:
        if not isinstance(effect, dict):
            continue
        if effect.get("type") != "teleport":
            continue
        target = effect.get("target")
        if isinstance(target, str):
            targets.append(target)
    return targets


def build_graph(world: dict) -> tuple[dict[str, list[str]], list[str]]:
    nodes = world.get("nodes", {})
    graph = {node_id: [] for node_id in nodes}
    missing_targets: list[str] = []

    for node_id, node in nodes.items():
        for target in collect_teleport_targets(node.get("on_enter")):
            graph[node_id].append(target)
            if target not in nodes:
                missing_targets.append(f"Node {node_id} teleports to missing node {target}")
        for choice in node.get("choices", []) or []:
            target = choice.get("target")
            if isinstance(target, str):
                graph[node_id].append(target)
                if target not in nodes:
                    missing_targets.append(
                        f"Node {node_id} choice targets missing node {target}"
                    )
            for target in collect_teleport_targets(choice.get("effects")):
                graph[node_id].append(target)
                if target not in nodes:
                    missing_targets.append(f"Node {node_id} teleports to missing node {target}")
    return graph, missing_targets


def traverse_from(start_node: str, graph: dict[str, list[str]]) -> set[str]:
    if start_node not in graph:
        return set()
    visited = set()
    stack = [start_node]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        stack.extend(graph.get(current, []))
    return visited


def iter_conditions(condition: Any) -> Iterable[dict[str, Any]]:
    if isinstance(condition, list):
        for entry in condition:
            yield from iter_conditions(entry)
    elif isinstance(condition, dict):
        yield condition
        nested = condition.get("conditions")
        if isinstance(nested, list):
            for entry in nested:
                yield from iter_conditions(entry)


def is_tag_gated(condition: Any) -> bool:
    if condition is None:
        return False
    return any(item.get("type") in TAG_GATING_TYPES for item in iter_conditions(condition))


def has_localization_key(entry: dict, field_name: str) -> bool:
    if any(key in entry for key in LOCALIZATION_KEY_FIELDS):
        return True
    return f"{field_name}_key" in entry


def collect_missing_localization(world: dict, max_entries: int) -> dict[str, Any]:
    missing: list[dict[str, str]] = []
    total_missing = 0

    def record(path: str, text_value: str, entry: dict, field: str) -> None:
        nonlocal total_missing
        if has_localization_key(entry, field):
            return
        total_missing += 1
        if len(missing) < max_entries:
            missing.append({"path": path, "text": text_value})

    world_title = world.get("title")
    if isinstance(world_title, str):
        record("title", world_title, world, "title")

    for start in world.get("starts", []) or []:
        if not isinstance(start, dict):
            continue
        for field in ("title", "locked_title", "blurb"):
            value = start.get(field)
            if isinstance(value, str):
                record(f"starts.{start.get('id', '<unknown>')}.{field}", value, start, field)

    for node_id, node in world.get("nodes", {}).items():
        if not isinstance(node, dict):
            continue
        for field in ("title", "text"):
            value = node.get(field)
            if isinstance(value, str):
                record(f"nodes.{node_id}.{field}", value, node, field)
        for index, choice in enumerate(node.get("choices", []) or []):
            if not isinstance(choice, dict):
                continue
            value = choice.get("text")
            if isinstance(value, str):
                record(f"nodes.{node_id}.choices[{index}].text", value, choice, "text")

    endings = world.get("endings", {})
    if isinstance(endings, dict):
        for key, value in endings.items():
            if not isinstance(value, str):
                continue
            total_missing += 1
            if len(missing) < max_entries:
                missing.append({"path": f"endings.{key}", "text": value})

    return {
        "count": total_missing,
        "examples": missing,
        "limit": max_entries,
    }


def parse_budget_doc(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    match = re.search(r"```json\s*(\{.*\})\s*```", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def gather_module_stats(world: dict, node_prefixes: list[str]) -> BudgetStats:
    stats = BudgetStats()
    nodes = world.get("nodes", {})
    for node_id, node in nodes.items():
        if not isinstance(node_id, str) or not isinstance(node, dict):
            continue
        if not any(node_id.startswith(prefix) for prefix in node_prefixes):
            continue
        stats.nodes += 1
        stats.words += count_words(node.get("title"))
        stats.words += count_words(node.get("text"))
        for choice in node.get("choices", []) or []:
            if not isinstance(choice, dict):
                continue
            stats.choices += 1
            stats.words += count_words(choice.get("text"))
    return stats


def compare_budget(stats: BudgetStats, budget: dict[str, Any]) -> dict[str, Any]:
    overages = {}
    for key, value in (
        ("nodes", budget.get("max_nodes")),
        ("choices", budget.get("max_choices")),
        ("words", budget.get("max_words")),
    ):
        if isinstance(value, int) and getattr(stats, key) > value:
            overages[key] = getattr(stats, key) - value
    return {
        "stats": {"nodes": stats.nodes, "choices": stats.choices, "words": stats.words},
        "budget": budget,
        "over_budget": bool(overages),
        "overages": overages,
    }


def build_content_budget_report(world: dict, budget_doc: Path) -> dict[str, Any]:
    budgets = parse_budget_doc(budget_doc)
    if not budgets:
        return {"errors": [f"No JSON budget block found in {budget_doc}."]}

    report: dict[str, Any] = {"modules": {}, "chapters": {}, "doc_path": str(budget_doc)}
    modules = budgets.get("modules", {}) if isinstance(budgets, dict) else {}
    module_stats_cache: dict[str, BudgetStats] = {}

    for module_id, module_budget in modules.items():
        if not isinstance(module_budget, dict):
            continue
        prefixes = module_budget.get("node_prefixes")
        if not isinstance(prefixes, list) or not prefixes:
            report.setdefault("errors", []).append(
                f"Module {module_id} has no node_prefixes configured."
            )
            continue
        stats = gather_module_stats(world, prefixes)
        module_stats_cache[module_id] = stats
        report["modules"][module_id] = compare_budget(stats, module_budget)

    chapters = budgets.get("chapters", {}) if isinstance(budgets, dict) else {}
    for chapter_id, chapter_budget in chapters.items():
        if not isinstance(chapter_budget, dict):
            continue
        module_ids = chapter_budget.get("module_ids")
        if not isinstance(module_ids, list) or not module_ids:
            report.setdefault("errors", []).append(
                f"Chapter {chapter_id} has no module_ids configured."
            )
            continue
        totals = BudgetStats()
        missing_modules = []
        for module_id in module_ids:
            stats = module_stats_cache.get(module_id)
            if stats is None:
                missing_modules.append(module_id)
                continue
            totals.nodes += stats.nodes
            totals.choices += stats.choices
            totals.words += stats.words
        chapter_report = compare_budget(totals, chapter_budget)
        if missing_modules:
            chapter_report["missing_modules"] = missing_modules
        report["chapters"][chapter_id] = chapter_report

    return report


def build_markdown(report: dict[str, Any]) -> str:
    missing_loc = report["missing_localization"]
    tag_gate = report["tag_gate_density"]
    content_budgets = report.get("content_budgets", {})

    lines = ["# World Health Report", ""]
    lines.append(f"Generated: {report['generated_at']}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- World file: `{report['world_path']}`")
    lines.append(f"- Total nodes: {report['node_count']}")
    lines.append(f"- Unreachable nodes: {len(report['unreachable_nodes'])}")
    lines.append(f"- Missing targets: {len(report['missing_targets'])}")
    lines.append(f"- Dead ends: {len(report['dead_ends'])}")
    lines.append(f"- Average branching factor: {report['average_branching_factor']:.2f}")
    lines.append(
        f"- Tag-gate density: {tag_gate['tag_gated_choices']}/{tag_gate['total_choices']} "
        f"({tag_gate['density']:.2%})"
    )
    lines.append("")

    def add_list_section(title: str, items: list[str]) -> None:
        lines.append(f"## {title}")
        if not items:
            lines.append("- None")
        else:
            for item in items:
                lines.append(f"- {item}")
        lines.append("")

    add_list_section("Unreachable Nodes", report["unreachable_nodes"])
    add_list_section("Missing Targets", report["missing_targets"])
    add_list_section("Dead Ends", report["dead_ends"])

    lines.append("## Missing Localization Keys")
    lines.append(f"- Total missing entries: {missing_loc['count']}")
    lines.append(f"- Showing up to {missing_loc['limit']} examples")
    for entry in missing_loc["examples"]:
        lines.append(f"  - `{entry['path']}`: {entry['text']}")
    lines.append("")

    lines.append("## Content Budgets")
    if content_budgets.get("errors"):
        lines.append("- Errors:")
        for error in content_budgets["errors"]:
            lines.append(f"  - {error}")
    modules = content_budgets.get("modules", {})
    if modules:
        lines.append("### Modules")
        for module_id, module_report in modules.items():
            status = "OVER" if module_report["over_budget"] else "OK"
            stats = module_report["stats"]
            budget = module_report["budget"]
            lines.append(
                f"- **{module_id}**: {status} "
                f"(nodes {stats['nodes']}/{budget.get('max_nodes')}, "
                f"choices {stats['choices']}/{budget.get('max_choices')}, "
                f"words {stats['words']}/{budget.get('max_words')})"
            )
            if module_report["overages"]:
                lines.append(f"  - Overages: {module_report['overages']}")
    chapters = content_budgets.get("chapters", {})
    if chapters:
        lines.append("### Chapters")
        for chapter_id, chapter_report in chapters.items():
            status = "OVER" if chapter_report["over_budget"] else "OK"
            stats = chapter_report["stats"]
            budget = chapter_report["budget"]
            lines.append(
                f"- **{chapter_id}**: {status} "
                f"(nodes {stats['nodes']}/{budget.get('max_nodes')}, "
                f"choices {stats['choices']}/{budget.get('max_choices')}, "
                f"words {stats['words']}/{budget.get('max_words')})"
            )
            if chapter_report.get("missing_modules"):
                lines.append(
                    f"  - Missing modules: {', '.join(chapter_report['missing_modules'])}"
                )
            if chapter_report["overages"]:
                lines.append(f"  - Overages: {chapter_report['overages']}")
    lines.append("")

    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a world health report.")
    parser.add_argument(
        "--world-path",
        default=str(DEFAULT_WORLD),
        help="Path to the compiled world JSON file.",
    )
    parser.add_argument(
        "--budget-doc",
        default=str(DEFAULT_BUDGET_DOC),
        help="Path to the content budgets markdown file.",
    )
    parser.add_argument(
        "--json-out",
        default=str(DEFAULT_JSON_OUT),
        help="Path to write the JSON report.",
    )
    parser.add_argument(
        "--markdown-out",
        default=str(DEFAULT_MD_OUT),
        help="Path to write the Markdown report.",
    )
    parser.add_argument(
        "--max-missing-localization",
        type=int,
        default=50,
        help="Maximum missing localization entries to include in the report.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv[1:])
    world_path = Path(args.world_path).resolve()
    budget_doc = Path(args.budget_doc).resolve()

    try:
        world = load_json(world_path)
    except json.JSONDecodeError as exc:
        print(f"Failed to parse JSON from {world_path}: {exc}")
        return 1

    graph, missing_targets = build_graph(world)
    starts = world.get("starts", [])
    all_reached: set[str] = set()
    for start in starts:
        if not isinstance(start, dict):
            continue
        node = start.get("node")
        if not isinstance(node, str):
            continue
        all_reached.update(traverse_from(node, graph))

    unreachable = sorted(set(graph.keys()) - all_reached)
    dead_ends = sorted([node_id for node_id, edges in graph.items() if not edges])

    total_choices = 0
    tag_gated_choices = 0
    for node in world.get("nodes", {}).values():
        if not isinstance(node, dict):
            continue
        for choice in node.get("choices", []) or []:
            if not isinstance(choice, dict):
                continue
            total_choices += 1
            if is_tag_gated(choice.get("condition")):
                tag_gated_choices += 1

    edge_count = sum(len(edges) for edges in graph.values())
    average_branching_factor = edge_count / len(graph) if graph else 0.0

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "world_path": str(world_path),
        "node_count": len(graph),
        "unreachable_nodes": unreachable,
        "missing_targets": sorted(set(missing_targets)),
        "dead_ends": dead_ends,
        "missing_localization": collect_missing_localization(
            world, args.max_missing_localization
        ),
        "tag_gate_density": {
            "tag_gated_choices": tag_gated_choices,
            "total_choices": total_choices,
            "density": (tag_gated_choices / total_choices) if total_choices else 0.0,
        },
        "average_branching_factor": average_branching_factor,
        "content_budgets": build_content_budget_report(world, budget_doc),
    }

    json_out_path = Path(args.json_out)
    json_out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    markdown_out_path = Path(args.markdown_out)
    markdown_out_path.write_text(build_markdown(report), encoding="utf-8")

    print(f"JSON report written to {json_out_path}")
    print(f"Markdown report written to {markdown_out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
