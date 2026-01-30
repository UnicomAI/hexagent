## Project Overview

**OpenAgent** is a general-purpose agent harness that **gives LLM agents access to a computer via the terminal** to complete tasks the way humans do.

### Architecture Principles

- **Testability:** Every module must be testable in isolation without complex mocks. If you can't write a fast, deterministic test for it, redesign the module—not the test.
- **Composability:** Prefer small, single-purpose units with explicit inputs and outputs over larger multi-purpose ones. No hidden state. Pieces should combine freely and fail locally.
- **Minimal Dependencies:** A change to module A should require understanding only module A. No implicit contracts, no action-at-a-distance, no "you also need to update X, Y, Z."
- **Agent-First:** Design tools and format results for agent ergonomics. Hide infrastructure complexity inside modules.
- **Simplicity:** Favor obvious solutions over clever ones. Code should be readable without context.
- **Idempotency:** Operations should be safely repeatable. Retries must not cause unintended side effects.

### Status

Pre-Experimental (0.0.x).

Backward compatibility is not a concern. Clean architecture and code quality always win. Refactor, rename, restructure, or break APIs as needed. Don't preserve patterns just because they exist.

## Commands

This project uses **uv** for dependency management and running Python.

```bash
make test              # Unit tests with coverage
make integration_test  # Integration tests
make lint              # Ruff + mypy strict
make format            # Auto-fix formatting
```

## Code Style Standards

**Typing**: MyPy strict mode (`mypy --strict`).

**Docstrings**: Google style. Required on all public APIs.

**Async**: All session/tool operations are async.

**Error Handling**: Fail fast on bugs, retry on transient failures. Specific exceptions only—no bare `except:`. Actionable messages (what failed, why, what to do next). Explicit timeouts on external operations.

## Testing

**Running Tests**:
```bash
make test                                              # All unit tests
uv run pytest tests/unit_tests/path/to/test_file.py   # Single file
uv run pytest tests/unit_tests/path/to/test_file.py::test_name -v  # Single test
```

**Test Organization**:
- Unit tests: `tests/unit_tests/` — mirrors `openagent/` structure
- Integration tests: `tests/integration_tests/`

**Writing Tests**:
- Use pytest-asyncio with `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed)
- Test behavior, not implementation details
- Prefer testing public APIs over internal functions
- Use descriptive test names: `test_<action>_<condition>_<expected_result>`

## Review Guidelines

Focus on **correctness, logic, and code quality**. Backward compatibility should never block a better design.
