"""XCodeGraph CLI — SystemVerilog code intelligence for verification agents.

Default output: Markdown. Use --json for machine-readable output.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from xcodegraph.core import formatter
from xcodegraph.core.indexer import Indexer
from xcodegraph.core.storage import Storage

DB_DEFAULT = ".xcodegraph/index.sqlite"


def main() -> None:
    parser = argparse.ArgumentParser(prog="xcodegraph",
                                     description="Python SystemVerilog Code Intelligence")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("index", help="Build the index")
    p.add_argument("--filelist", "-f", help="VCS .f filelist path")
    p.add_argument("--root", "-r", help="Root directory to scan")
    p.add_argument("--db", default=DB_DEFAULT, help="SQLite database path")
    p.add_argument("--define", "-d", action="append", help="+define+MACRO=VAL")
    p.add_argument("--resolve", action="store_true", help="Resolve cross-file references after indexing")

    p = sub.add_parser("status", help="Show index status")
    p.add_argument("--db", default=DB_DEFAULT)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("search", help="Search for symbols")
    p.add_argument("query")
    p.add_argument("--kind", "-k")
    p.add_argument("--db", default=DB_DEFAULT)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("node", help="Show node details")
    p.add_argument("name")
    p.add_argument("--kind", "-k")
    p.add_argument("--source", action="store_true", help="Include source code")
    p.add_argument("--db", default=DB_DEFAULT)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("definition", help="Jump to definition")
    p.add_argument("name")
    p.add_argument("--db", default=DB_DEFAULT)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("file-symbols", help="List all symbols in a file")
    p.add_argument("file")
    p.add_argument("--db", default=DB_DEFAULT)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("serve", help="Start MCP server (stdio transport)")
    p.add_argument("--db", default=DB_DEFAULT)

    p = sub.add_parser("hierarchy", help="Show module instantiation tree")
    p.add_argument("name", help="Top module name")
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--db", default=DB_DEFAULT)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("instantiated-by", help="Find instantiators of a module")
    p.add_argument("name")
    p.add_argument("--db", default=DB_DEFAULT)
    p.add_argument("--json", action="store_true")

    for cmd in ["imports", "includes", "extends"]:
        p = sub.add_parser(cmd, help=f"List {cmd} of a node")
        p.add_argument("name")
        p.add_argument("--db", default=DB_DEFAULT)
        p.add_argument("--json", action="store_true")

    p = sub.add_parser("reindex", help="Re-index after changes")
    p.add_argument("--file", help="Re-index a single file")
    p.add_argument("--filelist", "-f", help="Re-index full filelist")
    p.add_argument("--changed", action="store_true", help="Re-index modified files")
    p.add_argument("--db", default=DB_DEFAULT)

    p = sub.add_parser("summary", help="Generate AI-oriented module summary")
    p.add_argument("name")
    p.add_argument("--db", default=DB_DEFAULT)

    p = sub.add_parser("clean", help="Remove the index database")
    p.add_argument("--db", default=DB_DEFAULT)

    args = parser.parse_args()
    dispatch(args)


def dispatch(args: argparse.Namespace) -> None:
    cmd_map = {
        "index": cmd_index, "status": cmd_status, "search": cmd_search,
        "node": cmd_node, "definition": cmd_definition, "file-symbols": cmd_file_symbols,
        "serve": cmd_serve, "hierarchy": cmd_hierarchy, "instantiated-by": cmd_inst_by,
        "imports": lambda a: cmd_edge_query(a, "IMPORTS"),
        "includes": lambda a: cmd_edge_query(a, "INCLUDES"),
        "extends": lambda a: cmd_edge_query(a, "EXTENDS"),
        "reindex": cmd_reindex, "summary": cmd_summary, "clean": cmd_clean,
    }
    fn = cmd_map.get(args.command)
    if fn:
        fn(args)
    else:
        print("xcodegraph: no command specified. Try 'xcodegraph --help'", file=sys.stderr)
        sys.exit(1)


# ── command implementations ────────────────────────────────────────────────

def cmd_index(args: argparse.Namespace) -> None:
    db_path = os.path.abspath(args.db)
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    defines = {}
    if args.define:
        for d in args.define:
            if "=" in d: k, v = d.split("=", 1); defines[k] = v
            else: defines[d] = ""

    indexer = Indexer(db_path)
    if args.filelist:
        result = indexer.index_filelist(args.filelist, defines)
        print(f"Indexed {result['indexed_files']} files, {result['total_nodes']} nodes ({result['duration_ms']:.0f}ms)")
    elif args.root:
        result = indexer.index_directory(args.root)
        print(f"Indexed {result['indexed_files']} files, {result['total_nodes']} nodes ({result['duration_ms']:.0f}ms)")
    else:
        print("Specify --filelist or --root", file=sys.stderr); sys.exit(1)

    if result["errors"]:
        print(f"  {len(result['errors'])} errors")
        for e in result["errors"][:5]: print(f"    {e}")

    if args.resolve:
        rr = indexer.resolve_references()
        print(f"  Resolved: {rr['resolved']}/{rr['total']} refs")
    indexer.close()

    stats = Storage(db_path).stats()
    print(f"  DB: {stats['node_count']} nodes, {stats['edge_count']} edges, {stats['unresolved_ref_count']} unresolved refs")


def cmd_status(args: argparse.Namespace) -> None:
    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        _out({"status": "no_index", "db_path": db_path}, args); return
    s = Storage(db_path)
    try:
        _out(formatter.format_status(s.stats(), s.get_all_meta()), args)
    finally: s.close()


def cmd_search(args: argparse.Namespace) -> None:
    s = Storage(os.path.abspath(args.db))
    try:
        results = s.search_nodes(args.query, args.kind)
        _out(formatter.format_search_results(args.query, results), args, raw_data=results)
    finally: s.close()


def cmd_node(args: argparse.Namespace) -> None:
    s = Storage(os.path.abspath(args.db))
    try:
        node = s.get_node(args.name, args.kind)
        if not node: print(f"Not found: {args.name}", file=sys.stderr); sys.exit(1)
        edges = s.get_edges_for_node(args.name)
        _out(formatter.format_node_detail(node, edges, show_source=args.source),
             args, raw_data={"node": node, "edges": edges})
    finally: s.close()


def cmd_definition(args: argparse.Namespace) -> None:
    s = Storage(os.path.abspath(args.db))
    try:
        node = s.get_node(args.name)
        if not node: print(f"Not found: {args.name}", file=sys.stderr); sys.exit(1)
        _out(formatter.format_definition(node), args, raw_data=node)
    finally: s.close()


def cmd_file_symbols(args: argparse.Namespace) -> None:
    s = Storage(os.path.abspath(args.db))
    try:
        symbols = s.get_file_symbols(args.file)
        _out(formatter.format_file_symbols(symbols, args.file), args, raw_data=symbols)
    finally: s.close()


def cmd_hierarchy(args: argparse.Namespace) -> None:
    s = Storage(os.path.abspath(args.db))
    try:
        result = s.get_hierarchy(args.name, args.depth)
        _out(formatter.format_hierarchy(result, args.name), args, raw_data=result)
    finally: s.close()


def cmd_inst_by(args: argparse.Namespace) -> None:
    s = Storage(os.path.abspath(args.db))
    try:
        result = s.get_instantiated_by(args.name)
        _out(formatter.format_instantiated_by(result, args.name), args, raw_data=result)
    finally: s.close()


def cmd_edge_query(args: argparse.Namespace, kind: str) -> None:
    s = Storage(os.path.abspath(args.db))
    try:
        result = s.get_edges_by_kind(args.name, kind)
        _out(formatter.format_edge_list(result, kind, args.name), args, raw_data=result)
    finally: s.close()


def cmd_serve(args: argparse.Namespace) -> None:
    db_path = os.path.abspath(args.db)
    from xcodegraph.mcp_server import create_server
    create_server(db_path).run(transport="stdio")


def cmd_reindex(args: argparse.Namespace) -> None:
    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        print(f"No index at {db_path}", file=sys.stderr); sys.exit(1)
    indexer = Indexer(db_path)
    if args.file:
        with open(args.file, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        rec = indexer.storage.upsert_file(args.file, source.encode("utf-8"))
        result = indexer.parser.extract(args.file, source)
        n = indexer.storage.store_extraction(rec, result)
        print(formatter.format_reindex_result({"nodes_added": n}))
    elif args.filelist:
        result = indexer.index_filelist(args.filelist)
        print(formatter.format_reindex_result(result))
    else:
        count = 0
        for row in indexer.storage.conn.execute("SELECT path, abs_path FROM files").fetchall():
            fpath = row["abs_path"] or row["path"]
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        source = f.read()
                    rec = indexer.storage.upsert_file(fpath, source.encode("utf-8"))
                    result = indexer.parser.extract(fpath, source)
                    indexer.storage.store_extraction(rec, result)
                    count += 1
                except Exception: pass
        print(f"Re-indexed {count} files")
    indexer.close()


def cmd_summary(args: argparse.Namespace) -> None:
    from xcodegraph.core.summary import generate_summary
    s = Storage(os.path.abspath(args.db))
    try:
        print(formatter.format_summary(generate_summary(s, args.name)))
    finally: s.close()


def cmd_clean(args: argparse.Namespace) -> None:
    db_path = os.path.abspath(args.db)
    if os.path.exists(db_path): os.remove(db_path); print(f"Removed {db_path}")
    else: print(f"No index at {db_path}")


def _out(data, args, raw_data=None):
    """Output helper: --json prints raw_data, otherwise prints data (already MD)."""
    if getattr(args, "json", False) and raw_data is not None:
        print(json.dumps(raw_data, indent=2))
    else:
        print(data)


if __name__ == "__main__":
    main()
