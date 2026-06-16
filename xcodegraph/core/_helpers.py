"""Shared helpers — no circular imports."""

from __future__ import annotations

import hashlib

from tree_sitter import Node as TSNode


def generate_node_id(file_path: str, kind: str, name: str, line: int) -> str:
    raw = f"{file_path}:{kind}:{name}:{line}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:32]
    return f"{kind}:{h}"


def ts_node_text(node: TSNode) -> str:
    """Get node text — Python tree-sitter has .text as a property."""
    t = node.text
    if isinstance(t, bytes):
        return t.decode("utf-8", errors="replace")
    return t or ""


def ts_node_text_bytes(node: TSNode) -> bytes:
    t = node.text
    if isinstance(t, str):
        return t.encode("utf-8")
    return t or b""
