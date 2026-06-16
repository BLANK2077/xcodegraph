"""XCodeGraph MCP Server — thin adapter over core API, powered by official MCP SDK.

All tools return Markdown strings for direct AI consumption.
Architecture: MCP handler → parameter validation → core API → format_*() → return str
Never: parsing logic, SQL queries, or business state in handlers.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from xcodegraph.core.storage import Storage
from xcodegraph.core import formatter

_DB_PATH: str = ""


def _storage() -> Storage:
    return Storage(_DB_PATH)


def create_server(db_path: str) -> FastMCP:
    global _DB_PATH
    _DB_PATH = db_path

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Index not found: {db_path}")

    mcp = FastMCP(
        "xcodegraph",
        instructions="""XCodeGraph — SystemVerilog code intelligence for verification agents.

Capabilities:
- Search for modules, interfaces, classes, parameters, typedefs, SVA items
- Browse module hierarchy and instantiation chains
- Find definitions and file symbols
- Query UVM class inheritance

Best practices:
- Start with xcodegraph_search for keyword-based queries
- Use xcodegraph_hierarchy to understand module instantiation trees
- Use xcodegraph_node for full context about a specific symbol
""",
    )

    # ── tools ──────────────────────────────────────────────────────

    @mcp.tool()
    def xcodegraph_status() -> str:
        """Get index status: file/node/edge counts and metadata."""
        s = _storage()
        try:
            return formatter.format_status(s.stats(), s.get_all_meta())
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_search(query: str, kind: str | None = None) -> str:
        """Search for SystemVerilog symbols by name. Returns Markdown table."""
        s = _storage()
        try:
            results = s.search_nodes(query, kind)
            return formatter.format_search_results(query, results)
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_node(name: str, kind: str | None = None, source: bool = False) -> str:
        """Get details for a symbol with relationships. Set source=true to include source code."""
        s = _storage()
        try:
            node = s.get_node(name, kind)
            if not node:
                return f"## {name}\n\nNot found in index.\n"
            edges = s.get_edges_for_node(name)
            return formatter.format_node_detail(node, edges, show_source=source)
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_definition(name: str) -> str:
        """Get the file and line location where a symbol is defined."""
        s = _storage()
        try:
            node = s.get_node(name)
            if not node:
                return f"## {name}\n\nNot found.\n"
            return formatter.format_definition(node)
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_file_symbols(file_path: str) -> str:
        """List all code symbols found in a given source file."""
        s = _storage()
        try:
            symbols = s.get_file_symbols(file_path)
            return formatter.format_file_symbols(symbols, file_path)
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_hierarchy(name: str, depth: int = 10) -> str:
        """Build the module/instance hierarchy tree from a top module."""
        s = _storage()
        try:
            hierarchy = s.get_hierarchy(name, depth)
            return formatter.format_hierarchy(hierarchy, name)
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_instantiated_by(name: str) -> str:
        """Find all modules that instantiate the given module or interface."""
        s = _storage()
        try:
            results = s.get_instantiated_by(name)
            return formatter.format_instantiated_by(results, name)
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_imports(name: str) -> str:
        """List packages imported by the given node."""
        return _edge_tool(name, "IMPORTS")

    @mcp.tool()
    def xcodegraph_includes(name: str) -> str:
        """List files included by the given file via `include."""
        return _edge_tool(name, "INCLUDES")

    @mcp.tool()
    def xcodegraph_extends(name: str) -> str:
        """List base classes extended by the given class."""
        return _edge_tool(name, "EXTENDS")

    @mcp.tool()
    def xcodegraph_conditionals(file_path: str) -> str:
        """Show conditional compilation blocks (ifdef/ifndef) for a file."""
        s = _storage()
        try:
            conditionals = s.get_conditionals(file_path)
            return formatter.format_conditionals(conditionals, file_path)
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_reindex_file(file_path: str) -> str:
        """Re-index a single file after modification."""
        from xcodegraph.core.parser import SVParser
        s = _storage()
        try:
            if not os.path.exists(file_path):
                return f"## Reindex\n\nError: file not found: {file_path}\n"
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
            file_rec = s.upsert_file(file_path, source.encode("utf-8"))
            parser = SVParser()
            result = parser.extract(file_path, source)
            count = s.store_extraction(file_rec, result)
            return formatter.format_reindex_result({"nodes_added": count})
        finally:
            s.close()

    # ── helpers ──────────────────────────────────────────────────────

    def _edge_tool(name: str, kind: str) -> str:
        s = _storage()
        try:
            results = s.get_edges_by_kind(name, kind)
            return formatter.format_edge_list(results, kind, name)
        finally:
            s.close()

    return mcp
