"""Tests for types.py - ToolResult, CLIResult."""

import pytest

from openagent.types import CLIResult, ToolResult


class TestToolResultBool:
    """Tests for ToolResult.__bool__."""

    def test_empty_result_is_falsy(self) -> None:
        """Empty ToolResult should be falsy."""
        result = ToolResult()
        assert not result

    def test_result_with_output_is_truthy(self) -> None:
        """ToolResult with output should be truthy."""
        result = ToolResult(output="hello")
        assert result

    def test_result_with_error_is_truthy(self) -> None:
        """ToolResult with error should be truthy."""
        result = ToolResult(error="something went wrong")
        assert result

    def test_result_with_system_is_truthy(self) -> None:
        """ToolResult with system message should be truthy."""
        result = ToolResult(system="restarted")
        assert result

    def test_result_with_base64_image_is_truthy(self) -> None:
        """ToolResult with base64_image should be truthy."""
        result = ToolResult(base64_image="abc123")
        assert result

    def test_result_with_empty_strings_is_falsy(self) -> None:
        """ToolResult with empty strings is still falsy (empty string is falsy)."""
        result = ToolResult(output="", error="", system="")
        assert not result


class TestToolResultAdd:
    """Tests for ToolResult.__add__."""

    def test_add_outputs(self) -> None:
        """Adding two results with outputs concatenates them."""
        r1 = ToolResult(output="line1\n")
        r2 = ToolResult(output="line2")
        combined = r1 + r2
        assert combined.output == "line1\nline2"

    def test_add_errors(self) -> None:
        """Adding two results with errors concatenates them."""
        r1 = ToolResult(error="err1")
        r2 = ToolResult(error="err2")
        combined = r1 + r2
        assert combined.error == "err1err2"

    def test_add_system_messages(self) -> None:
        """Adding two results with system messages concatenates them."""
        r1 = ToolResult(system="msg1")
        r2 = ToolResult(system="msg2")
        combined = r1 + r2
        assert combined.system == "msg1msg2"

    def test_add_with_one_none_field(self) -> None:
        """When only one result has a field, use that field."""
        r1 = ToolResult(output="hello")
        r2 = ToolResult()
        combined = r1 + r2
        assert combined.output == "hello"
        assert combined.error is None

    def test_add_base64_images_raises(self) -> None:
        """Adding two results with base64_images raises ValueError."""
        r1 = ToolResult(base64_image="abc")
        r2 = ToolResult(base64_image="def")
        with pytest.raises(ValueError, match="Cannot combine"):
            _ = r1 + r2

    def test_add_base64_image_with_none(self) -> None:
        """Adding result with base64_image to result without is fine."""
        r1 = ToolResult(base64_image="abc")
        r2 = ToolResult(output="hello")
        combined = r1 + r2
        assert combined.base64_image == "abc"
        assert combined.output == "hello"

    def test_add_preserves_all_fields(self) -> None:
        """Adding combines all fields appropriately."""
        r1 = ToolResult(output="out1", error="err1", system="sys1")
        r2 = ToolResult(output="out2", error="err2", system="sys2")
        combined = r1 + r2
        assert combined.output == "out1out2"
        assert combined.error == "err1err2"
        assert combined.system == "sys1sys2"


class TestToolResultReplace:
    """Tests for ToolResult.replace."""

    def test_replace_output(self) -> None:
        """Replace output field."""
        original = ToolResult(output="hello")
        replaced = original.replace(output="world")
        assert replaced.output == "world"
        assert original.output == "hello"  # Original unchanged

    def test_replace_adds_new_field(self) -> None:
        """Replace can add a field that was None."""
        original = ToolResult(output="hello")
        replaced = original.replace(error="oops")
        assert replaced.output == "hello"
        assert replaced.error == "oops"

    def test_replace_multiple_fields(self) -> None:
        """Replace multiple fields at once."""
        original = ToolResult(output="hello", error="err")
        replaced = original.replace(output="world", error="fixed")
        assert replaced.output == "world"
        assert replaced.error == "fixed"

    def test_replace_with_none(self) -> None:
        """Replace a field with None."""
        original = ToolResult(output="hello", error="err")
        replaced = original.replace(error=None)
        assert replaced.output == "hello"
        assert replaced.error is None


class TestCLIResult:
    """Tests for CLIResult class."""

    def test_has_exit_code(self) -> None:
        """CLIResult has exit_code field."""
        result = CLIResult(stdout="hello", exit_code=0)
        assert result.exit_code == 0

    def test_has_stdout_stderr(self) -> None:
        """CLIResult has stdout and stderr fields."""
        result = CLIResult(stdout="output", stderr="error", exit_code=0)
        assert result.stdout == "output"
        assert result.stderr == "error"

    def test_defaults(self) -> None:
        """CLIResult has sensible defaults."""
        result = CLIResult()
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.metadata is None

    def test_to_text_success(self) -> None:
        """CLIResult.to_text for successful command."""
        result = CLIResult(stdout="hello", exit_code=0)
        assert result.to_text() == "hello"

    def test_to_text_success_with_stderr(self) -> None:
        """CLIResult.to_text for successful command with stderr."""
        result = CLIResult(stdout="output", stderr="warning", exit_code=0)
        text = result.to_text()
        assert "output" in text
        assert "<stderr>warning</stderr>" in text

    def test_to_text_failure(self) -> None:
        """CLIResult.to_text for failed command."""
        result = CLIResult(stderr="No such file", exit_code=1)
        text = result.to_text()
        assert "<error>" in text
        assert "Exit Code 1" in text
        assert "No such file" in text

    def test_to_text_failure_with_stdout(self) -> None:
        """CLIResult.to_text for failed command with stdout."""
        result = CLIResult(stdout="partial", stderr="failed", exit_code=1)
        text = result.to_text()
        assert "<error>" in text
        assert "Exit Code 1" in text
        assert "failed" in text
        assert "partial" in text

    def test_frozen_dataclass(self) -> None:
        """CLIResult is a frozen dataclass."""
        from dataclasses import FrozenInstanceError

        result = CLIResult(stdout="hello")
        with pytest.raises(FrozenInstanceError):
            result.stdout = "world"  # type: ignore[misc]
