"""XCodeGraph CLI — SystemVerilog code intelligence for verification agents."""

from __future__ import annotations

import argparse
import json
import os
import sys

from xcodegraph.core.indexer import Indexer
from xcodegraph.core.storage import Storage

DB_DEFAULT = ".xcodegraph/index.sqlite"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="xcodegraph",
        description="Python SystemVerilog Code Intelligence",
    )
    sub = parser.add_subparsers(dest="command")

    # index
    p = sub.add_parser("index", help="Build the index")
    p.add_argument("--filelist", "-f", help="VCS .f filelist path")
    p.add_argument("--root", "-r", help="Root directory to scan")
    p.add_argument("--db", default=DB_DEFAULT, help="SQLite database path")
    p.add_argument("--define", "-d", action="append", help="+define+MACRO=VAL")

    # status
    p = sub.add_parser("status", help="Show index status")
    p.add_argument("--db", default=DB_DEFAULT)
    p.add_argument("--json", action="store_true")

    # search
    p = sub.add_parser("search", help="Search for symbols")
    p.add_argument("query")
    p.add_argument("--kind", "-k")
    p.add_argument("--db", default=DB_DEFAULT)
    p.add_argument("--json", action="store_true")

    # node
    p = sub.add_parser("node", help="Show node details")
    p.add_argument("name")
    p.add_argument("--kind", "-k")
    p.add_argument("--db", default=DB_DEFAULT)
    p.add_argument("--json", action="store_true")

    # definition
    p = sub.add_parser("definition", help="Jump to definition")
    p.add_argument("name")
    p.add_argument("--db", default=DB_DEFAULT)
    p.add_argument("--json", action="store_true")

    # file-symbols
    p = sub.add_parser("file-symbols", help="List all symbols in a file")
    p.add_argument("file")
    p.add_argument("--db", default=DB_DEFAULT)
    p.add_argument("--json", action="store_true")

    # serve
    p = sub.add_parser("serve", help="Start MCP server (stdio transport)")
    p.add_argument("--db", default=DB_DEFAULT)

    # clean
    p = sub.add_parser("clean", help="Remove the index database")
    p.add_argument("--db", default=DB_DEFAULT)

    args = parser.parse_args()
    dispatch(args)


def dispatch(args: argparse.Namespace) -> None:
    cmd = args.command

    if cmd == "index":
        cmd_index(args)
    elif cmd == "status":
        cmd_status(args)
    elif cmd == "search":
        cmd_search(args)
    elif cmd == "node":
        cmd_node(args)
    elif cmd == "definition":
        cmd_definition(args)
    elif cmd == "file-symbols":
        cmd_file_symbols(args)
    elif cmd == "serve":
        cmd_serve(args)
    elif cmd == "clean":
        cmd_clean(args)
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
            if "=" in d:
                k, v = d.split("=", 1)
                defines[k] = v
            else:
                defines[d] = ""

    indexer = Indexer(db_path)

    if args.filelist:
        result = indexer.index_filelist(args.filelist, defines)
        print(f"Indexed {result['indexed_files']} files, {result['total_nodes']} nodes "
              f"({result['duration_ms']:.0f}ms)")
    elif args.root:
        result = indexer.index_directory(args.root)
        print(f"Indexed {result['indexed_files']} files, {result['total_nodes']} nodes "
              f"({result['duration_ms']:.0f}ms)")
    else:
        print("Specify --filelist or --root", file=sys.stderr)
        sys.exit(1)

    if result["errors"]:
        print(f"  {len(result['errors'])} errors")
        for e in result["errors"][:5]:
            print(f"    {e}")

    indexer.close()
    stats = Storage(db_path).stats()
    print(f"  DB: {stats['node_count']} nodes, {stats['edge_count']} edges, "
          f"{stats['unresolved_ref_count']} unresolved refs")


def cmd_status(args: argparse.Namespace) -> None:
    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        output({"status": "no_index", "db_path": db_path}, args)
        return

    storage = Storage(db_path)
    stats = storage.stats()
    meta = storage.get_all_meta()
    status = {
        "status": "ok",
        "db_path": db_path,
        **stats,
        "meta": meta,
    }
    storage.close()
    output(status, args)


def cmd_search(args: argparse.Namespace) -> None:
    storage = Storage(os.path.abspath(args.db))
    results = storage.search_nodes(args.query, args.kind)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{r['kind']:16s} {r['name']:40s} {r['path']}:{r['line_start']}")
    storage.close()


def cmd_node(args: argparse.Namespace) -> None:
    storage = Storage(os.path.abspath(args.db))
    node = storage.get_node(args.name, args.kind)
    if not node:
        print(f"Not found: {args.name}", file=sys.stderr)
        sys.exit(1)

    edges = storage.get_edges_for_node(args.name)
    result = {"node": node, "edges": edges}
    output(result, args)
    storage.close()


def cmd_definition(args: argparse.Namespace) -> None:
    storage = Storage(os.path.abspath(args.db))
    node = storage.get_node(args.name)
    if not node:
        print(f"Not found: {args.name}", file=sys.stderr)
        sys.exit(1)
    output(node, args)
    storage.close()


def cmd_file_symbols(args: argparse.Namespace) -> None:
    storage = Storage(os.path.abspath(args.db))
    symbols = storage.get_file_symbols(args.file)
    if args.json:
        print(json.dumps(symbols, indent=2))
    else:
        for s in symbols:
            print(f"{s['kind']:16s} {s['name']:40s} line {s['line_start']}")
    storage.close()


def cmd_serve(args: argparse.Namespace) -> None:
    """Start MCP server using official MCP SDK (stdio transport)."""
    db_path = os.path.abspath(args.db)
    from xcodegraph.mcp_server import create_server
    mcp = create_server(db_path)
    mcp.run(transport="stdio")


def cmd_clean(args: argparse.Namespace) -> None:
    db_path = os.path.abspath(args.db)
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed {db_path}")
    else:
        print(f"No index at {db_path}")


def output(data: dict | list, args: argparse.Namespace) -> None:
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2))
    else:
        _pretty(data)


def _pretty(data: dict | list, indent: int = 0) -> None:
    prefix = "  " * indent
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                print(f"{prefix}{k}:")
                _pretty(v, indent + 1)
            else:
                print(f"{prefix}{k}: {v}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                print(f"{prefix}-")
                _pretty(item, indent + 1)
            else:
                print(f"{prefix}- {item}")


if __name__ == "__main__":
    main()
