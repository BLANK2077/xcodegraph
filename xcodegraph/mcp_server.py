"""XCodeGraph MCP Server — thin adapter over core API, powered by official MCP SDK.

Architecture: MCP handler → parameter validation → core API → format → return
Never: parsing logic, SQL queries, or business state in handlers.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from xcodegraph.core.storage import Storage

# Global reference — set by create_server() before tools are called
_DB_PATH: str = ""


def _storage() -> Storage:
    return Storage(_DB_PATH)


def create_server(db_path: str) -> FastMCP:
    """Create a configured FastMCP server tied to a database path.

    Usage:
        mcp = create_server(".xcodegraph/index.sqlite")
        mcp.run(transport="stdio")
    """
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
    def xcodegraph_status() -> dict[str, Any]:
        """Get index status: file/node/edge counts and metadata."""
        s = _storage()
        try:
            stats = s.stats()
            meta = s.get_all_meta()
            return {"status": "ok", **stats, "db_path": _DB_PATH, "meta": meta}
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_search(query: str, kind: str | None = None) -> dict[str, Any]:
        """Search for SystemVerilog symbols by name. Optionally filter by kind (module/class/interface/parameter/typedef/property/sequence/constraint/covergroup)."""
        s = _storage()
        try:
            results = s.search_nodes(query, kind)
            return {
                "status": "ok",
                "count": len(results),
                "results": [
                    {"kind": r["kind"], "name": r["name"], "file": r["path"], "line": r["line_start"]}
                    for r in results
                ],
            }
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_node(name: str, kind: str | None = None) -> dict[str, Any]:
        """Get details for a named code symbol including related edges (CONTAINS, EXTENDS, INSTANTIATES, IMPORTS, CALLS)."""
        s = _storage()
        try:
            node = s.get_node(name, kind)
            if not node:
                return {"status": "not_found", "name": name}
            edges = s.get_edges_for_node(name)
            return {
                "status": "ok",
                "node": {
                    "kind": node["kind"], "name": node["name"],
                    "file": node["path"], "line": node["line_start"],
                    "signature": node.get("signature"),
                },
                "edges": _simplify_edges(edges),
            }
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_definition(name: str) -> dict[str, Any]:
        """Get the file and line location where a symbol is defined."""
        s = _storage()
        try:
            node = s.get_node(name)
            if not node:
                return {"status": "not_found", "name": name}
            return {
                "status": "ok", "kind": node["kind"], "name": node["name"],
                "file": node["path"], "line": node["line_start"],
            }
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_file_symbols(file_path: str) -> dict[str, Any]:
        """List all code symbols found in a given source file."""
        s = _storage()
        try:
            symbols = s.get_file_symbols(file_path)
            return {
                "status": "ok", "count": len(symbols),
                "symbols": [
                    {"kind": sym["kind"], "name": sym["name"], "line": sym["line_start"]}
                    for sym in symbols
                ],
            }
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_hierarchy(name: str, depth: int = 10) -> dict[str, Any]:
        """Build the module/instance hierarchy tree from a top module. Depth controls nesting level (default 10)."""
        s = _storage()
        try:
            hierarchy = s.get_hierarchy(name, depth)
            return {
                "status": "ok", "count": len(hierarchy),
                "hierarchy": [
                    {"kind": h["kind"], "name": h["name"], "depth": h["depth"], "file": h.get("path")}
                    for h in hierarchy
                ],
            }
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_instantiated_by(name: str) -> dict[str, Any]:
        """Find all modules that instantiate the given module or interface."""
        s = _storage()
        try:
            result = s.get_instantiated_by(name)
            return {
                "status": "ok", "count": len(result),
                "instantiated_by": [
                    {"kind": r["kind"], "name": r["name"], "file": r.get("path"), "line": r.get("line_start")}
                    for r in result
                ],
            }
        finally:
            s.close()

    @mcp.tool()
    def xcodegraph_imports(name: str) -> dict[str, Any]:
        """List packages imported by the given node."""
        return _edge_query(name, "IMPORTS")

    @mcp.tool()
    def xcodegraph_includes(name: str) -> dict[str, Any]:
        """List files included by the given file via `include."""
        return _edge_query(name, "INCLUDES")

    @mcp.tool()
    def xcodegraph_extends(name: str) -> dict[str, Any]:
        """List base classes extended by the given class."""
        return _edge_query(name, "EXTENDS")

    @mcp.tool()
    def xcodegraph_reindex_file(file_path: str) -> dict[str, Any]:
        """Re-index a single file after modification. The file must be part of an already-indexed project."""
        from xcodegraph.core.parser import SVParser
        s = _storage()
        try:
            if not os.path.exists(file_path):
                return {"status": "error", "reason": f"File not found: {file_path}"}
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
            file_rec = s.upsert_file(file_path, source.encode("utf-8"))
            parser = SVParser()
            result = parser.extract(file_path, source)
            count = s.store_extraction(file_rec, result)
            return {"status": "ok", "file": file_path, "nodes_added": count}
        finally:
            s.close()

    # ── edge query helper ──────────────────────────────────────────

    def _edge_query(name: str, kind: str) -> dict[str, Any]:
        s = _storage()
        try:
            results = s.get_edges_by_kind(name, kind)
            return {
                "status": "ok", "count": len(results), "kind": kind,
                "results": [
                    {"dst_name": r.get("dst_name", ""), "file": r.get("path"), "line": r.get("line")}
                    for r in results
                ],
            }
        finally:
            s.close()

    return mcp


def _simplify_edges(edges: dict[str, list[dict]]) -> list[dict]:
    """Simplify edge output for MCP responses."""
    result = []
    for kind, items in edges.items():
        for item in items:
            result.append({
                "kind": kind,
                "src_name": item.get("src_name", ""),
                "dst_name": item.get("dst_name", ""),
            })
    return result
