# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

**OpenAgent** is a general-purpose agent harness that gives LLM agents a CLI-based computer, enabling them to complete tasks the way humans do.

**Core Philosophy**:
1. Give the agent a computer (via the terminal)
2. Agent-First: Design for agent ergonomics—easy to use with minimal cognitive burden. Absorb infrastructure complexity inside modules; expose only what agents need to reason about.
3. Testability, Composability, Minimal Dependencies

Just as humans interact with computers through terminals—running commands, editing files, navigating filesystems—OpenAgent provides agents with the same primitives. This design choice is intentional: the CLI is a proven, composable interface that has stood the test of time.

**Status**: Pre-Experimental (0.0.x). Breaking changes are made all the time. Bold refactoring encouraged.

## Commands

This project uses **uv** for dependency management and running Python.

```bash
make test              # Unit tests with coverage
make integration_test  # Integration tests
make lint              # Ruff + mypy strict
make format            # Auto-fix formatting

# Single test file
uv run pytest tests/unit_tests/core/test_results.py -v
```

## Code Standards

**Typing**: MyPy strict mode. All code must pass `mypy --strict`.

**Docstrings**: Google style. Required on all public APIs.

**Async**: All session/tool operations are async. Tests use pytest-asyncio with `asyncio_mode = "auto"`.

**Error Handling**:
- Specific exceptions only—never bare `except:` or `except Exception:` without re-raise
- Actionable messages: what failed, why, what to do next
- Custom exception types for domain errors
- All external operations need explicit timeouts

**Architecture Design**:
- Simplicity
- Testability
- Composition
- Minimal dependencies

**Reliability**:
- Idempotency: operations should be safe to retry
- Graceful degradation: partial failures shouldn't cascade into total failure

## Making Changes

Full permission to refactor, rename, restructure, or break APIs.

If something feels wrong or if there's better architecture or code design, actively propose your suggestions. Don't preserve patterns just because they exist.