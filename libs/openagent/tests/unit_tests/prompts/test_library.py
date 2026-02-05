"""Tests for PromptLibrary."""

# ruff: noqa: SIM118

import pytest

from openagent.prompts.library import PromptLibrary


class TestPromptLibraryScan:
    """Tests for automatic fragment scanning."""

    def test_scan_finds_fragments(self) -> None:
        """Test that scanning discovers .md fragment files."""
        library = PromptLibrary()
        keys = library.keys()
        assert len(keys) > 0

    def test_scan_finds_system_base(self) -> None:
        """Test that system/base fragment is discovered."""
        library = PromptLibrary()
        assert library.has("system/base")

    def test_scan_finds_all_system_fragments(self) -> None:
        """Test all system fragments are discovered."""
        library = PromptLibrary()
        expected = [
            "system/base",
            "system/tools",
            "system/skills",
            "system/mcps",
            "system/environment",
            "system/user_instructions",
        ]
        for key in expected:
            assert library.has(key), f"Missing fragment: {key}"

    def test_scan_finds_tool_fragments(self) -> None:
        """Test all tool instruction fragments are discovered."""
        library = PromptLibrary()
        expected = [
            "tools/bash",
            "tools/read",
            "tools/write",
            "tools/edit",
            "tools/glob",
            "tools/grep",
            "tools/web_search",
            "tools/web_fetch",
            "tools/skill",
        ]
        for key in expected:
            assert library.has(key), f"Missing fragment: {key}"

    def test_scan_finds_compaction_fragments(self) -> None:
        """Test compaction fragments are discovered."""
        library = PromptLibrary()
        assert library.has("compaction/request")
        assert library.has("compaction/summary_rebuild")


class TestPromptLibraryGet:
    """Tests for get() method."""

    def test_get_returns_raw_template(self) -> None:
        """Test get returns the raw template string."""
        library = PromptLibrary()
        template = library.get("system/base")
        assert isinstance(template, str)
        assert "OpenAgent" in template

    def test_get_missing_key_raises(self) -> None:
        """Test get raises KeyError for missing key."""
        library = PromptLibrary()
        with pytest.raises(KeyError, match="Prompt template not found"):
            library.get("nonexistent/key")


class TestPromptLibraryRender:
    """Tests for render() method."""

    def test_render_substitutes_variables(self) -> None:
        """Test render substitutes {variable} placeholders."""
        library = PromptLibrary()
        result = library.render("system/tools", {"tool_instructions": "Use bash."})
        assert "Use bash." in result
        assert "{tool_instructions}" not in result

    def test_render_missing_variable_raises(self) -> None:
        """Test render raises KeyError for missing variable."""
        library = PromptLibrary()
        with pytest.raises(KeyError):
            library.render("system/tools", {})

    def test_render_missing_key_raises(self) -> None:
        """Test render raises KeyError for missing template key."""
        library = PromptLibrary()
        with pytest.raises(KeyError, match="Prompt template not found"):
            library.render("nonexistent/key", {})


class TestPromptLibraryRegister:
    """Tests for register() method."""

    def test_register_adds_template(self) -> None:
        """Test register adds a new template."""
        library = PromptLibrary()
        library.register("custom/tool", "Description of {tool_name}")
        assert library.has("custom/tool")
        assert library.get("custom/tool") == "Description of {tool_name}"

    def test_register_overwrites_existing(self) -> None:
        """Test register overwrites existing template."""
        library = PromptLibrary()
        library.register("custom/tool", "Original")
        library.register("custom/tool", "Updated")
        assert library.get("custom/tool") == "Updated"


class TestPromptLibraryHas:
    """Tests for has() method."""

    def test_has_returns_true_for_existing(self) -> None:
        """Test has returns True for existing key."""
        library = PromptLibrary()
        assert library.has("system/base") is True

    def test_has_returns_false_for_missing(self) -> None:
        """Test has returns False for missing key."""
        library = PromptLibrary()
        assert library.has("nonexistent") is False


class TestPromptLibraryKeys:
    """Tests for keys() method."""

    def test_keys_returns_sorted_list(self) -> None:
        """Test keys returns a sorted list."""
        library = PromptLibrary()
        keys = library.keys()
        assert keys == sorted(keys)

    def test_keys_includes_registered(self) -> None:
        """Test keys includes programmatically registered templates."""
        library = PromptLibrary()
        library.register("zzz/custom", "Custom template")
        keys = library.keys()
        assert "zzz/custom" in keys


class TestAllFragmentsRender:
    """Smoke test: all fragments render without error."""

    def test_all_fragments_render_with_test_vars(self) -> None:
        """All fragments should render with a complete set of test variables."""
        library = PromptLibrary()

        # Build a comprehensive set of variables that covers all templates
        test_vars = {
            "tool_instructions": "Use bash for commands.\n\nUse read for files.",
            "skill_list": "- **commit**: Git commits",
            "mcp_list": "- **context7**: Docs",
            "environment_list": "- platform: linux",
            "user_instructions": "Be helpful.",
            "summary_content": "Previous work summary.",
            # Tool name variables (auto-derived by assembler)
            "tool_bash": "bash",
            "tool_read": "read",
            "tool_write": "write",
            "tool_edit": "edit",
            "tool_glob": "glob",
            "tool_grep": "grep",
            "tool_web_search": "web_search",
            "tool_web_fetch": "web_fetch",
            "tool_skill": "skill",
        }

        for key in library.keys():
            template = library.get(key)
            # Try to render - some templates may not have variables
            try:
                template.format_map(test_vars)
            except KeyError as e:
                pytest.fail(f"Fragment '{key}' has unresolved variable: {e}")
