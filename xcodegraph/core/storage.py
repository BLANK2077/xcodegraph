"""SQLite storage layer for XCodeGraph."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

from ..models import Edge, ExtractionResult, FileRecord, IndexMeta, Node, UnresolvedRef


class Storage:
    """Manages the SQLite index database."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    # ── schema ──────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())
        self.conn.commit()

    # ── file operations ─────────────────────────────────────────────────

    def upsert_file(self, path: str, content: bytes) -> FileRecord:
        abs_path = os.path.abspath(path)
        sha = hashlib.sha256(content).hexdigest()
        mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0
        size = len(content)

        cur = self.conn.execute(
            "SELECT id, sha256 FROM files WHERE path = ?",
            (path,),
        )
        row = cur.fetchone()
        if row and row["sha256"] == sha:
            return FileRecord(
                id=row["id"], path=path, abs_path=abs_path, sha256=sha,
                mtime=mtime, size=size,
            )

        if row:
            # delete old data for this file
            self.conn.execute("DELETE FROM edges WHERE file_id = ?", (row["id"],))
            self.conn.execute("DELETE FROM nodes WHERE file_id = ?", (row["id"],))
            self.conn.execute("DELETE FROM files WHERE id = ?", (row["id"],))

        indexed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        cur = self.conn.execute(
            "INSERT INTO files (path, abs_path, sha256, mtime, size, indexed_at) VALUES (?,?,?,?,?,?)",
            (path, abs_path, sha, mtime, size, indexed_at),
        )
        self.conn.commit()
        return FileRecord(
            id=cur.lastrowid or 0, path=path, abs_path=abs_path,
            sha256=sha, mtime=mtime, size=size, indexed_at=indexed_at,
        )

    def get_file(self, path: str) -> FileRecord | None:
        row = self.conn.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
        if not row:
            return None
        return FileRecord(**{k: row[k] for k in row.keys()})

    # ── extraction storage ──────────────────────────────────────────────

    def store_extraction(self, file_record: FileRecord, result: ExtractionResult) -> int:
        """Store extracted nodes/edges/refs; return node count."""
        file_id = file_record.id or 0
        node_map: dict[str, int] = {}  # external_id → DB rowid

        # Insert nodes
        for node in result.nodes:
            cur = self.conn.execute(
                """INSERT INTO nodes (kind, name, full_name, file_id, line_start, line_end,
                          col_start, col_end, parent_id, signature, attributes_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    node.kind, node.name, node.full_name, file_id,
                    node.line_start, node.line_end, node.col_start, node.col_end,
                    None, node.signature,
                    json.dumps(node.attributes) if node.attributes else None,
                ),
            )
            node_map[node.id] = cur.lastrowid

        # Update parent_id references
        for node in result.nodes:
            if node.parent_id and node.parent_id in node_map:
                db_id = node_map[node.id]
                parent_db_id = node_map[node.parent_id]
                self.conn.execute(
                    "UPDATE nodes SET parent_id = ? WHERE id = ?",
                    (parent_db_id, db_id),
                )

        # Insert edges
        for edge in result.edges:
            src_db = node_map.get(edge.src_id)
            dst_db = node_map.get(edge.dst_id)
            if src_db and dst_db:
                self.conn.execute(
                    """INSERT INTO edges (src_id, dst_id, kind, src_name, dst_name, file_id, line, detail_json)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (src_db, dst_db, edge.kind, edge.src_name, edge.dst_name, file_id, edge.line,
                     json.dumps(edge.detail) if edge.detail else None),
                )

        # Insert unresolved refs
        for ref in result.unresolved_refs:
            ctx_db = node_map.get(ref.context_node_id) if ref.context_node_id else None
            self.conn.execute(
                """INSERT INTO unresolved_refs (kind, name, file_id, line, context_node_id, detail_json)
                   VALUES (?,?,?,?,?,?)""",
                (ref.kind, ref.name, file_id, ref.line, ctx_db,
                 json.dumps(ref.detail) if ref.detail else None),
            )

        self.conn.commit()
        return len(result.nodes)

    # ── meta operations ─────────────────────────────────────────────────

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
            (key, value),
        )
        self.conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def get_all_meta(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT key, value FROM meta").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ── queries ─────────────────────────────────────────────────────────

    def search_nodes(self, query: str, kind: str | None = None) -> list[dict]:
        """Full-text search via FTS5, with LIKE fallback."""
        # Try FTS5 first — handles multi-word queries and ranks results
        try:
            fts_query = _to_fts_query(query)
            params: list = [fts_query]
            join = "JOIN nodes_fts ON n.id = nodes_fts.rowid"
            where = "nodes_fts MATCH ?"
            order = "ORDER BY rank"
            if kind:
                where += " AND n.kind = ?"
                params.append(kind)
            sql = f"SELECT n.*, f.path FROM nodes n {join} JOIN files f ON n.file_id = f.id WHERE {where} {order} LIMIT 50"
            rows = self.conn.execute(sql, params).fetchall()
            if rows:
                return [dict(r) for r in rows]
        except Exception:
            pass  # FTS5 may fail on special chars; fall through to LIKE

        # LIKE fallback
        sql = "SELECT n.*, f.path FROM nodes n JOIN files f ON n.file_id = f.id WHERE n.name LIKE ?"
        params = [f"%{query}%"]
        if kind:
            sql += " AND n.kind = ?"
            params.append(kind)
        sql += " ORDER BY n.name LIMIT 50"
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def get_node(self, name: str, kind: str | None = None) -> dict | None:
        sql = "SELECT n.*, f.path FROM nodes n JOIN files f ON n.file_id = f.id WHERE n.name = ?"
        params: list = [name]
        if kind:
            sql += " AND n.kind = ?"
            params.append(kind)
        sql += " LIMIT 1"
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def get_node_by_id(self, node_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT n.*, f.path FROM nodes n JOIN files f ON n.file_id = f.id WHERE n.id = ?",
            (node_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_file_symbols(self, file_path: str) -> list[dict]:
        return [
            dict(r) for r in
            self.conn.execute(
                "SELECT n.* FROM nodes n JOIN files f ON n.file_id = f.id WHERE f.path = ? ORDER BY n.line_start",
                (file_path,),
            ).fetchall()
        ]

    def get_edges_for_node(self, node_name: str) -> dict[str, list[dict]]:
        """Return edges grouped by kind for a node.

        Includes both resolved edges and unresolved refs (lightweight resolve).
        """
        node = self.get_node(node_name)
        if not node:
            return {}

        result: dict[str, list[dict]] = {}
        node_id = node["id"]

        # Resolved edges (outgoing + incoming)
        for direction, col in [("out", "src_id"), ("in", "dst_id")]:
            key = "outgoing" if direction == "out" else "incoming"
            rows = self.conn.execute(
                f"""SELECT e.*, sn.name as src_name, dn.name as dst_name
                    FROM edges e
                    JOIN nodes sn ON e.src_id = sn.id
                    JOIN nodes dn ON e.dst_id = dn.id
                    WHERE e.{col} = ?""",
                (node_id,),
            ).fetchall()
            for r in rows:
                d = dict(r)
                kind = d["kind"]
                result.setdefault(kind, [])
                result[kind].append(d)

        # Unresolved refs — filter by context_node_id (belongs to THIS node)
        refs = self.conn.execute(
            "SELECT kind, name, line FROM unresolved_refs WHERE context_node_id = ?",
            (node_id,),
        ).fetchall()
        for r in refs:
            d = dict(r)
            kind = d["kind"]
            d["src_name"] = node["name"]
            d["dst_name"] = d["name"]  # unresolved_refs.name is the target
            result.setdefault(kind, [])
            result[kind].append(d)

        return result

    def get_hierarchy(self, top_name: str, depth: int = 10) -> list[dict]:
        """BFS from a top node following INSTANTIATES edges.

        Checks both resolved edges and unresolved_refs (lightweight resolve).
        """
        top = self.get_node(top_name)
        if not top:
            return []

        visited: set[int] = {top["id"]}
        frontier = [(top, 0)]
        result: list[dict] = []

        while frontier:
            current, d = frontier.pop(0)
            current_with_depth = dict(current)
            current_with_depth["depth"] = d
            result.append(current_with_depth)
            if d >= depth:
                continue

            # Check resolved edges
            edge_rows = self.conn.execute(
                """SELECT dn.*, f.path
                   FROM edges e
                   JOIN nodes sn ON e.src_id = sn.id
                   JOIN nodes dn ON e.dst_id = dn.id
                   JOIN files f ON dn.file_id = f.id
                   WHERE e.kind = 'INSTANTIATES' AND sn.id = ?""",
                (current["id"],),
            ).fetchall()

            # Also check unresolved refs for INSTANTIATES
            current_file_id = current.get("file_id")
            ref_rows = self.conn.execute(
                """SELECT n.*, f.path
                   FROM unresolved_refs ur
                   JOIN nodes n ON ur.name = n.name
                   JOIN files f ON n.file_id = f.id
                   WHERE ur.kind = 'INSTANTIATES'
                     AND ur.file_id = ?
                     AND ur.context_node_id IS NOT NULL""",
                (current_file_id,),
            ).fetchall() if current_file_id else []

            all_rows = {}
            for row in edge_rows:
                all_rows[row["id"]] = dict(row)
            for row in ref_rows:
                all_rows[row["id"]] = dict(row)

            for node_id, row_data in all_rows.items():
                if node_id not in visited:
                    visited.add(node_id)
                    frontier.append((row_data, d + 1))

        return result

    def get_instantiated_by(self, name: str) -> list[dict]:
        """Return all nodes that instantiate the named module/interface.

        Checks both resolved edges and unresolved_refs."""
        target = self.get_node(name)
        if not target:
            return []

        # Resolved edges
        edge_rows = self.conn.execute(
            """SELECT sn.*, f.path
               FROM edges e
               JOIN nodes sn ON e.src_id = sn.id
               JOIN files f ON sn.file_id = f.id
               WHERE e.kind = 'INSTANTIATES' AND e.dst_id = ?""",
            (target["id"],),
        ).fetchall()

        # Unresolved refs: find instantiator modules
        ref_rows = self.conn.execute(
            """SELECT DISTINCT n.*, f.path
               FROM unresolved_refs ur
               JOIN files src_f ON ur.file_id = src_f.id
               JOIN nodes n ON n.file_id = src_f.id
               JOIN files f ON n.file_id = f.id
               WHERE ur.kind = 'INSTANTIATES' AND ur.name = ?
                 AND n.kind IN ('module', 'interface')""",
            (name,),
        ).fetchall()

        seen = set()
        result = []
        for row in edge_rows + ref_rows:
            r = dict(row)
            if r["id"] not in seen:
                seen.add(r["id"])
                result.append(r)

        return result

    def get_edges_by_kind(self, name: str, kind: str) -> list[dict]:
        """Generic query for IMPORTS/EXTENDS/INCLUDES edges."""
        node = self.get_node(name)
        if not node:
            return []

        rows = self.conn.execute(
            """SELECT e.*, dn.name as dst_name, f.path
               FROM edges e
               JOIN nodes dn ON e.dst_id = dn.id
               JOIN files f ON dn.file_id = f.id
               WHERE e.src_id = ? AND e.kind = ?""",
            (node["id"], kind),
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        return {
            "file_count": self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "node_count": self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
            "edge_count": self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
            "unresolved_ref_count": self.conn.execute("SELECT COUNT(*) FROM unresolved_refs").fetchone()[0],
        }

    def close(self) -> None:
        self.conn.close()


def _to_fts_query(user_query: str) -> str:
    """Convert a user search string to an FTS5 query.

    Multi-word queries become AND terms: "axi master" → "axi AND master"
    Single-word queries are quoted for exact prefix match.
    """
    terms = user_query.strip().split()
    if len(terms) == 1:
        return f'"{terms[0]}"*'
    return " AND ".join(f'"{t}"*' for t in terms)
