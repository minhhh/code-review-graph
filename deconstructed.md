# Deconstructed: code-review-graph

## Architecture Overview
The system is built on a "Structural Knowledge Graph" architecture that mirrors the codebase structure into a persistent SQLite database. It follows a layered approach:
0.  **Discovery Layer**: Git-aware file discovery and filtering. Defines the "world view" of the tool.
1.  **Parsing Layer**: Tree-sitter grammars extract AST nodes (classes, functions, etc.) into a language-agnostic data model.
2.  **Storage Layer**: SQLite stores nodes and edges with a NetworkX integration for advanced graph algorithms.
3.  **Analysis Layer**: Logic for blast-radius calculations, execution flows, and community detection.
4.  **Interface Layer**: A multi-platform CLI and an MCP server for AI tool integration.

## Discovery: The Repo-Centric Input Layer
The tool's utility is limited by what it "sees." This layer handles the discovery and filtering of input files:
- **Repo-Centricity**: The tool is designed to work within a single Git repository root. It uses `git ls-files` as the primary discovery mechanism, ensuring that only tracked files (and optionally submodules) are indexed. 
    - *Impact*: This means the tool is excellent for internal code review but does not index external libraries unless they are physically vendored or included as submodules.
- **Filtering Logic**: 
    - **`.code-review-graphignore`**: A project-specific ignore file (similar to `.gitignore`) that allows developers to exclude generated code, large asset files, or vendor directories that would bloat the graph.
    - **Language Filtering**: The discovery logic uses `EXTENSION_TO_LANGUAGE` mappings to skip files that don't have a supported Tree-sitter grammar.
- **Incremental Detection**: During `build`, it compares current file SHAs against the database to determine which files require re-parsing.

## Entry Points
- **`code_review_graph/cli.py`**: Main CLI entry point. Dispatches commands to specialized modules (`incremental.py`, `changes.py`, `visualization.py`).
- **`code_review_graph/main.py`**: MCP server entry point. Registers 22+ tools using `fastmcp`.
- **`.claude-plugin/`**: Integration hook for Claude-specific workflows.

## Important Classes/Symbols
- **`GraphStore`** ([graph.py:L122](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/graph.py#L122))
    - Responsibility: Manages the SQLite connection, schema, and performance-critical Recursive CTE queries for impact analysis.
- **`CodeParser`** ([parser.py:L348](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/parser.py#L348))
    - Responsibility: A semantic translation engine. Maps low-level Tree-sitter ASTs to a unified symbol graph, handles cross-file name resolution, and manages file-format polyglots (Vue/Notebooks).
- **`IncrementalUpdateManager`** ([incremental.py](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/incremental.py))
    - Responsibility: Detects changed files via Git and determines the "minimal set" of files to re-parse.
- **`NodeInfo` / `EdgeInfo`** ([parser.py:L43-L67](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/parser.py#L43-L67))
    - Responsibility: Data transfer objects (DTOs) for the graph's structural elements.

## Important Flows

### Build/Update Flow (The "Happy Path")
- `code-review-graph build`
    -> `incremental.full_build()`
        -> `incremental.collect_all_files()` (Git-aware file discovery)
            -> `ProcessPoolExecutor` (Parallel parsing)
                -> `CodeParser.parse_file()` (Tree-sitter AST extraction)
                    -> `GraphStore.store_file_nodes_edges()` (Atomic SQLite write)
        -> `run_postprocess()` (Signatures, Flows, Communities)

### Change Detection / Code Review Flow
- `get_impact_radius_tool`
    -> `graph.get_impact_radius_sql()` (Recursive CTE)
        -> Finds all nodes reachable from `changed_files` up to `max_depth`.
        -> Computes "minimal review context" including only affected functions/tests.

## Specific Features
- **Incremental Updates**: Uses SHA-256 hashing to skip re-parsing unchanged files.
- **Execution Flows**: Traces call chains from entry points to compute "criticality" scores for code review.
- **Community Detection**: Uses the Leiden algorithm (via `igraph`) to cluster related code into modules.
- **Interactive Visualization**: Generates a self-contained D3.js force-directed graph.
- **Polyglot Parsing**: 
    - **Vue SFCs**: Splits files into script/template blocks and executes recursive TS/JS parsing.
    - **Jupyter Notebooks**: Strips magics and concatenates code cells for unified Python analysis.

## Search Implementation: Hybrid Ranking Pipeline

The search implementation lives in [`search.py`](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/search.py) and runs a **4-phase pipeline**: two independent retrieval lists → RRF fusion → heuristic boosting → kind filtering.

### Phase 1 — Two Independent Retrieval Lists

**FTS5 BM25** ([`_fts_search`](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/search.py#L181-L204)):
- SQLite FTS5 virtual table `nodes_fts` with `porter unicode61` tokenizer
- Indexed fields: `name`, `qualified_name`, `file_path`, `signature`
- Query is double-quote-escaped to prevent FTS5 operator injection
- Returns `(node_id, -bm25_rank)` — negated because FTS5 rank is negative

**Vector cosine similarity** ([`_embedding_search`](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/search.py#L212-L247)):
- Optional — only runs if `embed_graph_tool` has been called first
- Providers: `local` (sentence-transformers), `openai`, `google`, `minimax`
- Returns `(node_id, cosine_score)` after mapping qualified names to node IDs
- Gracefully returns empty list if embeddings unavailable — FTS5 continues alone

**Fallback chain**: FTS5 + embeddings → FTS5 only → `LIKE` keyword matching

The two lists are **completely independent** — a node that ranks high in embeddings but low in BM25 (or vice versa) is still a valid candidate for the merged result.

### Phase 2 — Reciprocal Rank Fusion ([`rrf_merge`](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/search.py#L150-L173))

```
rrf_score(item) = Σ  1 / (k + rank + 1)    [k = 60, 0-based rank]
```

Each item accumulates contributions from every list it appears in. An item ranking at position 5 in both lists outscores one ranking at position 1 in only one list.

**Why RRF instead of weighted score combination**:
- BM25 and cosine similarity live in incompatible, query-dependent score spaces
- Min-max normalizing BM25 per batch is query-relative (a tight cluster looks the same as a clear winner)
- RRF is hyperparameter-free in terms of score calibration — only `k=60` needed, which is universally robust
- No graph edges or node centrality influence the RRF step — it is purely rank-based

### Phase 3 — Heuristic Score Boosting

After RRF merge, a batch-fetch of all candidate nodes is done (in 450-node batches), then score multipliers are applied:

| Signal | Condition | Multiplier |
|---|---|---|
| PascalCase query | Node kind is `Class` or `Type` | ×1.5 |
| snake_case query | Node kind is `Function` | ×1.5 |
| Query contains `.` | `query` is substring of `qualified_name` | ×2.0 |
| Identifier tokens in query | Any dotted/snake/PascalCase token found in `qualified_name` | ×2.0 |
| Context file boost | Node's `file_path` is in caller-supplied `context_files` | ×1.5 |

Boosts are **multiplicative and stackable** — a PascalCase class in the currently open file can receive ×1.5 × ×1.5 = ×2.25.

Identifier extraction ([`extract_query_identifiers`](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/search.py#L80-L98)) works on natural-language queries too: "Who advances the gin middleware chain via Context.Next" → extracts `Context.Next`, `context.next` — allowing the boost to fire even on conversational queries.

### Phase 4 — Kind Filtering & Result Assembly

After boosted sort, results are truncated to `limit` with an optional `kind` filter (`File`, `Class`, `Function`, `Type`, `Test`) applied at this stage — not earlier — so boosting operates on the full candidate set.

Each result includes: `name`, `qualified_name`, `kind`, `file_path`, `line_start`, `line_end`, `language`, `params`, `return_type`, `signature`, `score`.

### What Is NOT in the Ranking

- **No graph edge traversal** — call graph, import edges, and community membership do not influence search ranking. Graph links are only used by `query_graph_tool`, `traverse_graph_tool`, and `get_impact_radius_tool` as separate, explicit operations.
- **No learned reranker / cross-encoder** — the boosting multipliers are hand-coded heuristics, not a trained model.
- **No PageRank / hub centrality** — `get_hub_nodes_tool` surfaces high-centrality nodes separately but does not feed into search scoring.

### Symbol-Centric Embedding Strategy

Each non-`File` node is the embedding unit. The embedded string is built by [`_node_to_text`](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/embeddings.py#L799-L850) and concatenates **8 components** in order:

| # | Component | Example | Notes |
|---|---|---|---|
| 1 | `Parent.name` (dotted form) | `APIRoute.dispatch_request` | Only if parent exists and kind ≠ File |
| 2 | Bare `name` | `dispatch_request` | Always present |
| 3 | Identifier split into words | `dispatch request` | Skipped if identical to bare name |
| 4 | `kind` lowercased | `function` | Skipped for File nodes |
| 5 | `"in <ParentName>"` phrase | `in APIRoute` | Only if parent exists |
| 6 | Parent split into words | `API Route` | Skipped if identical to parent name |
| 7 | `params` + `"returns <return_type>"` | `(self, environ) returns Response` | Only if present on node |
| 8 | Parent directory name | `routing` | Skipped for `.`, `src`, `lib` |
| 9 | `language` | `python` | Only if present |

The identifier splitter ([`_split_identifier`](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/embeddings.py#L781-L796)) handles `snake_case`, `camelCase`, `PascalCase`, dotted, and hyphenated forms — e.g. `get_route_handler` → `"get route handler"`, `APIRoute` → `"API Route"`.

**Deduplication**: Nodes are re-embedded only when their text hash changes or the provider changes. The hash is stored alongside the vector in the `embeddings` table.

**`File` nodes excluded**: Embedding file-level nodes would dilute symbol-level precision — a query for "authentication middleware" should land on the function, not the file.

## Persistence & Schema Migration
The tool uses a custom migration framework ([migrations.py](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/migrations.py)) to manage the database lifecycle without external dependencies.
- **Versioning**: Schema version is tracked in the `metadata` table via the `schema_version` key.
- **Execution**: `GraphStore` automatically checks for and runs pending migrations during initialization.
- **Milestones**:
    - **v2-v4**: Core structural expansion (signatures, flows, and communities).
    - **v5**: **FTS5 Integration** for hybrid keyword/vector search.
    - **v6**: LLM-optimized summary tables (`flow_snapshots`, `risk_index`) designed to reduce token usage when the MCP server provides context to an AI.
- **Safety**: Uses idempotent SQL (`IF NOT EXISTS`) and transactional rollbacks to prevent DB corruption during aborted builds.

## Database & Performance Trade-offs
The choice of standard SQLite over a specialized Vector DB or `sqlite-vss` extension is a deliberate engineering trade-off:
- **Portability**: By avoiding native vector extensions, the project remains a "pure-pip" install that works instantly on Mac (Intel/M1), Windows, and Linux without compiling C++ binaries.
- **Scale**: At repository scale (1k - 50k nodes), a brute-force Python scan is extremely fast (<50ms), making the complexity of a KNN index (like HNSW) unnecessary.
- **Concurrency**: Uses **Write-Ahead Logging (WAL)** mode to allow the background file-watcher to update the graph database while the AI assistant concurrently performs read-heavy analysis.
- **Ignore**: `.code-review-graphignore` or `.gitignore`.
- **Env Vars**:
    - `CRG_RECURSE_SUBMODULES`: Toggle submodule indexing.
    - `CRG_EMBEDDING_MODEL`: Choose vector model for semantic search.
    - `CRG_DATA_DIR`: Override where `.code-review-graph/` is stored.

## The Parser's Engine: How it works
The `CodeParser` doesn't just "parse"; it translates language-specific syntax into a language-agnostic knowledge graph using three core strategies:

1.  **Normalization Mapping**: Uses `_CLASS_TYPES`, `_FUNCTION_TYPES`, etc., to map disparate AST nodes (e.g., Python's `class_definition` vs. Java's `class_declaration`) to unified `NodeInfo` types.
2.  **Scope Collection**: Two-pass parsing strategy. The first pass (`_collect_file_scope`) maps local definitions and imports. This allows the second pass to resolve names like `init()` to `auth_module.init()` based on local imports.
3.  **Cross-File Resolution**: The `_resolve_call_targets` step takes bare names found by Tree-sitter and qualifies them (`file.py::func_name`) using the import map. Significant complexity is invested in handling TypeScript path aliases and Python module resolution.

### Deconstructed: Node Name (`node_name`) Resolution Flow
Extracting and qualifying a symbol's name follows a specific, language-aware pipeline in the parser:
- **Extraction (`_get_name`)** ([parser.py:L3381](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/parser.py#L3381)):
  - *Language-Specific Overrides*: 
    - **Go**: Extracts name from `field_identifier` (methods) or delegates to `type_spec` (types).
    - **Bash**: Extracts name from the `word` child of `function_definition` nodes.
    - **C/C++/Objective-C**: Checks recursive declarator children (`function_declarator`/`pointer_declarator`) to avoid capturing type specifiers. For Obj-C methods, captures the first identifier part of the selector.
    - **Solidity**: Standardizes constructors, fallback, and receive functions to "constructor", "fallback", and "receive" respectively.
    - **Dart**: Scans exclusively for the `identifier` child of `function_signature` to skip return types.
    - **Lua/Luau**: Extracts the method name from `dot_index_expression` or `method_index_expression` (e.g., `function A.foo()` returns `foo`).
    - **Perl**: Matches `bareword` or `package` node values.
  - *Generic Fallback*: If no language-specific override matches, searches the node's direct children for standard identifier names (e.g. `identifier`, `name`, `type_identifier`, `property_identifier`, `simple_identifier`, or `constant`).
- **Qualification (`_qualify`)** ([parser.py:L3375](file:///Users/minh/gitrepos/local_tools/code-review-graph/code_review_graph/parser.py#L3375)):
  - Prepends the absolute file path and the enclosing class scope.
  - **With Class Context**: `file_path::ClassName.name` (can be recursive: `file_path::OuterClass.InnerClass.name`).
  - **Without Class Context**: `file_path::name`.

## Deep Dive: The Cross-File Linking & Call Graph Pipeline
The parser uses a multi-stage pipeline to resolve bare call identifiers (like `login()`) in `file_a.py` to their absolute definition nodes (e.g., `file_b.ts::login`) across the codebase.

### Stage 1: Local Scope & Import Mapping
During the first pass (`_collect_file_scope`), the parser builds an `import_map` and collects `defined_names` for the file. 
- **Code**: `import { login } from './auth'` -> `import_map['login'] = './auth'`.
- When encountering call nodes during the AST walk, the target is delegated to the call resolution pipeline.

### Stage 2: Initial Call Resolution (`_resolve_call_target`)
For each call, the parser checks the following in order:
1. **Local Definition**: If the call name matches a key in `defined_names`, it is qualified immediately with the current file path: `_qualify(call_name, file_path, None)`.
2. **Import Map Match**: If the call name exists in `import_map`, it proceeds to the physical module and symbol resolution stages.
3. **Unresolved Fallback**: If neither, the parser retains the bare `call_name` as the target.

### Stage 3: Physical Module Resolution (`_resolve_module_to_file`)
The parser converts the import source (e.g., `./auth` or a package import) to a concrete absolute path:
- **Python**: Replaces dots with slashes and walks up directory parents checking for `.py` or `/__init__.py` files.
- **JS/TS/Vue**: Resolves relative imports by trying extensions (`.ts`, `.tsx`, `.js`, etc.) or matching `index` files inside subdirectories. Resolves non-relative paths using `tsconfig.json` path aliases via `TsconfigResolver`.
- **Dart**: Resolves package URIs (`package:<name>/<sub_path>`) back to absolute paths by looking up a matching `pubspec.yaml` in parent directories.

### Stage 4: Export/Barrel Chasing (`_resolve_exported_symbol`)
Often the resolved file is an entrypoint or barrel file (like `index.ts`) that re-exports symbols.
- **Recursive Scan**: The parser reads the target file and parses it.
- **Local Check**: If the target contains a local declaration for the symbol, the search terminates there.
- **Re-Export Check**: If the file re-exports it (`export { login } from './internal'` or `export * from './internal'`), the parser recursively calls `_resolve_exported_symbol` on the target module.
- **Final Link**: The caller and fully resolved target are joined by a `CALLS` edge.

### Stage 5: Post-Parse Local Call Linking (`_resolve_call_targets`)
After the AST walk completes for a file, the parser runs a final pass over all extracted edges. Any remaining bare `CALLS` or `REFERENCES` targets are matched against the file's local symbol table (`nodes`). This ensures that late-defined or forward-referenced symbols within the same file are correctly qualified.

## Side Effect Audit
- **Disk**: Database lives in `.code-review-graph/graph.db`.
- **Git**: Heavy reliance on `git ls-files` and `git diff`.
- **Subprocesses**: Uses `subprocess.run` to call Git; requires Git to be in PATH.

## Testing
- **Suite**: `pytest` located in `tests/`.
- **Patterns**:
  - `test_parser.py`: Unit tests for language extraction.
  - `test_incremental.py`: Verifies Git-based update logic.
  - `test_integration_v2.py`: End-to-end flow checks using file fixtures.
