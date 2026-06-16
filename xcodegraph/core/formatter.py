"""Markdown formatter — renders extraction results as AI-consumable Markdown.

Principles:
- Compact: target 85% smaller than JSON equivalent
- Selective: strip internal DB fields (id, file_id, etc.)
- Guided: append tail hints for next tool call
- Bounded: per-tool character budgets with truncation
"""

from __future__ import annotations

import os

# ── lib boundary ────────────────────────────────────────────────────────────

DEFAULT_LIB_PATHS = ["uvm-1.2/", "uvm_pkg.sv", "uvm_macros.svh"]


def _is_lib_node(file_path: str, lib_paths: list[str] | None = None) -> bool:
    paths = lib_paths or DEFAULT_LIB_PATHS
    return any(p in file_path for p in paths)


# ── source snippet ──────────────────────────────────────────────────────────

def _source_snippet(file_path: str, start: int, end: int, max_lines: int = 40) -> str:
    """Read source and return line-numbered Markdown code block."""
    if not os.path.exists(file_path):
        return ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return ""

    body = lines[start - 1:end]
    if len(body) > max_lines:
        body = body[:max_lines // 2] + ["...\n"] + body[-(max_lines // 4):]

    numbered = []
    for i, line in enumerate(body, start=start):
        n = f"{i:4d}"
        numbered.append(f"  {n} │ {line.rstrip()}")
    return "```systemverilog\n" + "\n".join(numbered) + "\n```"


# ── edge helpers ────────────────────────────────────────────────────────────

def _filter_edges(edges: dict, node_name: str, node_kind: str) -> dict:
    """Filter out noise: file→node containment, empty kinds, lib-path refs."""
    clean: dict[str, list[dict]] = {}
    for kind, items in edges.items():
        filtered = []
        for e in items:
            src = e.get("src_name", "")
            dst = e.get("dst_name", "")
            # Skip file/package containment (already implied by file: field)
            if kind == "CONTAINS" and src != node_name:
                continue
            # Skip empty-name entries
            if not dst:
                continue
            filtered.append(e)
        if filtered:
            clean[kind] = filtered
    return clean


# ── format functions ────────────────────────────────────────────────────────

def format_search_results(query: str, results: list[dict],
                          max_results: int = 20,
                          lib_paths: list[str] | None = None) -> str:
    """Pipe table of search results."""
    # Filter lib-path and file-kind results by default
    paths = lib_paths or DEFAULT_LIB_PATHS
    filtered = [r for r in results
                if not _is_lib_node(r.get("path", ""), paths)
                and r.get("kind") != "file"]
    truncated = filtered != results

    if not filtered:
        return f"## Search: \"{query}\"\n\nNo results found.\n"

    lines = [
        f"## Search: \"{query}\" ({len(filtered)} found)",
        "",
        "| Kind | Name | File | Line |",
        "|------|------|------|------|",
    ]
    shown = filtered[:max_results]
    for r in shown:
        lines.append(f"| {r['kind']} | {r['name']} | {r['path']} | {r['line_start']} |")

    remaining = len(filtered) - max_results
    if remaining > 0:
        lines.append(f"\n*({remaining} more results — narrow your query)*")
    if truncated:
        lines.append(f"\n*({len(results) - len(filtered)} standard-library results hidden)*")

    lines.append(f"\n→ Use `xcodegraph_node <name>` for details and source")
    return "\n".join(lines)


def format_node_detail(node: dict, edges: dict,
                       source_lines: list[str] | None = None,
                       show_source: bool = False,
                       lib_paths: list[str] | None = None) -> str:
    """Rendered node detail with relationships. Source only when show_source=True."""
    name = node["name"]
    kind = node["kind"]
    file_path = node.get("path", "")
    line = node.get("line_start", 0)
    sig = node.get("signature", "")

    # Filter edges
    edges = _filter_edges(edges, name, kind)

    lines = [f"## {name} ({kind})", ""]
    lines.append(f"**Location:** {file_path}:{line}")
    if sig:
        lines.append(f"**Signature:** `{sig}`")

    # Children — grouped: methods (with prototypes) vs fields (with kinds)
    contains = edges.get("CONTAINS", [])
    if contains:
        methods = []
        fields = []
        for c in contains:
            child_name = c["dst_name"]
            ckind = c.get("dst_kind", "")
            csig = c.get("dst_signature", "")
            if ckind in ("function", "task", "method"):
                methods.append((ckind, child_name, csig))
            else:
                fields.append((ckind, child_name))

        if methods:
            lines.append("**Methods:**")
            for ckind, child_name, csig in methods:
                if csig and csig != child_name:
                    lines.append(f"- `{ckind}` `{csig}`")
                else:
                    lines.append(f"- `{ckind}` {child_name}")

        if fields:
            parts = []
            for ckind, child_name in fields:
                if ckind and ckind not in ("class", "module"):
                    parts.append(f"`{ckind}` {child_name}")
                else:
                    parts.append(child_name)
            lines.append(f"**Fields:** {', '.join(parts)}")

    # Relations
    for edge_kind in ("EXTENDS", "REFERENCES", "CALLS", "INSTANTIATES", "OVERRIDES",
                       "IMPORTS", "INCLUDES"):
        items = edges.get(edge_kind, [])
        if not items:
            continue
        names = []
        for e in items:
            dst = e["dst_name"]
            efile = e.get("file", "")
            if _is_lib_node(efile, lib_paths):
                dst += " *(stdlib)*"
            names.append(dst)
        lines.append(f"**{edge_kind}:** {', '.join(names)}")

    lines.append("")

    # Source snippet — only when explicitly requested
    if show_source:
        if source_lines:
            lines.append("### Source")
            lines.append("```systemverilog")
            for i, line_text in enumerate(source_lines, start=node.get("line_start", 1)):
                lines.append(f"  {i:4d} │ {line_text.rstrip()}")
            lines.append("```")
        elif file_path and line and os.path.exists(file_path):
            end = node.get("line_end", line + 1)
            src = _source_snippet(file_path, line, end)
            if src:
                lines.append("### Source")
                lines.append(src)

    # Tail guidance
    if not show_source:
        lines.append(f"→ Use `xcodegraph_node {name} source=true` for full source code")
    else:
        lines.append(f"→ Use `xcodegraph_node <name>` for other symbols")
    return "\n".join(lines)


def format_hierarchy(hierarchy: list[dict], top_name: str,
                     max_depth: int = 10) -> str:
    """Tree view of module hierarchy."""
    if not hierarchy:
        return f"## Hierarchy: {top_name}\n\nNot found.\n"

    lines = [f"## Hierarchy: {top_name}", ""]

    # Group by depth, track last-child markers
    depth_counts: dict[int, int] = {}
    for h in hierarchy:
        d = h.get("depth", 0)
        depth_counts[d] = depth_counts.get(d, 0) + 1
    depth_seen: dict[int, int] = {}

    for h in hierarchy:
        depth = h.get("depth", 0)
        if depth > max_depth:
            lines.append(f"*... ({len(hierarchy) - len(lines) + 2} more levels truncated)*")
            break

        depth_seen[depth] = depth_seen.get(depth, 0) + 1
        is_last = (depth_seen[depth] == depth_counts[depth])

        # Build prefix with vertical lines
        prefix_parts = []
        for d in range(1, depth + 1):
            prev_depth_last = depth_seen.get(d, 0) == depth_counts.get(d, 0) or (d == depth and is_last)
            if d == depth:
                prefix_parts.append("└── " if is_last else "├── ")
            else:
                # Check if there are more siblings at this level
                prefix_parts.append("    " if prev_depth_last else "│   ")
        prefix = "".join(prefix_parts)
        lines.append(f"{prefix}{h['name']} ({h.get('path', '')}:{h.get('line_start', '')})")

    lines.append(f"\n→ Use `xcodegraph_instantiated_by <module>` to find instantiators")
    return "\n".join(lines)


def format_instantiated_by(results: list[dict], target_name: str) -> str:
    """List of instantiators."""
    if not results:
        return f"## Instantiated by: {target_name}\n\nNot found or not instantiated.\n"
    lines = [f"## Instantiated by: {target_name}", ""]
    for r in results:
        lines.append(f"- **{r['name']}** ({r.get('path', '')}:{r.get('line_start', '')})")
    return "\n".join(lines)


def format_edge_list(results: list[dict], kind: str, node_name: str) -> str:
    """Generic edge list (imports/includes/extends)."""
    if not results:
        return f"## {kind} of {node_name}\n\nNone found.\n"
    lines = [f"## {kind} of {node_name}", ""]
    for r in results:
        dst = r.get("dst_name", "?")
        lines.append(f"- **{dst}** ({r.get('path', '')}:{r.get('line', '')})")
    return "\n".join(lines)


def format_file_symbols(symbols: list[dict], file_path: str,
                        max_symbols: int = 30) -> str:
    """File symbol listing."""
    if not symbols:
        return f"## Symbols in {file_path}\n\nNo symbols found.\n"
    lines = [f"## Symbols in {file_path} ({len(symbols)} total)", ""]
    shown = symbols[:max_symbols]
    for s in shown:
        lines.append(f"- **{s['kind']}** `{s['name']}` line {s['line_start']}")
    remaining = len(symbols) - max_symbols
    if remaining > 0:
        lines.append(f"\n*... and {remaining} more symbols*")
    return "\n".join(lines)


def format_status(stats: dict, meta: dict) -> str:
    """Index status summary."""
    lines = [
        "## XCodeGraph Status",
        "",
        f"**Files:** {stats.get('file_count', 0)}",
        f"**Nodes:** {stats.get('node_count', 0)}",
        f"**Edges:** {stats.get('edge_count', 0)}",
        f"**Unresolved:** {stats.get('unresolved_ref_count', 0)}",
    ]
    # Only output 3 key meta fields
    for key in ("git_head", "backend", "schema_version"):
        if meta.get(key):
            lines.append(f"**{key}:** {meta[key]}")
    return "\n".join(lines)


def format_definition(node: dict) -> str:
    """Single-line definition location."""
    return (f"## {node['name']} ({node['kind']})\n\n"
            f"**Location:** {node['path']}:{node['line_start']}\n")


def format_summary(summary_text: str) -> str:
    return f"## Summary\n\n{summary_text}\n"


def format_reindex_result(result: dict) -> str:
    lines = [f"## Reindex",
             f"**Files:** {result.get('indexed_files', result.get('nodes_added', 'N/A'))}",
             f"**Nodes:** {result.get('total_nodes', result.get('nodes_added', 'N/A'))}"]
    if result.get("errors"):
        lines.append(f"**Errors:** {len(result['errors'])}")
    return "\n".join(lines)
