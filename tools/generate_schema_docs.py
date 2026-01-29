"""Update documentation blocks that list allowed schema types."""

from __future__ import annotations

from pathlib import Path

from engine import world_schema

MARKER_START = "<!-- schema-docs:start -->"
MARKER_END = "<!-- schema-docs:end -->"


def _format_type_list(types: list[str]) -> str:
    return ", ".join(f"`{type_name}`" for type_name in types)


def _render_block() -> str:
    condition_types = list(world_schema.CONDITION_SPECS.keys())
    effect_types = list(world_schema.EFFECT_SPECS.keys())
    return "\n".join(
        [
            f"- **Allowed condition types:** {_format_type_list(condition_types)}",
            f"- **Allowed effect types:** {_format_type_list(effect_types)}",
            "- _Regenerate docs with `python tools/generate_schema_docs.py` when the schema spec changes._",
        ]
    )


def _render_prompts_block() -> str:
    condition_types = list(world_schema.CONDITION_SPECS.keys())
    effect_types = list(world_schema.EFFECT_SPECS.keys())
    return "\n".join(
        [
            f"- Allowed condition types: {_format_type_list(condition_types)}.",
            f"- Allowed effect types: {_format_type_list(effect_types)}.",
            "- Regenerate docs with `python tools/generate_schema_docs.py` when the schema spec changes.",
        ]
    )


def _replace_block(path: Path, new_block: str) -> None:
    content = path.read_text()
    if MARKER_START not in content or MARKER_END not in content:
        raise RuntimeError(f"Markers not found in {path}.")
    before, rest = content.split(MARKER_START, 1)
    _, after = rest.split(MARKER_END, 1)
    updated = f"{before}{MARKER_START}\n{new_block}\n{MARKER_END}{after}"
    path.write_text(updated)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    readme_path = repo_root / "README.md"
    prompts_path = repo_root / "docs" / "prompts.md"

    _replace_block(readme_path, _render_block())
    _replace_block(prompts_path, _render_prompts_block())

    print("Updated schema docs. Regenerate docs with: python tools/generate_schema_docs.py")


if __name__ == "__main__":
    main()
