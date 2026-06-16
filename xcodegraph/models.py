"""XCodeGraph — Python SystemVerilog Code Intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── NodeKind ────────────────────────────────────────────────────────────────

class NodeKind(str, Enum):
    # RTL
    MODULE = "module"
    INTERFACE = "interface"
    PACKAGE = "package"
    CLASS = "class"
    FUNCTION = "function"
    TASK = "task"
    INSTANCE = "instance"
    IMPORT = "import"
    PARAMETER = "parameter"
    TYPEDEF = "typedef"

    # Verification — TLM
    TLMINITF = "tlminitf"
    CONFIG_DB_CALL = "config_db_call"

    # Verification — SVA
    PROPERTY = "property"
    SEQUENCE = "sequence"
    ASSERT = "assert"
    ASSUME = "assume"
    COVER_PROPERTY = "cover_property"
    CHECKER = "checker"

    # Verification — Constraints
    CONSTRAINT = "constraint"
    RAND_FIELD = "rand_field"

    # Verification — Coverage
    COVERGROUP = "covergroup"
    COVERPOINT = "coverpoint"
    CROSS = "cross"
    COVERAGE_OPTION = "coverage_option"


# ── EdgeKind ────────────────────────────────────────────────────────────────

class EdgeKind(str, Enum):
    CONTAINS = "CONTAINS"
    INSTANTIATES = "INSTANTIATES"
    EXTENDS = "EXTENDS"
    IMPORTS = "IMPORTS"
    REFERENCES = "REFERENCES"
    CALLS = "CALLS"
    OVERRIDES = "OVERRIDES"
    DECLARES = "DECLARES"
    CROSSES = "CROSSES"
    SOLVES_BEFORE = "SOLVES_BEFORE"


# ── Data Model ──────────────────────────────────────────────────────────────

@dataclass
class Node:
    id: str
    kind: str
    name: str
    full_name: str | None = None
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    col_start: int = 0
    col_end: int = 0
    parent_id: str | None = None
    signature: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    id: int | None = None
    src_id: str = ""
    dst_id: str = ""
    kind: str = ""
    src_name: str = ""
    dst_name: str = ""
    file_path: str = ""
    line: int = 0
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class UnresolvedRef:
    id: int | None = None
    kind: str = ""
    name: str = ""
    file_path: str = ""
    line: int = 0
    context_node_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class FileRecord:
    id: int | None = None
    path: str = ""
    abs_path: str = ""
    sha256: str = ""
    mtime: float = 0.0
    size: int = 0
    language: str = "systemverilog"
    parse_backend: str = "tree-sitter"
    parse_status: str = "ok"
    parse_warnings: str = ""
    indexed_at: str = ""


@dataclass
class ExtractionResult:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    unresolved_refs: list[UnresolvedRef] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class IndexMeta:
    repo_root: str = ""
    git_head: str = ""
    git_branch: str = ""
    filelist_path: str = ""
    filelist_hash: str = ""
    defines_hash: str = ""
    incdirs_hash: str = ""
    schema_version: str = "1"
    parser_version: str = "0.1"
    backend: str = "tree-sitter"
    created_at: str = ""
    updated_at: str = ""
