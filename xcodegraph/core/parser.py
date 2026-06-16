"""Tree-sitter extraction pipeline for SystemVerilog."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import tree_sitter_systemverilog as tssv
from tree_sitter import Language, Node as TSNode, Parser as TSParser

from ..models import Edge, ExtractionResult, Node, UnresolvedRef
from ._helpers import generate_node_id, ts_node_text, ts_node_text_bytes
from .visitor import SVEVisitor, ExtractionContext


# ── parser ─────────────────────────────────────────────────────────────────

class SVParser:
    """SystemVerilog tree-sitter parser + extraction pipeline."""

    def __init__(self):
        self._lang = Language(tssv.language())
        self._parser = TSParser(self._lang)
        self._visitor = SVEVisitor()

    def extract(self, file_path: str, source: str) -> ExtractionResult:
        """Parse a single SV source file and return the extraction result."""
        t0 = time.time()
        ctx = ExtractionContext(file_path=file_path, source=source)

        try:
            src_bytes = source.encode("utf-8")
            tree = self._parser.parse(src_bytes)
            root = tree.root_node

            # Create file-level root node
            file_id = generate_node_id(file_path, "file", file_path, 1)
            ctx._file_node_id = file_id
            file_node = Node(
                id=file_id,
                kind="file",
                name=file_path,
                file_path=file_path,
                line_start=1,
                line_end=source.count("\n") + 1,
            )
            ctx.nodes.append(file_node)
            ctx.push_scope(file_id)

            # Traverse
            self._visit(root, ctx)

            ctx.pop_scope()

        except Exception as e:
            ctx.errors.append(f"Parse error in {file_path}: {e}")

        result = ExtractionResult(
            nodes=ctx.nodes,
            edges=ctx.edges,
            unresolved_refs=ctx.unresolved_refs,
            errors=ctx.errors,
            warnings=ctx.warnings,
            duration_ms=(time.time() - t0) * 1000,
        )
        return result

    # ── traversal ───────────────────────────────────────────────────────

    def _visit(self, node: TSNode, ctx: ExtractionContext) -> None:
        handled = self._visitor.visit_node(node, ctx)
        if not handled:
            for child in node.named_children:
                self._visit(child, ctx)
