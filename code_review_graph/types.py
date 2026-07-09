"""Shared type definitions and data models for code-review-graph.

This module contains language-agnostic types used by both the parser
(producer) and the graph storage (consumer) to avoid circular imports.
"""

from __future__ import annotations

from typing import Literal, TypeAlias


# ---------------------------------------------------------------------------
# Core Type Aliases
# ---------------------------------------------------------------------------

Language: TypeAlias = Literal[
    "python",
    "javascript",
    "typescript",
    "tsx",
    "go",
    "rust",
    "java",
    "csharp",
    "ruby",
    "cpp",
    "c",
    "kotlin",
    "swift",
    "php",
    "scala",
    "solidity",
    "vue",
    "dart",
    "r",
    "perl",
    "lua",
    "luau",
    "objc",
    "bash",
    "elixir",
    "notebook",
    "markdown",
]

NodeKind: TypeAlias = Literal["File", "Class", "Function", "Type", "Test", "Section"]

EdgeKind: TypeAlias = Literal[
    "CALLS",
    "IMPORTS_FROM",
    "INHERITS",
    "IMPLEMENTS",
    "CONTAINS",
    "TESTED_BY",
    "DEPENDS_ON",
    "REFERENCES",
]
