"""XCodeGraph MCP Server — thin adapter over core API.

Architecture: MCP handler → parameter validation → core API → format → return
Never: parsing logic, SQL queries, or business state in handlers.
"""

from __future__ import annotations

import json
import os
from typing import Any

from xcodegraph.core.storage import Storage


class XCodeGraphMCPServer:
    """MCP server wrapping Storage queries — no business logic here."""

    def __init__(self, db_path: str):
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Index not found: {db_path}")
        self.db_path = db_path

    # ── tool handlers ──────────────────────────────────────────────────

    def tool_status(self) -> dict[str, Any]:
        """Return index status."""
        s = Storage(self.db_path)
        try:
            stats = s.stats()
            meta = s.get_all_meta()
            return {
                "status": "ok",
                **stats,
                "db_path": self.db_path,
                "meta": meta,
            }
        finally:
            s.close()

    def tool_search(self, query: str, kind: str | None = None) -> dict[str, Any]:
        """Search nodes by name."""
        s = Storage(self.db_path)
        try:
            results = s.search_nodes(query, kind)
            return {
                "status": "ok",
                "count": len(results),
                "results": [
                    {"kind": r["kind"], "name": r["name"],
                     "file": r["path"], "line": r["line_start"]}
                    for r in results
                ],
            }
        finally:
            s.close()

    def tool_node(self, name: str, kind: str | None = None) -> dict[str, Any]:
        """Get node details with related edges."""
        s = Storage(self.db_path)
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

    def tool_definition(self, name: str) -> dict[str, Any]:
        """Get definition location."""
        s = Storage(self.db_path)
        try:
            node = s.get_node(name)
            if not node:
                return {"status": "not_found", "name": name}
            return {
                "status": "ok",
                "kind": node["kind"],
                "name": node["name"],
                "file": node["path"],
                "line": node["line_start"],
            }
        finally:
            s.close()

    def tool_file_symbols(self, file_path: str) -> dict[str, Any]:
        """List all symbols in a file."""
        s = Storage(self.db_path)
        try:
            symbols = s.get_file_symbols(file_path)
            return {
                "status": "ok",
                "count": len(symbols),
                "symbols": [
                    {"kind": sym["kind"], "name": sym["name"],
                     "line": sym["line_start"]}
                    for sym in symbols
                ],
            }
        finally:
            s.close()

    def tool_hierarchy(self, name: str, depth: int = 10) -> dict[str, Any]:
        """Get module hierarchy from top module."""
        s = Storage(self.db_path)
        try:
            hierarchy = s.get_hierarchy(name, depth)
            return {
                "status": "ok",
                "count": len(hierarchy),
                "hierarchy": [
                    {"kind": h["kind"], "name": h["name"],
                     "depth": h["depth"], "file": h.get("path")}
                    for h in hierarchy
                ],
            }
        finally:
            s.close()

    def tool_instantiated_by(self, name: str) -> dict[str, Any]:
        """Find all instantiators of a module/interface."""
        s = Storage(self.db_path)
        try:
            result = s.get_instantiated_by(name)
            return {
                "status": "ok",
                "count": len(result),
                "instantiated_by": [
                    {"kind": r["kind"], "name": r["name"],
                     "file": r.get("path"), "line": r.get("line_start")}
                    for r in result
                ],
            }
        finally:
            s.close()

    def tool_imports(self, name: str) -> dict:
        return self._edge_query(name, "IMPORTS")

    def tool_includes(self, name: str) -> dict:
        return self._edge_query(name, "INCLUDES")

    def tool_extends(self, name: str) -> dict:
        return self._edge_query(name, "EXTENDS")

    def _edge_query(self, name: str, kind: str) -> dict[str, Any]:
        s = Storage(self.db_path)
        try:
            results = s.get_edges_by_kind(name, kind)
            return {
                "status": "ok",
                "count": len(results),
                "kind": kind,
                "results": [
                    {"dst_name": r.get("dst_name", ""),
                     "file": r.get("path"), "line": r.get("line")}
                    for r in results
                ],
            }
        finally:
            s.close()


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
