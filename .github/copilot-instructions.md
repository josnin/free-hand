# Repository instructions

## Project overview

Free-hand (`fh`) is a local, provider-neutral Python CLI. AI assistants produce a versioned JSON tool-call envelope; Free-hand validates it, executes registered local tools, and returns results for the assistant to consume. It does not call an AI API. The installed `fh` entry point is defined in `pyproject.toml` and implemented by `src/free_hand/cli.py`.

The main flow crosses several modules:

- `cli.py` owns subcommands and the interactive paste/execute loop. It loads project configuration, builds the registry, calls protocol parsing and execution, then saves the latest results and appends history.
- `protocol.py` cleans up surrounding prose or Markdown fences without rewriting JSON, then strictly validates the response envelope. Keep cleanup and validation separate: malformed JSON or invalid escapes must fail before tools run.
- `registry.py` defines `Tool` and `Registry`; `executor.py` registers the available tools and their JSON schemas, validates arguments, requests approval for non-read operations, and executes calls in order. A rejected or failed call halts later execution.
- `tools/` contains the local filesystem, command, and Git operations. Filesystem access is rooted in the current project and blocks traversal and secret-like paths. Mutating tools and commands have risk levels that drive the executor's approval flow.
- `prompt.py` generates the assistant instructions and tool schemas from the live registry; update the registry/schema source rather than duplicating tool definitions in the prompt.
- `config.py`, `history.py`, `clipboard.py`, and `color.py` provide configuration, result history, optional clipboard integration, and terminal rendering around that flow.

## Build and test

Python 3.14+ (pinned in `.python-version`) and `uv` are used. There are no runtime dependencies; pytest is in the `dev` dependency group.

From the repository root:

```sh
uv sync
uv run pytest -q
```

Run one test by its pytest node ID, for example:

```sh
uv run pytest -q tests/test_protocol.py::test_valid
```

Run the CLI from source with `uv run fh <command>`.

## Repository-specific conventions

- Keep application code under `src/free_hand/`; tests use pytest under `tests/`.
- Tool definitions belong in `executor.py` and are represented by `Tool` instances registered with JSON parameter schemas. Schemas reject undeclared arguments, and argument types are checked before handlers run.
- Treat the `risk` value on each tool as part of its behavior: `"read"` runs without confirmation; other risk levels require approval. Preserve sequential execution and halt-on-failure semantics.
- Project file operations should go through `safe_path` in `tools/filesystem.py` so project-root containment and blocked secret paths remain enforced. Git operations that accept paths use the same guard.
- External commands are passed as argv arrays with `shell=False`; preserve that interface rather than interpolating shell commands.
- Keep protocol parsing strict. `clean_response` may extract a valid response from surrounding text, but must not repair or reinterpret JSON string values.
- Tests that need project files or directories should use pytest's `tmp_path` fixture, avoiding changes to the working repository.
