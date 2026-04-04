# Contributing to readiness-as-code

Thanks for your interest in contributing.

## Development Setup

```bash
git clone https://github.com/jtwalters25/readiness-as-code.git
cd readiness-as-code
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
src/
├── ready.py          # CLI entry point
├── validators.py     # Core scan engine
├── mcp_server.py     # MCP server (AI tool integration)
└── adapters/         # Work item integrations
    ├── __init__.py   # WorkItemAdapter interface
    ├── github_issues.py
    └── ado.py

schemas/              # JSON schemas for validation
examples/             # Starter packs and examples
templates/            # CI/CD templates
ai-skills/            # AI prompt skills (works with any model)
mcp/                  # MCP client connection configs
tests/                # pytest tests
```

## How to Contribute

### Adding a New Verification Method

1. Add the method to `src/validators.py` following the `_verify_*` pattern
2. Register it in the `VERIFICATION_METHODS` dict
3. Update `schemas/checkpoint-definitions.schema.json` to include the new method
4. Add tests in `tests/test_validators.py`

### Adding a New Work Item Adapter

1. Create `src/adapters/your_adapter.py`
2. Implement the `WorkItemAdapter` interface from `src/adapters/__init__.py`
3. Add tests
4. Update README adapter table

### Adding a New MCP Tool

1. Open `src/mcp_server.py`
2. Add a function decorated with `@mcp.tool()`
3. Use a descriptive docstring — it becomes the tool description shown to AI assistants
4. Return a JSON string (use `json.dumps`)
5. Update `mcp/README.md` with the new tool's description

### Adding Example Checkpoint Packs

1. Create a new directory under `examples/`
2. Include a `checkpoint-definitions.json` with checks relevant to that service type
3. Include a brief README explaining the use case

### MCP Development Setup

To work on the MCP server, install the mcp extra:

```bash
pip install -e ".[mcp]"
ready-mcp    # verify it starts without errors
```

Test it with the MCP inspector:
```bash
npx @modelcontextprotocol/inspector ready-mcp
```

## Code Style

- Python 3.10+ (use type hints)
- Run `ruff check` before committing
- Keep functions focused — one verification method per function
- Every checkpoint definition field should have a clear purpose

## Submitting Changes

1. Fork the repo
2. Create a branch (`git checkout -b feature/my-feature`)
3. Make your changes with tests
4. Run `pytest tests/ -v`
5. Submit a PR with a clear description of what and why

## Design Principles

Before contributing, understand the core philosophy:

1. **No infrastructure** — This tool runs as scripts and files. Don't add databases, servers, or cloud dependencies.
2. **Human-in-the-loop** — The system detects, humans decide. Don't auto-close work items or auto-accept risks.
3. **Portable** — It should work in any repo, any CI system, any language ecosystem.
4. **Evidence-backed** — Every assertion needs a file path, attestation, or work item link.
