# Contributing to ClawWork

Thank you for your interest in contributing to ClawWork! We believe agent infrastructure should be open, vendor-neutral, and community-driven — and every contribution moves that forward.

Whether you're fixing a typo, adding a new tool, implementing a computer backend, or improving documentation, you're helping build the agent harness the community needs.

## Getting Started

### Prerequisites

- Python 3.11+ (3.12+ for the demo app)
- [uv](https://docs.astral.sh/uv/) — fast Python package manager
- Node.js 18+ (for the demo frontend/electron)

### Development Setup

```bash
# Clone the repository
git clone https://github.com/an7tang/clawwork.git
cd clawwork

# Set up the core library
cd libs/clawwork
uv sync --group test

# Verify everything works
make lint
make test
```

### Project Structure

```
clawwork/
├── libs/
│   ├── clawwork/          # Core agent harness library
│   │   ├── clawwork/      #   Package source
│   │   ├── tests/         #   Unit + integration tests
│   │   ├── sandbox/       #   Docker/VM sandbox configs
│   │   ├── Makefile       #   Build targets
│   │   └── pyproject.toml #   Package config
│   └── clawwork_demo/     # Demo desktop application
│       ├── backend/       #   FastAPI backend
│       ├── frontend/      #   React frontend
│       └── electron/      #   Electron shell
├── CONTRIBUTING.md        # This file
└── README.md              # Project overview
```

## Development Workflow

### Running Tests

```bash
cd libs/clawwork

make test              # Unit tests with coverage
make integration_test  # Integration tests (requires API keys)

# Run a specific test
uv run pytest tests/unit_tests/path/to/test_file.py -v
uv run pytest tests/unit_tests/path/to/test_file.py::test_name -v
```

### Code Quality

```bash
make lint    # Ruff formatting check + Ruff linting + MyPy strict
make format  # Auto-fix formatting and lint issues
```

All code must pass:
- **Ruff** — formatting and linting
- **MyPy strict** — full type checking with `--strict`

Pre-commit hooks are configured to run these checks automatically. Install them with:

```bash
pip install pre-commit
pre-commit install
```

### Code Style

- **Typing**: MyPy strict mode. All public APIs must have complete type annotations.
- **Docstrings**: Google style. Required on all public APIs.
- **Async**: All tool and session operations are async.
- **Error handling**: Fail fast on bugs, retry on transient failures. Specific exceptions only — no bare `except:`. Actionable messages (what failed, why, what to do next).
- **Line length**: 150 characters max.

### Writing Tests

- Use `pytest-asyncio` with `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed)
- Test behavior, not implementation details
- Prefer testing public APIs over internal functions
- Descriptive test names: `test_<action>_<condition>_<expected_result>`
- Unit tests in `tests/unit_tests/` — mirror the `clawwork/` directory structure
- Integration tests in `tests/integration_tests/`

## Making Changes

### Before You Start

1. Check existing [issues](https://github.com/an7tang/clawwork/issues) to see if someone is already working on it
2. For significant changes, open an issue first to discuss the approach
3. Fork the repository and create a feature branch

### Pull Request Process

1. Create a branch from `main`:
   ```bash
   git checkout -b your-feature-name
   ```

2. Make your changes. Keep commits focused and well-described.

3. Ensure all checks pass:
   ```bash
   cd libs/clawwork
   make format
   make lint
   make test
   ```

4. Push and open a pull request against `main`.

5. In your PR description:
   - Summarize what changed and why
   - Link related issues
   - Include a test plan

### What We Look For in Reviews

- **Correctness and logic** — Does it work? Are edge cases handled?
- **Code quality** — Is it readable, well-typed, and well-tested?
- **Simplicity** — Is this the simplest solution that works? No over-engineering.
- **Architecture alignment** — Does it follow the project's design principles?

Backward compatibility is not a concern at this stage (0.0.x). Clean design always wins.

## Architecture Principles

When contributing, keep these principles in mind:

- **Testability**: Every module must be testable in isolation without complex mocks.
- **Composability**: Small, single-purpose units with explicit inputs and outputs.
- **Minimal Dependencies**: A change to module A should require understanding only module A.
- **Agent-First**: Tools and results are designed for agent ergonomics, not human UIs.
- **Simplicity**: Obvious solutions over clever ones.
- **Idempotency**: Operations must be safely repeatable.

### Framework-Agnostic Core

The core library (`clawwork/`) is framework-agnostic — LangChain integration lives in `clawwork/langchain/`. Don't introduce LangChain imports outside of that directory.

### Where to Contribute

| Area | Good for | Location |
|------|----------|----------|
| New tools | Adding capabilities to agents | `clawwork/tools/` |
| Computer implementations | New execution environments | `clawwork/computer/` |
| Web providers | New search/fetch backends | `clawwork/tools/web/providers/` |
| MCP improvements | Protocol support | `clawwork/mcp/` |
| Prompt fragments | Better agent instructions | `clawwork/prompts/fragments/` |
| Demo features | UI/UX improvements | `libs/clawwork_demo/` |
| Tests | Improving coverage | `tests/` |
| Documentation | Clarity and examples | `README.md`, `libs/*/README.md` |

## Good First Issues

New to the project? Look for issues tagged [`good first issue`](https://github.com/an7tang/clawwork/labels/good%20first%20issue). These are scoped to be approachable without deep knowledge of the codebase.

## Reporting Issues

- Use [GitHub Issues](https://github.com/an7tang/clawwork/issues)
- Include steps to reproduce, expected behavior, and actual behavior
- For bugs, include your Python version, OS, and relevant dependency versions

## Questions?

Open a [Discussion](https://github.com/an7tang/clawwork/discussions) for questions, ideas, or feedback that don't fit neatly into an issue.
