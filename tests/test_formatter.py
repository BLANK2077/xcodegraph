"""TDD: Markdown formatter — all format_* functions."""

import pytest
from xcodegraph.core import formatter


# ── format_search_results ───────────────────────────────────────────────

class TestFormatSearch:
    def test_basic_table(self):
        results = [
            {"kind": "module", "name": "uart_tx", "path": "rtl/uart_tx.sv", "line_start": 2},
            {"kind": "class", "name": "uart_driver", "path": "tb/uart_pkg.sv", "line_start": 46},
        ]
        out = formatter.format_search_results("uart", results)
        assert "Search" in out
        assert "uart_tx" in out
        assert "uart_driver" in out
        assert "rtl/uart_tx.sv" in out
        # Should not contain internal fields
        assert "id" not in out.split("|")[-1]

    def test_empty_results(self):
        out = formatter.format_search_results("zzz_nonexistent", [])
        assert "No results" in out

    def test_truncates_large_results(self):
        results = [{"kind": "module", "name": f"mod_{i}", "path": "a.sv", "line_start": i}
                   for i in range(50)]
        out = formatter.format_search_results("mod", results, max_results=5)
        assert "5 more" in out.lower() or "narrow" in out.lower()


# ── format_node_detail ──────────────────────────────────────────────────

class TestFormatNodeDetail:
    def test_basic_module(self):
        node = {"kind": "module", "name": "uart_tx", "path": "rtl/uart_tx.sv",
                "line_start": 2, "signature": "module uart_tx(input logic clk);"}
        edges = {"CONTAINS": [{"src_name": "uart_tx", "dst_name": "u_baud"}],
                 "EXTENDS": []}
        out = formatter.format_node_detail(node, edges)
        assert "## uart_tx (module)" in out
        assert "rtl/uart_tx.sv:2" in out
        assert "u_baud" in out
        # Should not contain DB internal fields
        assert "id" not in out
        assert "file_id" not in out
        assert "attributes_json" not in out

    def test_no_empty_edge_sections(self):
        node = {"kind": "module", "name": "m", "path": "m.sv", "line_start": 1}
        edges = {}
        out = formatter.format_node_detail(node, edges)
        assert "EXTENDS" not in out
        assert "IMPORTS" not in out

    def test_lib_boundary_marks_stdlib(self):
        node = {"kind": "class", "name": "my_drv", "path": "tb/pkg.sv", "line_start": 10}
        edges = {"EXTENDS": [{"src_name": "my_drv", "dst_name": "uvm_driver",
                               "file": "/opt/uvm-1.2/src/base/uvm_driver.svh"}]}
        out = formatter.format_node_detail(node, edges)
        assert "uvm_driver" in out
        assert "stdlib" in out.lower()

    def test_source_only_when_requested(self):
        node = {"kind": "module", "name": "m", "path": "rtl/top.sv", "line_start": 1,
                "line_end": 3}
        edges = {}
        # Default: no source
        out = formatter.format_node_detail(node, edges)
        assert "```" not in out
        # source=true: source included
        out = formatter.format_node_detail(node, edges, show_source=True,
                                           source_lines=["module top;", "endmodule"])
        assert "```" in out
        assert "module top" in out

    def test_children_filtered(self):
        """CONTAINS from file/package to this node should be suppressed."""
        node = {"kind": "class", "name": "my_drv", "path": "tb/pkg.sv", "line_start": 10}
        edges = {"CONTAINS": [
            {"src_name": "my_pkg", "dst_name": "my_drv"},      # ← suppress: package→class
            {"src_name": "my_drv", "dst_name": "run_phase"},   # ← keep: own children
        ]}
        out = formatter.format_node_detail(node, edges)
        assert "run_phase" in out
        assert "my_pkg" not in out  # file-containment suppressed


# ── format_hierarchy ────────────────────────────────────────────────────

class TestFormatHierarchy:
    def test_tree_structure(self):
        hierarchy = [
            {"kind": "module", "name": "top", "depth": 0, "path": "top.sv", "line_start": 1},
            {"kind": "module", "name": "sub", "depth": 1, "path": "sub.sv", "line_start": 1},
        ]
        out = formatter.format_hierarchy(hierarchy, "top")
        assert "top" in out
        assert "sub" in out
        assert "├──" in out or "└──" in out

    def test_depth_truncation(self):
        hierarchy = [{"kind": "module", "name": f"m_{i}", "depth": i, "path": "x.sv", "line_start": 1}
                     for i in range(20)]
        out = formatter.format_hierarchy(hierarchy, "m_0", max_depth=3)
        assert "truncated" in out.lower() or "more levels" in out.lower()


# ── format_instantiated_by ──────────────────────────────────────────────

class TestFormatInstantiatedBy:
    def test_shows_instantiators(self):
        results = [{"kind": "module", "name": "top", "path": "top.sv", "line_start": 1}]
        out = formatter.format_instantiated_by(results, "sub")
        assert "top" in out
        assert "Instantiated" in out
        assert "sub" in out


# ── format_status ───────────────────────────────────────────────────────

class TestFormatStatus:
    def test_shows_key_stats(self):
        stats = {"file_count": 7, "node_count": 65, "edge_count": 63, "unresolved_ref_count": 36}
        meta = {"git_head": "abc123", "backend": "tree-sitter", "schema_version": "1",
                "created_at": "2026-01-01", "updated_at": "2026-01-02"}
        out = formatter.format_status(stats, meta)
        assert "65" in out
        assert "abc123" in out
        assert "tree-sitter" in out
        # Timestamps suppressed
        assert "created_at" not in out
        assert "2026-01-01" not in out


# ── format_definition ───────────────────────────────────────────────────

class TestFormatDefinition:
    def test_location_output(self):
        node = {"kind": "module", "name": "uart_tx", "path": "rtl/uart_tx.sv", "line_start": 2}
        out = formatter.format_definition(node)
        assert "uart_tx" in out
        assert "rtl/uart_tx.sv:2" in out


# ── _is_lib_node ────────────────────────────────────────────────────────

class TestLibBoundary:
    def test_uvm_path_detected(self):
        assert formatter._is_lib_node("/opt/uvm-1.2/src/base/uvm_driver.svh")
        assert formatter._is_lib_node("/proj/uvm_pkg.sv")
        assert not formatter._is_lib_node("/proj/tb/my_pkg.sv")
