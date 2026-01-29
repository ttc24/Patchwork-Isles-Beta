from engine.engine_min import ANSI_RESET, print_formatted


def test_print_formatted_applies_color_wrappers() -> None:
    text = (
        "Gain {trait:Swift} and {tag:Crimson Scarf} from {faction:Root Court}. "
        "{danger:Locked gate} ahead."
    )

    formatted = print_formatted(text)

    assert f"\033[36mSwift{ANSI_RESET}" in formatted
    assert f"\033[32mCrimson Scarf{ANSI_RESET}" in formatted
    assert f"\033[33mRoot Court{ANSI_RESET}" in formatted
    assert f"\033[31mLocked gate{ANSI_RESET}" in formatted
    assert "{trait:" not in formatted
