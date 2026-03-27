"""Tests for prompt content loading and substitution."""

from collections.abc import Generator

import pytest

from hexagent.prompts import content
from hexagent.prompts.content import substitute


@pytest.fixture(autouse=True)
def _clear_caches() -> Generator[None]:
    """Clear content caches after each test for isolation."""
    yield
    content.load.cache_clear()
    content._scan_package_keys.cache_clear()


class TestLoad:
    """Tests for content.load()."""

    def test_load_returns_nonempty_string(self) -> None:
        result = content.load("system_prompt_identity")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_load_missing_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="Prompt fragment not found"):
            content.load("nonexistent_key_xyz")

    def test_all_system_prompt_fragments_loadable(self) -> None:
        keys = content.find("system_prompt_")
        assert len(keys) > 0, "Expected at least one system_prompt fragment"
        for key in keys:
            result = content.load(key)
            assert len(result) > 0, f"Fragment '{key}' is empty"

    def test_all_tool_instruction_fragments_loadable(self) -> None:
        keys = content.find("tool_instruction_")
        assert len(keys) > 0, "Expected at least one tool_instruction fragment"
        for key in keys:
            result = content.load(key)
            assert len(result) > 0, f"Fragment '{key}' is empty"

    def test_all_user_prompt_fragments_loadable(self) -> None:
        keys = content.find("user_prompt_")
        assert len(keys) > 0, "Expected at least one user_prompt fragment"
        for key in keys:
            result = content.load(key)
            assert len(result) > 0, f"Fragment '{key}' is empty"

    def test_temporary_dir_excluded(self) -> None:
        all_keys = content.find("")
        assert not any(k.startswith("_temporary") for k in all_keys)


class TestFind:
    """Tests for content.find()."""

    def test_find_by_prefix_returns_matching_keys(self) -> None:
        result = content.find("system_prompt_")
        assert len(result) > 0
        assert all(k.startswith("system_prompt_") for k in result)

    def test_find_tool_supplements(self) -> None:
        result = content.find("tool_instruction_bash_")
        assert "tool_instruction_bash_git_commit_and_pr_creation_instructions" in result

    def test_find_no_match(self) -> None:
        result = content.find("nonexistent_prefix_")
        assert result == []

    def test_find_sorted(self) -> None:
        result = content.find("system_prompt_")
        assert result == sorted(result)


class TestSubstitute:
    """Tests for content.substitute()."""

    def test_single_var(self) -> None:
        assert substitute("Hello ${NAME}!", NAME="World") == "Hello World!"

    def test_multiple_vars(self) -> None:
        result = substitute("${A} and ${B}", A="one", B="two")
        assert result == "one and two"

    def test_leaves_dollar_signs_alone(self) -> None:
        assert substitute("$(cat file) and $HOME") == "$(cat file) and $HOME"

    def test_raises_on_unresolved(self) -> None:
        with pytest.raises(ValueError, match=r"Unresolved placeholders.*\$\{MISSING\}"):
            substitute("Hello ${MISSING}!")

    def test_lists_all_unresolved(self) -> None:
        with pytest.raises(ValueError, match=r"\$\{A\}.*\$\{B\}"):
            substitute("${A} and ${B}")

    def test_extra_vars_ignored(self) -> None:
        result = substitute("Hello ${NAME}!", NAME="World", EXTRA="ignored")
        assert result == "Hello World!"

    def test_no_placeholders_is_noop(self) -> None:
        text = "No vars here: $dollar sign"
        assert substitute(text) == text

    def test_ignores_non_uppercase_placeholders(self) -> None:
        """Lowercase, dotted, and paren patterns are NOT checked."""
        text = "${lowercase} ${OBJ.field} ${FN()}"
        assert substitute(text) == text
