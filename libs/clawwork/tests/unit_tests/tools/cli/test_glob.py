"""Tests for GlobTool."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from clawwork.computer import LocalNativeComputer
from clawwork.exceptions import CLIError
from clawwork.tools import GlobTool


@pytest.fixture
def sample_tree(tmp_path: Path) -> Path:
    """Create a directory tree with known files for glob testing.

    Structure:
        tmp_path/
            readme.md
            config.toml
            src/
                main.py
                utils.py
                sub/
                    helper.py
            tests/
                test_main.py
    """
    (tmp_path / "src" / "sub").mkdir(parents=True)
    (tmp_path / "tests").mkdir()

    files = [
        tmp_path / "readme.md",
        tmp_path / "config.toml",
        tmp_path / "src" / "main.py",
        tmp_path / "src" / "utils.py",
        tmp_path / "src" / "sub" / "helper.py",
        tmp_path / "tests" / "test_main.py",
    ]
    for f in files:
        f.write_text(f"# {f.name}")

    return tmp_path


class TestGlobToolExecute:
    """Tests for glob pattern matching with a real computer."""

    async def test_finds_py_files_recursively(self, sample_tree: Path) -> None:
        """**/*.py finds all .py files in the tree."""
        tool = GlobTool(LocalNativeComputer())
        result = await tool(description="test", pattern="**/*.py", path=str(sample_tree))
        assert result.output is not None
        assert result.error is None
        lines = result.output.strip().split("\n")
        assert len(lines) == 4
        for line in lines:
            assert line.endswith(".py")

    async def test_pattern_without_double_star_still_recurses(self, sample_tree: Path) -> None:
        """*.py (without **) behaves the same as **/*.py."""
        tool = GlobTool(LocalNativeComputer())
        result = await tool(description="test", pattern="*.py", path=str(sample_tree))
        assert result.output is not None
        lines = result.output.strip().split("\n")
        assert len(lines) == 4

    async def test_brace_expansion(self, sample_tree: Path) -> None:
        """**/*.{py,toml} finds both .py and .toml files."""
        tool = GlobTool(LocalNativeComputer())
        result = await tool(description="test", pattern="**/*.{py,toml}", path=str(sample_tree))
        assert result.output is not None
        lines = result.output.strip().split("\n")
        py_count = sum(1 for line in lines if line.endswith(".py"))
        toml_count = sum(1 for line in lines if line.endswith(".toml"))
        assert py_count == 4
        assert toml_count == 1

    async def test_no_matches_returns_output_not_error(self, sample_tree: Path) -> None:
        """Pattern with no matches returns output (not error)."""
        tool = GlobTool(LocalNativeComputer())
        result = await tool(description="test", pattern="**/*.xyz", path=str(sample_tree))
        assert result.output is not None
        assert result.error is None
        # Should not contain any .xyz file paths
        assert ".xyz" not in result.output

    async def test_nonexistent_directory_returns_error(self) -> None:
        """Non-existent directory returns error with descriptive message."""
        tool = GlobTool(LocalNativeComputer())
        result = await tool(description="test", pattern="*.py", path="/nonexistent/path/12345")
        assert result.error is not None
        assert "does not exist" in result.error.lower()
        assert result.output is None

    async def test_results_are_absolute_paths(self, sample_tree: Path) -> None:
        """All result paths are absolute."""
        tool = GlobTool(LocalNativeComputer())
        result = await tool(description="test", pattern="**/*.py", path=str(sample_tree))
        assert result.output is not None
        for line in result.output.strip().split("\n"):
            assert line.startswith("/")

    async def test_specific_filename_pattern(self, sample_tree: Path) -> None:
        """**/test_*.py finds only test files."""
        tool = GlobTool(LocalNativeComputer())
        result = await tool(description="test", pattern="**/test_*.py", path=str(sample_tree))
        assert result.output is not None
        lines = result.output.strip().split("\n")
        assert len(lines) == 1
        assert "test_main.py" in lines[0]

    async def test_default_path_uses_cwd(self) -> None:
        """Omitting path uses the current working directory without error."""
        tool = GlobTool(LocalNativeComputer())
        result = await tool(description="test", pattern="**/*.py")
        # Should not error; may or may not find files depending on cwd
        assert result.error is None

    async def test_only_files_not_directories(self, sample_tree: Path) -> None:
        """Results contain only files, not directories."""
        tool = GlobTool(LocalNativeComputer())
        result = await tool(description="test", pattern="**/*", path=str(sample_tree))
        assert result.output is not None
        for line in result.output.strip().split("\n"):
            assert not Path(line).is_dir()


class TestGlobToolSorting:
    """Tests for modification-time sorting."""

    async def test_sorted_by_mtime_oldest_first(self, tmp_path: Path) -> None:
        """Files are returned sorted by modification time, oldest first."""
        old = tmp_path / "old.py"
        new = tmp_path / "new.py"

        old.write_text("# old")
        new.write_text("# new")

        # Set explicit modification times so order is deterministic.
        os.utime(old, (1000, 1000))
        os.utime(new, (2000, 2000))

        tool = GlobTool(LocalNativeComputer())
        result = await tool(description="test", pattern="*.py", path=str(tmp_path))
        assert result.output is not None
        lines = result.output.strip().split("\n")
        assert len(lines) == 2
        assert "old.py" in lines[0]  # oldest first
        assert "new.py" in lines[1]


class TestGlobToolResultLimit:
    """Tests for result count limiting."""

    async def test_max_100_results(self, tmp_path: Path) -> None:
        """No more than 100 results are returned."""
        for i in range(105):
            (tmp_path / f"file_{i:03d}.txt").write_text(f"# {i}")

        tool = GlobTool(LocalNativeComputer())
        result = await tool(description="test", pattern="*.txt", path=str(tmp_path))
        assert result.output is not None
        lines = result.output.strip().split("\n")
        assert len(lines) == 100


class TestGlobToolCLIError:
    """Tests for infrastructure failure handling."""

    async def test_cli_error_returns_error_result(self) -> None:
        """CLIError from computer.run is caught and returned as error."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("sandbox crashed"))
        tool = GlobTool(computer)
        result = await tool(description="test", pattern="*.py")
        assert result.error is not None
        assert "sandbox crashed" in result.error

    async def test_cli_error_includes_system_message(self) -> None:
        """CLIError result includes a system message for the agent."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("timeout"))
        tool = GlobTool(computer)
        result = await tool(description="test", pattern="*.py")
        assert result.system is not None

    async def test_cli_error_output_is_none(self) -> None:
        """CLIError result has no output."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("boom"))
        tool = GlobTool(computer)
        result = await tool(description="test", pattern="*.py")
        assert result.output is None
