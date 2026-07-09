# Project Map: code-review-graph

## Stack & Versions
- **Language**: Python 3.10+
- **Version**: 2.3.1
- **Core Libraries**:
  - `mcp` / `fastmcp`: Model Context Protocol implementation
  - `tree-sitter` / `tree-sitter-language-pack`: Multi-language code parsing
  - `networkx`: Graph data structure and algorithms
  - `sqlite3`: Local persistent storage
  - `watchdog`: File system monitoring for incremental updates
- **Optional Extensions**:
  - `sentence-transformers`: Local vector embeddings
  - `google-generativeai`: Gemini-based embeddings
  - `igraph`: Community detection (Leiden algorithm)
  - `matplotlib`: Benchmark visualization
  - `ollama`: Wiki generation with LLMs

## Project Structure
- `code_review_graph/`: Main Python package
  - `parser.py`: Tree-sitter integration for 19+ languages
  - `graph.py`: Core graph management with SQLite and NetworkX
  - `incremental.py`: Logic for tracking file changes and partial re-indexing
  - `main.py`: MCP server entry point and tool registrations
  - `cli.py`: Command Line Interface implementation
  - `tools/`: Modular implementation of 22+ MCP tools
  - `visualization.py`: D3.js interactive graph generator
- `code-review-graph-vscode/`: Companion VS Code extension
- `tests/`: Comprehensive regression and integration tests
- `docs/`: Documentation and index
- `diagrams/`: Architectural diagrams
- `hooks/`: Git hooks for automation

## Infrastructure & Deployment
- **Build System**: `hatchling`
- **Package Manager**: `uv` (preferred), `pip`
- **CI/CD**: GitHub Actions (`.github/workflows/ci.yml`)
- **Distribution**: PyPI (`pip install code-review-graph`)

## Configuration
- **Ignored Files**: `.code-review-graphignore` or standard `.gitignore`
- **Environment Variables**:
  - `CRG_RECURSE_SUBMODULES`: Toggle submodule indexing
  - `CRG_EMBEDDING_MODEL`: Set the model for semantic search
- **Metadata Storage**: `.code-review-graph/` in repository root

## Entry Points
- **CLI**: `code-review-graph` (mapped to `code_review_graph.cli:main`)
- **MCP Server**: `code-review-graph serve` (mapped to `code_review_graph.main:main`)
- **Plugin Hook**: `.claude-plugin/` (for Claude Desktop/Code integration)

## Development
- **Setup**:
  ```bash
  git clone https://github.com/tirth8205/code-review-graph.git
  cd code-review-graph
  ```
- **Dependency Installation**:
  - **Option 1: Managed Environment (Recommended)**
    Use `uv` to create a local `.venv` and install all dependencies:
    ```bash
    uv sync --all-extras
    ```
  - **Option 2: Existing Virtual Environment**
    If you have an existing environment (e.g. Conda) active, use `uv pip` to install into it:
    ```bash
    uv pip install -e ".[all,dev]"
    ```
  - **Option 3: Legacy pip**
    ```bash
    pip install -e ".[all,dev]"
    ```
- **Running Commands**:
  After installing in editable mode, you can run CLI commands:
  * If the virtual environment is **active**:
    ```bash
    code-review-graph build
    ```
  * If the virtual environment is **inactive**:
    ```bash
    uv run code-review-graph build
    ```
- **Tests**:
  ```bash
  uv run pytest  # or simply 'pytest' if env is active
  ```
- **Build**:
  ```bash
  uv build  # or: python -m build
  ```

## Development & Quality
- **Linter/Formatter**: [Ruff](https://astral.sh/ruff)
- **Commands**:
    - `ruff check .` : Lint the codebase.
    - `ruff check . --fix` : Automatically fix resolvable lint errors.
    - `ruff format .` : Standardize code formatting.
- **Configuration**: Managed in `pyproject.toml` with specific rules for fixtures and templates.

## API Documentation
- Primary docs located in [`docs/INDEX.md`](file:///Users/minh/gitrepos/local_tools/code-review-graph/docs/INDEX.md)
- MCP tool list and CLI reference available in [README.md](file:///Users/minh/gitrepos/local_tools/code-review-graph/README.md)

## Security Notes
- Refactoring tools include path validation and dry-run modes
- Uses parameterized SQL queries to prevent injection (though local DB only)
- `B603`/`B607` bandit skips acknowledged for standard subprocess usage
