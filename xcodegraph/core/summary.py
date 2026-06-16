"""AI-oriented module summary generator.

Produces concise natural-language summaries of SV code structures
for use by AI agents (via MCP or CLI).
"""

from __future__ import annotations

from xcodegraph.core.storage import Storage


def generate_summary(storage: Storage, name: str) -> str:
    """Generate a structural summary for a named node.

    Returns a concise description including kind, location, contained
    children, instantiation relationships, and any SVA/coverage info.
    """
    node = storage.get_node(name)
    if not node:
        return f"Symbol '{name}' not found in index."

    kind = node["kind"]
    file_path = node.get("path", "")
    line = node.get("line_start", 0)

    lines = [f"{kind} '{name}' defined in {file_path}:{line}"]

    # Get edges grouped by kind
    edges = storage.get_edges_for_node(name)

    # CONTAINS → list children
    contains = edges.get("CONTAINS", [])
    if contains:
        child_names = [c.get("dst_name", "?") for c in contains][:8]
        lines.append(f"  Contains: {', '.join(child_names)}")

    # INSTANTIATES → outgoing
    inst_out = edges.get("INSTANTIATES", [])
    inst_in = edges.get("INSTANTIATES", [])  # same edge kind, different direction
    inst_out_names = [c.get("dst_name", "?") for c in inst_out if c.get("src_name") == name][:5]

    # Instantiated by → use dedicated query
    instantiators = storage.get_instantiated_by(name)
    if instantiators:
        inst_names = [i["name"] for i in instantiators[:5]]
        lines.append(f"  Instantiated by: {', '.join(inst_names)}")

    # EXTENDS chain
    extends = edges.get("EXTENDS", [])
    if extends:
        base_classes = [c.get("dst_name", "?") for c in extends][:3]
        lines.append(f"  Extends: {', '.join(base_classes)}")

    # IMPORTS
    imports = storage.get_edges_by_kind(name, "IMPORTS")
    if imports:
        pkg_names = [i.get("dst_name", "?") for i in imports][:5]
        lines.append(f"  Imports: {', '.join(pkg_names)}")

    # Node type-specific meta
    if kind == "checker":
        lines.append("  [SVA Checker — formal verification unit]")
    elif kind == "covergroup":
        lines.append("  [Coverage Group — collects functional coverage samples]")

    return "\n".join(lines)
