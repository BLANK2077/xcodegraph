"""Cross-file Reference Resolver — batch resolve unresolved_refs to edges."""

from __future__ import annotations

from xcodegraph.core.storage import Storage


class ReferenceResolver:
    """Resolve unresolved references by matching against indexed nodes.

    Strategies (in priority order):
        1. Exact name match (same kind preferred)
        2. Name match with different kind (fallback)
    """

    RESOLVABLE_KINDS = {"EXTENDS", "IMPORTS", "INSTANTIATES", "REFERENCES"}

    def resolve(self, storage: Storage) -> dict:
        """Run a resolution pass. Returns counts of resolved/remaining refs."""
        total = 0
        resolved = 0

        refs = list(storage.conn.execute(
            "SELECT id, kind, name, line, context_node_id FROM unresolved_refs"
        ).fetchall())

        for ref in refs:
            rkind = ref["kind"]
            if rkind not in self.RESOLVABLE_KINDS:
                continue
            total += 1

            target = self._find_target(storage, ref["name"], rkind)
            if target and ref["context_node_id"]:
                # Create edge from context node to resolved target
                src_node = storage.get_node_by_id(ref["context_node_id"])
                if src_node:
                    storage.conn.execute(
                        """INSERT INTO edges (src_id, dst_id, kind, src_name, dst_name, line)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            ref["context_node_id"], target["id"], rkind,
                            src_node["name"], target["name"], ref["line"],
                        ),
                    )
                    # Delete the resolved ref
                    storage.conn.execute("DELETE FROM unresolved_refs WHERE id = ?", (ref["id"],))
                    resolved += 1

        storage.conn.commit()
        remaining = total - resolved
        return {"total": total, "resolved": resolved, "remaining": remaining}

    def _find_target(self, storage: Storage, name: str, kind: str) -> dict | None:
        """Find the best matching node for a reference."""
        # Clean parameterized names: uvm_driver #(uart_transfer) → uvm_driver
        clean_name = name.split("#")[0].strip()
        # Clean package scope: pkg::name → name
        clean_name = clean_name.split("::")[-1].strip()

        # Strategy 1: match kind based on reference type
        kind_map = {
            "EXTENDS": ("class", "interface"),
            "INSTANTIATES": ("module", "interface", "class"),
            "IMPORTS": ("package",),
            "REFERENCES": ("interface", "module", "class"),
        }
        target_kinds = kind_map.get(kind, ("module", "interface", "class", "package"))

        for tk in target_kinds:
            node = storage.get_node(clean_name, tk)
            if node:
                return node

        # Strategy 2: any kind
        node = storage.get_node(clean_name)
        return node
